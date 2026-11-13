from support import checks, grounding
from support.kb import KB

kb = KB()
SRC = {c.cid: c.text for c in kb.chunks}


def test_supported_sentence_passes():
    r = grounding.check("1回のご注文が5,500円以上で送料無料です[KB-SHP-01#2]。", SRC)
    assert r["unsupported"] == [] and r["policy_sentences"] == 1


def test_invented_full_refund_is_flagged():
    r = grounding.check("開封済みの商品でも、到着後30日以内であれば全額返金いたします[KB-RET-01#2]。", SRC)
    assert any("全額" in u for u in r["unsupported"])


def test_number_not_in_source_flagged():
    r = grounding.check("ご注文から1営業日で出荷します[KB-SHP-01#1]。", SRC)
    assert any("1営業日" in u for u in r["unsupported"])


def test_policy_sentence_without_citation_flagged():
    r = grounding.check("送料は無料です。", SRC)
    assert any("引用が無い" in u for u in r["unsupported"])


def test_citation_to_unknown_chunk_flagged():
    r = grounding.check("返品は8日以内です[KB-XXX-99#1]。", SRC)
    assert any("渡していない節" in u for u in r["unsupported"])


def test_non_policy_sentence_ignored():
    r = grounding.check("お問い合わせいただき、ありがとうございます。", SRC)
    assert r["policy_sentences"] == 0


def test_known_limitation_condition_swap_passes_grounding():
    """限界: 節の語を使って条件だけ入れ替えた文は、根拠の検査を通り抜ける。だから約束の検査と人の承認でも止める。"""
    s = "開封済みの商品も返品をお受けします[KB-RET-01#1]。"
    assert grounding.check(s, SRC)["unsupported"] == []


def test_checks_promises():
    kinds = [f["msg"] for f in checks.run("必ず明日お届けします。全額返金いたします。5,000円のクーポンをお送りします。")]
    assert any("必ず" in k for k in kinds)
    assert any("返金" in k for k in kinds)
    assert any("クーポン" in k for k in kinds)
    assert any("届く日" in k for k in kinds)


def test_checks_tone():
    f = checks.run("取扱説明書をよくお読みのうえ、正しくお使いください。申し訳ございません。大変申し訳ございません。")
    msgs = [x["msg"] for x in f if x["kind"] == "tone"]
    assert any("責める" in m for m in msgs) and any("謝罪" in m for m in msgs)


def test_checks_internal_citation_in_chat():
    f = checks.run("担当者が判断します[KB-REF-02#2]。", channel="chat", cited=["KB-REF-02#2"], kb=kb)
    assert any(x["kind"] == "internal" for x in f)


def test_checks_clean():
    assert checks.run("マイページの「ご注文履歴」から、注文ごとの配送状況を確認できます[KB-SHP-02#1]。") == []
