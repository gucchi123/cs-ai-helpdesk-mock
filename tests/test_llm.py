import json

import pytest

from support import llm, prompts


def test_get_providers():
    assert llm.get("mock").name == "mock"
    assert llm.get("mock_naive").name == "mock_naive"
    assert llm.get("mock_flaky").name == "mock_flaky"
    with pytest.raises(ValueError):
        llm.get("nope")


def test_mock_meta_is_estimated():
    out = llm.get("mock").run("classify", {"text": "送料はいくらですか"})
    m = out["_meta"]
    assert m["estimated"] and m["in"] > 0 and m["cost_usd"] > 0 and m["model"] == "mock"


def test_anthropic_without_key_raises():
    with pytest.raises(RuntimeError) as e:
        llm.get("anthropic")
    assert "ANTHROPIC_API_KEY" in str(e.value)


def test_recorded_missing_raises(tmp_path):
    p = llm.RecordedProvider(str(tmp_path / "none.jsonl"))
    with pytest.raises(llm.MissingRecording):
        p.run("classify", {"text": "x"})


def test_recorded_replays_by_prompt_key(tmp_path):
    payload = {"text": "送料はいくらですか"}
    s, u = prompts.build("classify", payload)
    path = tmp_path / "rec.jsonl"
    path.write_text(json.dumps({"key": llm.key_of("classify", s, u), "task": "classify",
                                "output": {"category": "shipping", "confidence": 0.97, "reason": "r"},
                                "meta": {"model": "claude-opus-5-5", "effort": "high", "cost_usd": 0.001}},
                               ensure_ascii=False) + "\n", encoding="utf-8")
    out = llm.RecordedProvider(str(path)).run("classify", payload)
    assert out["category"] == "shipping" and out["_meta"]["replayed"] and out["_meta"]["model"] == "claude-opus-5-5"


def test_redact():
    assert "sk-ant-" in llm.redact("key sk-ant-abc123XYZ") and "abc123" not in llm.redact("key sk-ant-abc123XYZ")


def test_prices_and_cost():
    assert llm.price("claude-opus-5-5") == (4.0, 20.0, 0.20)
    assert llm.price("claude-haiku-5-5") == (0.10, 0.50, 0.01)
    assert abs(llm.cost_usd("claude-opus-5-5", 1_000_000, 0) - 4.0) < 1e-9


def test_parse_json():
    assert llm.parse_json('前置き {"a": 1} 後ろ') == {"a": 1}
    with pytest.raises(ValueError):
        llm.parse_json("no json")


def test_default_model_and_effort():
    assert llm.DEFAULT_MODEL == "claude-opus-5-5" and llm.DEFAULT_EFFORT == "high"


def test_ledger_spent_zero_in_tests():
    assert llm.spent() == 0


# ---- agent-sdk（講師の収録用）。本物は呼ばない: SDK の query を偽物に差し替える
def _fake_sdk(monkeypatch, text: str, seen: dict, usage: dict | None = None):
    import claude_agent_sdk as sdk

    async def fake_query(prompt, options):
        seen.setdefault("calls", []).append({"prompt": prompt, "options": options})
        yield sdk.AssistantMessage(content=[sdk.TextBlock(text=text)], model="claude-opus-5-5")
        yield sdk.ResultMessage(subtype="success", duration_ms=10, duration_api_ms=8, is_error=False, num_turns=1,
                                session_id="s", total_cost_usd=0.0123,
                                usage=usage or {"input_tokens": 900, "output_tokens": 300, "cache_read_input_tokens": 100})
    monkeypatch.setattr(sdk, "query", fake_query)


