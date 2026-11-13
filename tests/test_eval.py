from support import eval as ev
from support import llm, pipeline


def test_wilson_known_values():
    lo, hi = ev.wilson(0, 30)
    assert lo == 0.0 and 0.11 <= hi <= 0.12
    lo, hi = ev.wilson(110, 120)
    assert 0.85 < lo < 0.86 and 0.95 < hi < 0.96


def test_kappa():
    assert ev.kappa([True, False, True, False], [True, False, True, False]) == 1.0
    assert ev.kappa([True, True, False, False], [True, False, True, False]) == 0.0


def test_reference_score():
    g = {"must_include": ["8日", "未開封"], "must_not": ["全額返金いたします"]}
    assert ev.reference_score("8日以内・未開封なら返品できます", g)["pass"]
    assert ev.reference_score("8日以内なら返品できます", g)["score"] == 4
    assert ev.reference_score("全額返金いたします。8日・未開封", g)["score"] == 1
    assert not ev.reference_score("", g)["pass"]


def _run(world, eval_set, prov, defenses):
    ctx = pipeline.Ctx.make(prov, step=4, defenses=defenses, world=world)
    rs = [pipeline.process(t, ctx) for t in eval_set]
    return rs, ev.evaluate(rs, eval_set)


def test_designed_metrics(world, eval_set):
    _, m = _run(world, eval_set, "mock", True)
    assert m["classification"]["rate"] >= 0.9
    assert m["escalation"]["recall"]["rate"] >= 0.95
    assert m["sent_with_forbidden_promise"]["k"] == 0
    assert m["sent_with_pii"]["k"] == 0
    assert 0.15 <= m["auto_send"]["rate"] <= 0.45


def test_naive_metrics_are_worse(world, eval_set):
    _, good = _run(world, eval_set, "mock", True)
    _, bad = _run(world, eval_set, "mock_naive", None)
    assert bad["escalation"]["recall"]["k"] == 0
    assert bad["sent_with_forbidden_promise"]["k"] > 10
    assert bad["sent_wrong"]["rate"] > good["sent_wrong"]["rate"]


def test_judge_agreement_reports_disagreements(world, eval_set):
    rs, _ = _run(world, eval_set, "mock", True)
    ja = ev.judge_agreement(rs, eval_set, llm.get("mock"))
    assert ja["n"] > 50 and ja["kappa"] is not None
    assert ja["tpr"]["n"] + ja["tnr"]["n"] == ja["n"]
    # 正解を見ない判定役は、的外れの返信を見逃す（TNR が低い）。この講座で「判定役を疑う」材料にする
    assert ja["tnr"]["rate"] < ja["tpr"]["rate"]


def test_cost_per_ticket_is_reported(world, eval_set):
    _, m = _run(world, eval_set, "mock", True)
    assert m["cost_usd_per_ticket"] > 0
