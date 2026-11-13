"""1 件の問い合わせを、受付から「送る / 人の承認へ / 人に引き継ぐ」まで通す。

  受付 → ① 個人情報を伏せる → ② 分類 → ③ ナレッジ検索 → ④ 引き継ぎの規則 → ⑤ 下書き（根拠つき）
       → ⑥ 送る前の検査（根拠・口調と約束・個人情報・社内記事） → ⑦ 決める（人の承認の境界）

🔴 ⑦ の境界はコードが決める。AI の「人に回さなくてよい」は判断材料の 1 つにすぎない。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from support import checks, config, escalation, flags as flagmod, grounding, injection, llm, pii, seed
from support.kb import KB, default_kb

MIN_SCORE = 3.0        # これより弱い検索結果は「根拠なし」として扱う


@dataclass
class Ctx:
    kb: KB
    provider: llm.Provider
    flags: dict
    world: dict
    customers: dict = field(default_factory=dict)
    orders: dict = field(default_factory=dict)
    last_customer: dict | None = None      # 素朴な作り（isolate_context=False）で前のお客様の情報が混ざる経路

    @classmethod
    def make(cls, provider: str | llm.Provider = "mock", step: int = 4, defenses=True, world: dict | None = None,
             kb: KB | None = None) -> "Ctx":
        w = world or seed.world()
        p = llm.get(provider) if isinstance(provider, str) else provider
        f = flagmod.make(step, defenses) if defenses is not None else flagmod.naive(step)
        return cls(kb=kb or default_kb(), provider=p, flags=f, world=w,
                   customers={c["id"]: c for c in w["customers"]}, orders={o["id"]: o for o in w["orders"]})


def _meta_sum(metas: list[dict]) -> dict:
    return {"calls": len(metas), "cost_usd": round(sum(m.get("cost_usd", 0) for m in metas), 6),
            "in": sum(m.get("in", 0) for m in metas), "out": sum(m.get("out", 0) for m in metas),
            "estimated": any(m.get("estimated") for m in metas), "seconds": round(sum(m.get("seconds", 0) for m in metas), 2)}


def process(t: dict, ctx: Ctx, channel: str | None = None) -> dict:
    f = ctx.flags
    channel = channel or t.get("channel", "mail")
    customer = ctx.customers.get(t.get("customer_id"))
    order = ctx.orders.get(t.get("order_id"))
    metas: list[dict] = []
    trace: list[str] = []
    raw = t["body"]

    # ① 個人情報を伏せる
    if f["mask_pii"]:
        text, vault = pii.mask(raw)
        trace.append(f"伏せ字: {', '.join(vault.found()) or 'なし'}")
    else:
        text, vault = raw, pii.Vault()

    # ② 分類
    cls = {"category": None, "confidence": 0.0, "reason": "Step 0: AI を使わない"}
    if f["classify"]:
        cls = ctx.provider.run("classify", {"text": text})
        metas.append(cls.pop("_meta", {}))
        if cls.get("category") not in seed.CATEGORY_QUEUE:
            cls = {"category": "howto", "confidence": 0.0, "reason": "分類の出力が不正"}
    category = cls.get("category")

    # ③ ナレッジ検索
    hits = ctx.kb.search(text, k=3, product=t.get("product"), category=category) if f["draft"] or f["classify"] else []
    strong = [(c, s) for c, s in hits if s >= MIN_SCORE]
    chunks = [{"cid": c.cid, "title": c.title, "heading": c.heading, "text": c.text, "score": s} for c, s in strong]

    # ④ 引き継ぎの規則
    esc_ctx = {"order": order, "contact_count": t.get("contact_count", 1), "has_grounding": bool(chunks)}
    if f["escalation_rules"] and f["classify"]:
        esc = escalation.evaluate(text, cls, esc_ctx)
        if not f["detect_injection"] and "injection" in esc["reasons"]:
            esc["reasons"].remove("injection")
            esc["escalate"] = bool(esc["reasons"])
    else:
        esc = {"escalate": False, "reasons": [], "queue": None, "priority": "normal", "labels": []}

    # ⑤ 下書き
    draft = None
    if f["draft"]:
        payload = {"text": text, "category": category or "howto", "channel": channel, "chunks":
                   [{k: c[k] for k in ("cid", "title", "heading", "text", "score")} for c in chunks]}
        if not f["isolate_context"] and ctx.last_customer and ctx.last_customer is not customer:
            payload["context_other"] = ctx.last_customer          # 素朴な作り: 前の会話の情報が混ざる
        draft = ctx.provider.run("draft", payload)
        metas.append(draft.pop("_meta", {}))
        if draft.get("refusal") or draft.get("_parse_error"):
            draft = {"reply": "", "citations": [], "needs_human": True, "note": "AI の応答が使えない（断り・形式違い）"}
            esc["reasons"].append("refusal")
            esc["escalate"] = True
    ctx.last_customer = customer

    # ⑥ 送る前の検査
    findings: list[dict] = []
    ground = {"unsupported": [], "policy_sentences": 0, "details": []}
    if draft is not None:
        reply = draft.get("reply", "")
        if f["grounding"] and f["checks_ui"]:
            ground = grounding.check(reply, {c["cid"]: c["text"] for c in chunks})
            findings += [{"kind": "grounding", "msg": m} for m in ground["unsupported"]]
        if f["checks"] and f["checks_ui"]:
            findings += checks.run(reply, channel=channel, cited=draft.get("citations"),
                                   kb=ctx.kb if channel == "chat" else None)
            for m in pii.leak_check(reply, customer, list(ctx.customers.values())):
                findings.append({"kind": "pii", "msg": m})

    # ⑦ 決める
    queue = esc.get("queue") or (seed.CATEGORY_QUEUE.get(category) if category else "front")
    if not f["classify"]:
        action, why = "human", "Step 0: 人が読んで振り分け、一から書く"
    elif esc["escalate"]:
        action, why = "escalate", "引き継ぎの規則: " + "・".join(escalation.REASON_LABEL.get(r, r) for r in esc["reasons"])
    elif not f["draft"]:
        action, why = "human", "Step 1: 振り分けまで。返信は人が書く"
    elif findings:
        action, why = "approve", "下書きの検査で問題: " + " / ".join(x["msg"] for x in findings[:3])
    elif draft.get("needs_human"):
        action, why = "approve", "AI が人の確認を求めた"
    elif f["auto_send"] and _auto_ok(f, category, cls, draft, channel):
        action, why = "auto_send", "自動送信の条件をすべて満たした"
    else:
        action, why = "approve", "人の承認の境界（この分類・条件では自動送信しない）"

    return {
        "ticket_id": t["id"], "channel": channel, "masked_text": text, "pii_found": vault.found(),
        "injection_signs": injection.detect(raw), "classification": cls, "retrieval": chunks,
        "escalation": esc, "draft": draft, "grounding": ground, "findings": findings,
        "action": action, "why": why, "queue": queue, "priority": esc.get("priority", "normal"),
        "usage": _meta_sum(metas), "provider": ctx.provider.name, "step": f["step"],
    }


def _auto_ok(f: dict, category, cls: dict, draft: dict, channel: str) -> bool:
    if not f["approval_boundary"]:
        return True        # 素朴な作り: AI が needs_human=false なら全部送る
    allowed = tuple(config.AUTO_SEND_CATEGORIES)
    if channel == "chat" and f.get("chat"):
        allowed += config.CHAT_EXTRA_CATEGORIES      # チャットは「案内だけ」の分類も答える（約束は検査で止まる）
    return (category in allowed and cls.get("confidence", 0) >= config.AUTO_SEND_MIN_CONFIDENCE
            and bool(draft.get("citations")) and _top_matches(category, draft))


PREFIX = {"shipping": ("KB-SHP",), "howto": ("KB-HOW",), "account": ("KB-ACC", "KB-PAY"),
          "subscription": ("KB-SUB",), "refund": ("KB-REF-01",), "warranty": ("KB-WAR",)}


def _top_matches(category, draft) -> bool:
    """自動送信は、いちばん上に引用した記事の分類が、問い合わせの分類と同じときだけ（的外れの返信を自動で送らない）。"""
    first = (draft.get("citations") or [""])[0]
    pref = PREFIX.get(category, ())
    return first.startswith(pref) if pref else False