def test_agent_sdk_records_like_anthropic_and_replays(monkeypatch, tmp_path):
    seen: dict = {}
    _fake_sdk(monkeypatch, '分類しました ```json\n{"category": "shipping", "confidence": 0.9, "reason": "r"}\n```', seen)
    rec = tmp_path / "anthropic_runs.jsonl"
    p = llm.get("agent-sdk", tag="t", record_path=str(rec))
    assert p.name == "agent-sdk" and p.model == "claude-opus-5-5" and p.effort == "high"
    payload = {"text": "送料はいくらですか"}
    out = p.run("classify", payload)
    assert out["category"] == "shipping"
    m = out["_meta"]
    assert m["provider"] == "agent-sdk" and m["effort"] == "high" and m["in"] == 900 and m["out"] == 300
    assert m["cost_usd"] == round(llm.cost_usd("claude-opus-5-5", 900, 300, 100), 6) and m["billed"] is False
    # SDK に渡した設定: 依頼文の system で置き換え・道具なし・設定を読まない・1 ターン・キーは空
    o = seen["calls"][0]["options"]
    s, u = prompts.build("classify", payload)
    assert seen["calls"][0]["prompt"] == u and o.system_prompt == s
    assert o.tools == [] and o.setting_sources == [] and o.strict_mcp_config and o.max_turns == 1
    assert o.env["ANTHROPIC_API_KEY"] == "" and o.model == "claude-opus-5-5" and o.effort == "high"
    # 記録は anthropic と同じ形 → recorded で再生できる
    row = json.loads(rec.read_text(encoding="utf-8").splitlines()[0])
    assert row["key"] == llm.key_of("classify", s, u) and row["meta"]["provider"] == "agent-sdk"
    r2 = llm.RecordedProvider(str(rec)).run("classify", payload)
    assert r2["category"] == "shipping" and r2["_meta"]["replayed"] and r2["_meta"]["model"] == "claude-opus-5-5"
    # 台帳には残るが、予算には数えない
    rows = llm.ledger_rows()
    assert rows and rows[-1]["provider"] == "agent-sdk" and llm.spent() == 0


def test_agent_sdk_resumes_from_its_records(monkeypatch, tmp_path):
    seen: dict = {}
    _fake_sdk(monkeypatch, '{"category": "howto", "confidence": 0.8, "reason": "r"}', seen)
    rec = str(tmp_path / "rec.jsonl")
    llm.get("agent-sdk", record_path=rec).run("classify", {"text": "a"})
    p2 = llm.get("agent-sdk", record_path=rec)               # 回し直し
    out = p2.run("classify", {"text": "a"})
    assert out["category"] == "howto" and out["_meta"]["reused"] and len(seen["calls"]) == 1
    p2.run("classify", {"text": "b"})                         # 新しい入力だけ呼ぶ
    assert len(seen["calls"]) == 2


def test_agent_sdk_parse_error_and_error_are_safe(monkeypatch, tmp_path):
    seen: dict = {}
    _fake_sdk(monkeypatch, "JSON ではない返事", seen)
    out = llm.get("agent-sdk", record_path=str(tmp_path / "r.jsonl")).run("classify", {"text": "a"})
    assert out["_parse_error"] and out["_raw"]

    def boom(*a, **k):
        raise RuntimeError("failed with sk-ant-abc123XYZ")
    monkeypatch.setattr(llm, "sdk_query", boom)
    with pytest.raises(RuntimeError) as e:
        llm.get("agent-sdk", record_path=str(tmp_path / "r2.jsonl")).run("classify", {"text": "a"})
    assert "abc123" not in str(e.value)


def test_agent_sdk_through_pipeline(monkeypatch, tmp_path, world):
    from support import pipeline
    seen: dict = {}
    _fake_sdk(monkeypatch, '{"category": "shipping", "confidence": 0.95, "reason": "r", "reply": "ご連絡ありがとうございます。",'
                           ' "citations": [], "needs_human": true}', seen)
    p = llm.get("agent-sdk", record_path=str(tmp_path / "r.jsonl"))
    r = pipeline.process(world["tickets"][0], pipeline.Ctx.make(p, step=4, world=world))
    assert r["provider"] == "agent-sdk" and seen["calls"]
