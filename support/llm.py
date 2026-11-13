"""AI の呼び先の切り替え（provider）と費用の台帳。

- mock      : キー不要・決まった筋書き（support/mock_brain.py）。profile="careful"（ふつう）/ "naive"（筋書きで失敗する）
- recorded  : 本物のモデルで回した応答を labs/recorded/*.jsonl から再生する。キー不要・同じ入力なら同じ出力
- anthropic : 本物の Claude（既定 claude-opus-5-5・effort high）。環境変数 ANTHROPIC_API_KEY。応答は recorded にも保存する
- agent-sdk : 講師の収録用。本物の Claude を Claude Agent SDK（プランのログイン）で呼ぶ。記録の形は anthropic と同じ（provider 欄は agent-sdk）

🔴 mock の数字は性能の証拠ではない。講座で「AI がこう答えた」と言うのは anthropic（または、その記録の再生）だけ。
🔴 API キーは画面にもファイルにも出さない。エラー文は redact() で伏せ字にする。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from datetime import datetime

from support import config, prompts

DEFAULT_MODEL = os.environ.get("LLM_MODEL", "claude-opus-5-5")
DEFAULT_EFFORT = os.environ.get("LLM_EFFORT", "high")
LEDGER = os.environ.get("LLM_LEDGER", os.path.join(config.ROOT, "_api_cost_ledger.jsonl"))
BUDGET_USD = float(os.environ.get("LLM_BUDGET_USD", "3"))   # 既定は小さく（本物の 1 回の実演に足りる額）

# 公式単価（USD / 100 万トークン）: (入力, 出力, キャッシュ読み)。費用の見積もりにも使う
PRICES = {
    "claude-opus-5-5": (4.0, 20.0, 0.20),
    "claude-sonnet-5-5": (2.0, 10.0, 0.20),
    "claude-haiku-5-5": (0.10, 0.50, 0.01),
}
TOKENS_PER_CHAR = 0.9   # ASSUME: 日本語 1 文字あたりのトークン数の見積もり（本物の実行で置き換える）
_lock = threading.Lock()


class BudgetExceeded(RuntimeError):
    pass


class MissingRecording(KeyError):
    pass


def price(model: str) -> tuple[float, float, float]:
    for k, v in PRICES.items():
        if model.startswith(k):
            return v
    return (5.0, 25.0, 0.5)


def cost_usd(model: str, tin: int, tout: int, cache_read: int = 0) -> float:
    pin, pout, pcr = price(model)
    return (tin * pin + tout * pout + cache_read * pcr) / 1_000_000


def estimate_tokens(system: str, user: str, output: str) -> tuple[int, int]:
    return int((len(system) + len(user)) * TOKENS_PER_CHAR), int(len(output) * TOKENS_PER_CHAR)


def record(entry: dict) -> None:
    entry = {"t": datetime.now().isoformat(timespec="seconds"), **entry}
    with _lock, open(LEDGER, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def ledger_rows() -> list[dict]:
    if not os.path.exists(LEDGER):
        return []
    out = []
    for line in open(LEDGER, encoding="utf-8"):
        try:
            out.append(json.loads(line))
        except ValueError:
            pass
    return out


def spent() -> float:
    # agent-sdk の行は API の換算額（請求されない）なので予算には数えない
    return sum(float(r.get("cost_usd", 0)) for r in ledger_rows() if r.get("provider") != "agent-sdk")


def api_key() -> str | None:
    k = os.environ.get("ANTHROPIC_API_KEY")
    if k:
        return k
    if os.name == "nt":   # Windows: ユーザー環境変数から読む（表示しない）
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as h:
                return winreg.QueryValueEx(h, "ANTHROPIC_API_KEY")[0]
        except OSError:
            return None
    return None


def redact(s: str) -> str:
    return re.sub(r"sk-ant-[A-Za-z0-9_\-]+", "sk-ant-…(伏せ字)", str(s))


def key_of(task: str, system: str, user: str) -> str:
    return hashlib.sha256(f"{task}\n{system}\n{user}".encode("utf-8")).hexdigest()[:24]


def parse_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("応答に JSON がありません")
    return json.loads(m.group(0))


class Provider:
    name = "base"
    model = "-"
    effort = "-"

    def run(self, task: str, payload: dict) -> dict:
        raise NotImplementedError


class MockProvider(Provider):
    """筋書きで動く AI の代わり。費用は「本物で同じ長さの入出力だったら」の見積もり（estimated=True）。"""

    def __init__(self, profile: str = "careful", price_model: str = DEFAULT_MODEL):
        self.profile = profile
        self.name = "mock" if profile == "careful" else f"mock_{profile}"
        self.price_model = price_model

    def run(self, task: str, payload: dict) -> dict:
        from support import mock_brain
        out = mock_brain.run(task, payload, self.profile)
        system, user = prompts.build(task, payload)
        tin, tout = estimate_tokens(system, user, json.dumps(out, ensure_ascii=False))
        out["_meta"] = {"provider": self.name, "model": "mock", "estimated": True, "in": tin, "out": tout,
                        "cost_usd": round(cost_usd(self.price_model, tin, tout), 6), "seconds": 0.0}
        return out


class RecordedProvider(Provider):
    """本物の応答の記録を再生する。記録に無い入力は MissingRecording（mock にすり替えない）。"""
    name = "recorded"

    def __init__(self, path: str | None = None):
        self.path = path or os.path.join(config.RECORDED_DIR, "anthropic_runs.jsonl")
        self.rows: dict[str, dict] = {}
        if os.path.exists(self.path):
            for line in open(self.path, encoding="utf-8"):
                try:
                    r = json.loads(line)
                    self.rows[r["key"]] = r
                except (ValueError, KeyError):
                    pass

    def run(self, task: str, payload: dict) -> dict:
        system, user = prompts.build(task, payload)
        k = key_of(task, system, user)
        if k not in self.rows:
            raise MissingRecording(f"記録がありません（task={task} key={k}）。anthropic で一度回すと記録されます")
        r = self.rows[k]
        out = dict(r["output"])
        out["_meta"] = {**r.get("meta", {}), "provider": "recorded", "replayed": True}
        return out


class AnthropicProvider(Provider):
    name = "anthropic"

    def __init__(self, model: str | None = None, effort: str | None = None, max_tokens: int = 4000, tag: str = "",
                 record_path: str | None = None):
        import anthropic
        key = api_key()
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY が見つかりません。CSAI_PROVIDER=mock か recorded を使ってください")
        self.client = anthropic.Anthropic(api_key=key)
        del key
        self.model = model or DEFAULT_MODEL
        self.effort = effort or DEFAULT_EFFORT
        self.max_tokens = max_tokens
        self.tag = tag
        self.record_path = record_path or os.path.join(config.RECORDED_DIR, "anthropic_runs.jsonl")

    def run(self, task: str, payload: dict) -> dict:
        if spent() + 0.05 >= BUDGET_USD:
            raise BudgetExceeded(f"予算 {BUDGET_USD} USD に近づいたので止めます（使用済み {spent():.2f} USD）")
        import anthropic
        system, user = prompts.build(task, payload)
        t0 = time.time()
        kw = dict(model=self.model, max_tokens=self.max_tokens, system=system,
                  messages=[{"role": "user", "content": user}], output_config={"effort": self.effort})
        try:
            if self.model.startswith(("claude-opus-5-5", "claude-sonnet-5-5")):
                # 安全上の理由で断られたとき、サーバー側で別のモデルに回す（既定の作法）
                resp = self.client.beta.messages.create(betas=["server-side-fallback-2026-07-01"],
                                                        extra_body={"fallbacks": "default"}, **kw)
            else:
                resp = self.client.messages.create(**kw)
        except anthropic.BadRequestError as e:
            if "fallback" in str(e).lower():
                resp = self.client.messages.create(**kw)
            else:
                raise RuntimeError(redact(str(e))) from None
        except anthropic.APIError as e:
            raise RuntimeError(redact(f"{type(e).__name__}: {e}")) from None
        if resp.stop_reason == "refusal":
            # 断られた: 本文は空として扱い、人に回す（pipeline 側で refusal を見て escalate）
            text = '{"refusal": true}'
        else:
            text = "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", "") == "text")
        u = resp.usage
        tin, tout = int(u.input_tokens or 0), int(u.output_tokens or 0)
        cr = int(getattr(u, "cache_read_input_tokens", 0) or 0)
        meta = {"provider": "anthropic", "model": getattr(resp, "model", self.model), "effort": self.effort,
                "in": tin, "out": tout, "cost_usd": round(cost_usd(self.model, tin, tout, cr), 6),
                "seconds": round(time.time() - t0, 2), "stop_reason": resp.stop_reason, "estimated": False}
        record({"tag": self.tag or task, "task": task, **meta})
        try:
            out = parse_json(text)
        except ValueError:
            out = {"_raw": text, "_parse_error": True}
        with _lock, open(self.record_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"key": key_of(task, system, user), "task": task, "output": out, "meta": meta},
                               ensure_ascii=False) + "\n")
        out["_meta"] = meta
        return out


def sdk_query(system: str, user: str, model: str, effort: str | None) -> dict:
    """Claude Agent SDK（同梱の Claude Code）をプランのログインで 1 回だけ呼ぶ。道具なし・1 ターン。

    - system_prompt は依頼文の system で丸ごと置き換える（Claude Code の既定の指示は入れない）
    - 組み込みの道具は外す（tools=[]）・講師の手元の設定（CLAUDE.md など）は読まない（setting_sources=[]）
    - 🔴 子プロセスの ANTHROPIC_API_KEY を空にする → API のクレジットではなくログインで動く。キーは読まない・出さない
    戻り値: {"text", "usage", "api_equiv_usd", "model", "is_error", "error", "stop_reason"}
    """
    import asyncio
    import tempfile

    from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ResultMessage, TextBlock, query
    opts = ClaudeAgentOptions(
        model=model, system_prompt=system, tools=[], mcp_servers={}, allowed_tools=[], strict_mcp_config=True,
        setting_sources=[], max_turns=1, cwd=tempfile.mkdtemp(prefix="csai_sdk_"),
        env={"ANTHROPIC_API_KEY": "", "ENABLE_TOOL_SEARCH": "false"},
        **({"effort": effort} if effort else {}))
    texts: list[str] = []
    res: dict = {"model": model}

    async def main() -> None:
        async for m in query(prompt=user, options=opts):
            if isinstance(m, AssistantMessage):
                t = "".join(b.text for b in m.content if isinstance(b, TextBlock))
                if t:
                    texts.append(t)
                res["model"] = getattr(m, "model", None) or res["model"]
                if getattr(m, "stop_reason", None):
                    res["stop_reason"] = m.stop_reason
            elif isinstance(m, ResultMessage):
                res.update(usage=m.usage or {}, api_equiv_usd=m.total_cost_usd, is_error=m.is_error,
                           error=(m.result or "")[:300] if m.is_error else None)
                if getattr(m, "stop_reason", None):
                    res["stop_reason"] = m.stop_reason
    asyncio.run(main())
    res["text"] = texts[-1] if texts else ""
    return res


class AgentSdkProvider(Provider):
    """講師の収録用: Messages API の代わりに Claude Agent SDK（プランのログイン）で呼ぶ。API のクレジットは使わない。

    - 依頼文（prompts.build）・記録の形（labs/recorded/anthropic_runs.jsonl）・台帳の形は anthropic と同じ。
      受講者は recorded でそのまま再生できる。記録の provider 欄は "agent-sdk"。
    - 費用（cost_usd）は「API で同じトークン数だったら」の換算。台帳には残すが、予算（spent）には数えない。
    - 同じ依頼文の agent-sdk の記録が既にあれば、呼ばずにそれを使う（途中で止まっても、回し直せば続きから）。
    🔴 受講者向けの道ではない（受講者は自分のキーで anthropic）。Messages API と違い max_tokens は効かない。
    """
    name = "agent-sdk"

    def __init__(self, model: str | None = None, effort: str | None = None, tag: str = "", record_path: str | None = None,
                 reuse: bool = True, **_ignored):
        self.model = model or DEFAULT_MODEL
        self.effort = effort or DEFAULT_EFFORT
        self.tag = tag
        self.record_path = record_path or os.path.join(config.RECORDED_DIR, "anthropic_runs.jsonl")
        self.done: dict[str, dict] = {}
        if reuse and os.path.exists(self.record_path):
            for line in open(self.record_path, encoding="utf-8"):
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                m = r.get("meta", {})
                if (m.get("provider") == self.name and m.get("effort") == self.effort
                        and str(m.get("model", "")).startswith(self.model) and not r.get("output", {}).get("_parse_error")):
                    self.done[r["key"]] = r

    def run(self, task: str, payload: dict) -> dict:
        system, user = prompts.build(task, payload)
        k = key_of(task, system, user)
        if k in self.done:                                    # 回し直し: 記録済みの応答を使う（呼ばない）
            r = self.done[k]
            out = dict(r["output"])
            out["_meta"] = {**r["meta"], "reused": True}
            return out
        t0 = time.time()
        try:
            r = sdk_query(system, user, self.model, self.effort)
        except Exception as e:  # noqa: BLE001 - エラー文は伏せ字にして投げ直す
            raise RuntimeError(redact(f"agent-sdk: {type(e).__name__}: {e}")) from None
        if r.get("is_error"):
            raise RuntimeError(redact(f"agent-sdk がエラーで終わりました: {r.get('error')}"))
        text = r.get("text") or ""
        if r.get("stop_reason") == "refusal":
            text = '{"refusal": true}'                       # anthropic と同じ扱い（pipeline 側で人に回す）
        u = r.get("usage") or {}
        tin = int(u.get("input_tokens", 0) or 0) + int(u.get("cache_creation_input_tokens", 0) or 0)
        tout = int(u.get("output_tokens", 0) or 0)
        cr = int(u.get("cache_read_input_tokens", 0) or 0)
        meta = {"provider": self.name, "model": r.get("model") or self.model, "effort": self.effort,
                "in": tin, "out": tout, "cost_usd": round(cost_usd(self.model, tin, tout, cr), 6),
                "api_equiv_usd": r.get("api_equiv_usd"), "billed": False,
                "seconds": round(time.time() - t0, 2), "stop_reason": r.get("stop_reason"), "estimated": False}
        record({"tag": self.tag or task, "task": task, **meta})
        try:
            out = parse_json(text)
        except ValueError:
            out = {"_raw": text, "_parse_error": True}
        row = {"key": k, "task": task, "output": out, "meta": meta}
        with _lock, open(self.record_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        if not out.get("_parse_error"):
            self.done[k] = row
        out = dict(out)
        out["_meta"] = meta
        return out


def get(name: str | None = None, **kw) -> Provider:
    name = name or config.PROVIDER
    if name == "mock":
        return MockProvider("careful")
    if name == "mock_naive":
        return MockProvider("naive")
    if name == "mock_flaky":
        return MockProvider("flaky")
    if name == "recorded":
        return RecordedProvider(**kw)
    if name == "anthropic":
        return AnthropicProvider(**kw)
    if name == "agent-sdk":
        return AgentSdkProvider(**kw)
    raise ValueError(f"知らない provider です: {name}（mock / mock_naive / recorded / anthropic / agent-sdk）")
