import re

from support import config
from support.kb import KB, grams


def test_articles_load_and_chunk():
    kb = KB()
    assert len(kb.articles) >= 19
    assert "KB-RET-01#1" in kb.by_cid and "KB-RET-01#3" in kb.by_cid
    assert all(c.text for c in kb.chunks)


def test_internal_articles_marked():
    kb = KB()
    internal = {a.id for a in kb.articles if not a.public}
    assert {"KB-REF-02", "KB-PRV-01", "KB-POL-01"} <= internal


def test_policy_numbers_match_kb_text():
    """config.POLICY は kb/ の写し。食い違えば落ちる（正は kb/）。"""
    kb = KB()
    body = lambda aid: kb.by_article[aid].body.replace(",", "")
    P = config.POLICY
    assert f"{P['return_days_unopened']}日以内" in body("KB-RET-01")
    assert f"{P['defect_days']}日以内" in body("KB-RET-01")
    assert f"{P['free_shipping_yen']}円以上" in body("KB-SHP-01")
    assert f"{P['shipping_fee_yen']}円" in body("KB-SHP-01")
    assert f"{P['refund_needs_lead_yen']}円以上" in body("KB-REF-02")
    assert f"{P['subscription_change_days_before']}日前" in body("KB-SUB-01")
    assert f"合計{P['extended_total_years']}年" in body("KB-WAR-01")
    assert f"{P['extended_join_days']}日以内" in body("KB-WAR-01")


def test_search_finds_shipping_fee_with_category():
    kb = KB()
    top = kb.search("送料はいくらかかりますか", k=3, category="shipping")
    assert top[0][0].article_id == "KB-SHP-01"


def test_search_public_only_excludes_internal():
    kb = KB()
    hits = kb.search("お詫びのクーポン", k=5, public_only=True)
    assert all(c.public for c, _ in hits)


def test_product_boost_prefers_product_article():
    kb = KB()
    top = kb.search("電源が入りません", k=1, product="K1")
    assert top[0][0].article_id == "KB-TRB-K1"


def test_grams_are_bigrams():
    g = grams("送料無料")
    assert "送料" in g and "無料" in g


def test_no_text_conflicts_between_public_articles():
    """お客様向けの記事に『必ず』の言い切りが無い（規程の書き方の約束）。"""
    kb = KB()
    for a in kb.articles:
        if a.public:
            assert not re.search(r"必ず|絶対", a.body), a.id
