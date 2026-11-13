import re
from collections import Counter

from support import seed


def test_deterministic():
    a, b = seed.build(7), seed.build(7)
    assert [t["body"] for t in a["tickets"][:50]] == [t["body"] for t in b["tickets"][:50]]


def test_volume_and_weeks(world):
    t = world["tickets"]
    assert 1200 <= len(t) <= 1500
    assert set(x["week"] for x in t) == set(range(1, 9))


def test_trends_are_planted(world):
    t = world["tickets"]
    delay = Counter(x["week"] for x in t if x["template"] == "ship_delay")
    assert delay[3] > 3 * max(delay[1], 1)
    kettle = Counter(x["week"] for x in t if x["template"] == "kettle_lot")
    assert kettle[6] >= 20 and kettle[1] == 0
    price = Counter(x["week"] for x in t if x["template"] == "sub_price")
    assert price[7] >= 15 and price[2] == 0


def test_gold_labels_consistent(world):
    for t in world["tickets"]:
        g = t["gold"]
        assert g["category"] in seed.CATEGORY_QUEUE
        assert g["queue"] in seed.QUEUES
        if g["escalate"]:
            assert g["reason"] and not g["auto_ok"]
        if g["reason"] == "safety":
            assert g["queue"] == "quality" and g["priority"] == "urgent"


def test_refund_threshold_gold_follows_policy(world):
    by_order = {o["id"]: o for o in world["orders"]}
    for t in world["tickets"]:
        g = t["gold"]
        if g["category"] in ("return", "refund") and "返金" in t["body"] and by_order[t["order_id"]]["total"] >= 20000:
            assert g["escalate"]


def test_eval_set_stratified(world):
    es = seed.eval_set(world)
    assert len(es) == 120
    cats = Counter(t["gold"]["category"] for t in es)
    assert all(cats[c] >= 8 for c in seed.CATEGORY_QUEUE)
    assert sum(t["injection"] for t in es) >= 5


def test_fake_pii_formats_only(world):
    for c in world["customers"]:
        assert c["phone"].startswith("090-0000-")
        assert c["email"].endswith("@example.com")


def test_no_card_like_numbers(world):
    rx = re.compile(r"\b(?:\d[ -]?){13,16}\b")
    for t in world["tickets"]:
        assert not rx.search(t["body"]), t["id"]
