from support import config, llm, pipeline


def _t(body, cat="shipping", channel="mail", customer="C0001", order=None, product="K1", contact=1):
    return {"id": "X-1", "created_at": "2026-10-20T10:00", "week": 8, "channel": channel, "customer_id": customer,
            "order_id": order, "product": product, "body": body, "template": "x", "gold": None,
            "resolution": {"cause": "", "symptom": ""}, "pii": [], "injection": False, "contact_count": contact}


class Spy(llm.Provider):
    name = "spy"

    def __init__(self, inner):
        self.inner, self.seen = inner, []

    def run(self, task, payload):
        self.seen.append((task, payload))
        return self.inner.run(task, payload)


def test_auto_send_only_for_allowed_categories(world, eval_set):
    ctx = pipeline.Ctx.make("mock", step=4, world=world)
    for t in eval_set:
        r = pipeline.process(t, ctx)
        if r["action"] == "auto_send":
            assert r["classification"]["category"] in config.AUTO_SEND_CATEGORIES
            assert r["draft"]["citations"] and not r["findings"]


def test_refunds_never_auto_sent(world):
    ctx = pipeline.Ctx.make("mock", step=6, world=world)
    for t in world["tickets"]:
        if t["gold"]["category"] in ("refund", "return", "complaint", "safety") and t["channel"] != "chat":
            assert pipeline.process(t, ctx)["action"] != "auto_send", t["id"]


def test_safety_goes_to_quality_urgent(world):
    ctx = pipeline.Ctx.make("mock", step=4, world=world)
    r = pipeline.process(_t("スミカゼから焦げたにおいがして煙が出ました。", product="A1"), ctx)
    assert r["action"] == "escalate" and r["queue"] == "quality" and r["priority"] == "urgent"


def test_step0_is_human_without_ai(world):
    ctx = pipeline.Ctx.make("mock", step=0, world=world)
    r = pipeline.process(_t("送料はいくらですか"), ctx)
    assert r["action"] == "human" and r["usage"]["calls"] == 0


def test_step1_classifies_but_no_draft(world):
    ctx = pipeline.Ctx.make("mock", step=1, world=world)
    r = pipeline.process(_t("送料はいくらですか"), ctx)
    assert r["draft"] is None and r["classification"]["category"] == "shipping" and r["action"] == "human"


def test_step2_never_auto_sends(world, eval_set):
    ctx = pipeline.Ctx.make("mock", step=2, world=world)
    assert all(pipeline.process(t, ctx)["action"] != "auto_send" for t in eval_set)


def test_step4_auto_sends_shipping_fee(world):
    ctx = pipeline.Ctx.make("mock", step=4, world=world)
    r = pipeline.process(_t("送料無料になる条件を教えてください。"), ctx)
    assert r["action"] == "auto_send" and "5,500円" in r["draft"]["reply"]


def test_llm_never_sees_raw_phone(world):
    spy = Spy(llm.get("mock"))
    ctx = pipeline.Ctx.make(spy, step=4, world=world)
    pipeline.process(_t("届きません。連絡先は090-0000-4321です。"), ctx)
    assert spy.seen and all("090-0000-4321" not in str(p) for _, p in spy.seen)


def test_naive_mode_sends_raw_phone_to_llm(world):
    spy = Spy(llm.get("mock"))
    ctx = pipeline.Ctx.make(spy, step=4, defenses=None, world=world)
    pipeline.process(_t("届きません。連絡先は090-0000-4321です。"), ctx)
    assert any("090-0000-4321" in str(p) for _, p in spy.seen)


def test_naive_mode_sends_everything(world, eval_set):
    ctx = pipeline.Ctx.make("mock_naive", step=4, defenses=None, world=world)
    assert all(pipeline.process(t, ctx)["action"] == "auto_send" for t in eval_set[:30])


def test_chat_extends_categories_at_step5(world):
    ctx = pipeline.Ctx.make("mock", step=5, world=world)
    r = pipeline.process(_t("フィルター定期便を解約したいです。手数料はかかりますか？", channel="chat", product="A1"), ctx)
    assert r["action"] == "auto_send"
    ctx4 = pipeline.Ctx.make("mock", step=4, world=world)
    r4 = pipeline.process(_t("フィルター定期便を解約したいです。手数料はかかりますか？", channel="chat", product="A1"), ctx4)
    assert r4["action"] != "auto_send"


class Refuser(llm.Provider):
    name = "refuser"

    def __init__(self, out):
        self.out = out
        self.mock = llm.get("mock")

    def run(self, task, payload):
        return dict(self.out) if task == "draft" else self.mock.run(task, payload)


def test_refusal_is_escalated(world):
    ctx = pipeline.Ctx.make(Refuser({"refusal": True}), step=4, world=world)
    r = pipeline.process(_t("送料はいくらですか"), ctx)
    assert r["action"] == "escalate" and "refusal" in r["escalation"]["reasons"]


def test_parse_error_is_escalated(world):
    ctx = pipeline.Ctx.make(Refuser({"_raw": "x", "_parse_error": True}), step=4, world=world)
    assert pipeline.process(_t("送料はいくらですか"), ctx)["action"] == "escalate"


def test_no_grounding_goes_to_human(world):
    ctx = pipeline.Ctx.make("mock", step=4, world=world)
    r = pipeline.process(_t("カリッサで焼きむらがあります。", cat="defect", product="T1"), ctx)
    assert r["action"] in ("escalate", "approve")


def test_usage_is_estimated_for_mock(world):
    ctx = pipeline.Ctx.make("mock", step=4, world=world)
    r = pipeline.process(_t("送料はいくらですか"), ctx)
    assert r["usage"]["estimated"] and r["usage"]["cost_usd"] > 0
