from support import analytics, knowledge, llm, pii, pipeline
from support.kb import KB


def _results(world, n=None):
    ctx = pipeline.Ctx.make("mock", step=4, world=world)
    ts = world["tickets"][:n] if n else world["tickets"]
    return ts, {t["id"]: pipeline.process(t, ctx) for t in ts}


def test_spikes_found_at_planted_weeks(world):
    rep = analytics.report(world["tickets"])
    sym = {(s["week"], s["key"]) for s in rep["spikes_symptom"]}
    assert (3, "出荷の遅れ") in sym
    assert (5, "途中で電源が切れる") in sym or (6, "途中で電源が切れる") in sym
    assert any(k == "定期便の価格改定" and w >= 6 for w, k in sym)
    assert any(s["key"] == "subscription" and s["week"] == 6 for s in rep["spikes_category"])


def test_no_spike_in_first_two_weeks(world):
    rep = analytics.report(world["tickets"])
    assert all(s["week"] >= 3 for s in rep["spikes_symptom"])


def test_lot_concentration(world):
    rep = analytics.report(world["tickets"])
    assert rep["lots"].get("K-2609", 0) >= 20


def test_graph_and_gaps_with_results(world):
    ts, rs = _results(world)
    g = analytics.report(ts, rs)["graph"]
    rels = {e["rel"] for e in g["edges"]}
    assert {"HAS_SYMPTOM", "CAUSED_BY", "ANSWERED_BY", "SEEN_IN_LOT"} <= rels
    gaps = {x["symptom"] for x in g["knowledge_gaps"]}
    assert "症状:焼きむら" in gaps          # トースターの記事が無い


def test_mermaid_renders(world):
    rep = analytics.report(world["tickets"][:200])
    assert rep["graph"]["edges"] and analytics.mermaid(rep["graph"]).startswith("graph LR")


def test_symptom_vocab():
    assert analytics.symptom_of("満水にしても沸く前に勝手に切れます") == "途中で電源が切れる"
    assert analytics.symptom_of("送料はいくら") is None


def test_knowledge_candidates(world):
    ts, rs = _results(world)
    cands = knowledge.candidates(ts, rs, KB(), llm.get("mock"))
    assert cands
    for c in cands:
        assert c["status"] == "要確認" and c["review_points"]
        assert c["pii_in_draft"] == [] and not pii.detect(c["body"])
        assert c["cases"] >= 5
    assert all(c["symptom"] not in ("出荷の遅れ", "定期便の価格改定") for c in cands)
