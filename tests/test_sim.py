import pytest

from support import sim

R = {}


def step(n):
    if n not in R:
        R[n] = sim.run_step(n)
    return R[n]


def test_step0_baseline():
    r = step(0)
    assert r["auto_send"]["k"] == 0 and r["wrong_first_reply"]["k"] == 0
    assert r["frt_p50_h"] > 4


def test_drafts_cut_operator_time():
    assert step(2)["operator_hours"] < 0.6 * step(0)["operator_hours"]


def test_checks_reduce_wrong_replies():
    assert step(3)["wrong_first_reply"]["k"] <= step(2)["wrong_first_reply"]["k"]


def test_auto_send_cuts_first_response():
    assert step(4)["frt_p50_h"] < step(2)["frt_p50_h"]
    assert step(4)["auto_send"]["rate"] > 0.2


def test_chat_widens_auto_send_with_more_errors():
    """Step 5 で答える範囲を広げると、自動送信は増えるが誤りも増える（判断の材料）。"""
    assert step(5)["auto_send"]["k"] > step(4)["auto_send"]["k"]
    assert step(5)["wrong_first_reply"]["k"] >= step(4)["wrong_first_reply"]["k"]


def test_cost_per_ticket_falls():
    assert step(4)["yen_per_ticket"] < step(0)["yen_per_ticket"]


def test_weekly_frt_has_8_weeks():
    assert len(step(0)["frt_p90_by_week"]) == 8


def test_markdown_mentions_assume():
    md = sim.to_markdown([step(0), step(4)])
    assert "仮定" in md and "mock" in md


@pytest.mark.parametrize("h,expect", [(8, 9), (12, 12), (19, 9)])
def test_business_hours(h, expect):
    from datetime import datetime
    t = sim._next_open(datetime(2026, 10, 21, h, 0))      # 水曜
    assert t.hour == expect


def test_add_work_crosses_night():
    from datetime import datetime
    end = sim._add_work(datetime(2026, 10, 21, 17, 30), 60)
    assert end.day == 22 and end.hour == 9 and end.minute == 30


def test_weekend_skipped():
    from datetime import datetime
    t = sim._next_open(datetime(2026, 10, 24, 10, 0))      # 土曜
    assert t.weekday() == 0
