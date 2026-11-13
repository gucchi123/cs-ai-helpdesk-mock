"""導入の道筋（Step 0〜6）の模擬実験: 8 週間ぶんの問い合わせを流して、運用の数字を出す。

python -m support.sim                 # 全 Step（data/sim_report.md と .json）
python -m support.sim --steps 0 2 4   # 一部の Step

🔴 数字はすべて config.ASSUME の仮定のもとでの値。現実の予測ではない。
   「仮定を変えると数字がどう動くか」を見る道具として使う（講座では毎回そう言う）。
🔴 AI は mock_flaky（筋書き。ASSUME の ai_flaky_rate の割合で「よくある失敗」をする）。AI の費用は「本物で同じ長さの入出力だったら」の見積もり（estimated）。
"""
from __future__ import annotations

import argparse
import heapq
import json
import os
import random
from datetime import datetime, timedelta

from support import config, eval as ev, flags as flagmod, kb as kbmod, pipeline, seed

A = config.ASSUME
NEW_ARTICLE = """---
id: KB-NEW-K1
title: ユワカリで水量が十分でも途中で電源が切れるとき
category: defect
product: K1
public: true
updated: 2026-10-05
---
## 水量が十分でも途中で電源が切れる
ロット番号K-2609の一部で、この症状が見つかっています。使うのをやめて窓口にご連絡ください。無償で交換します。
"""


def _is_business(t: datetime) -> bool:
    h0, h1 = A["business_hours"]
    return t.weekday() < 5 and h0 <= t.hour < h1


def _next_open(t: datetime) -> datetime:
    h0, h1 = A["business_hours"]
    t = t.replace(second=0, microsecond=0)
    while not _is_business(t):
        if t.weekday() >= 5 or t.hour >= h1:
            t = (t + timedelta(days=1)).replace(hour=h0, minute=0)
        elif t.hour < h0:
            t = t.replace(hour=h0, minute=0)
    return t


def _add_work(start: datetime, minutes: float) -> datetime:
    """営業時間の中だけで minutes 分の仕事をしたあとの時刻。"""
    h0, h1 = A["business_hours"]
    t = _next_open(start)
    left = minutes
    while left > 1e-9:
        end_today = t.replace(hour=h1, minute=0)
        room = (end_today - t).total_seconds() / 60
        if left <= room:
            return t + timedelta(minutes=left)
        left -= room
        t = _next_open(end_today)
    return t


def _work_plan(step: int, t: dict, r: dict, rng: random.Random) -> dict:
    """1 件に人が何分かけるか・最初の返信が正しいか・自動で送ったか。"""
    g = t["gold"]
    draft = r.get("draft") or {}
    ref = ev.reference_score(draft.get("reply", ""), g) if r.get("draft") is not None else None
    minutes, correct, auto = 0.0, True, False
    misroute = r["queue"] != g["queue"] if step >= 1 else False
    if r["action"] == "auto_send":
        auto = True
        correct = ref["pass"] and not g["escalate"]
    elif r["action"] == "human":
        minutes = A["min_manual"] + (A["min_triage"] if step == 0 else 0)
        if g["escalate"]:
            minutes += A["min_escalation_extra"]
    elif r["action"] == "escalate":
        good_draft = ref is not None and ref["pass"]
        minutes = (A["min_review_draft"] if good_draft else A["min_manual"]) + A["min_escalation_extra"]
    else:  # approve
        if ref["pass"]:
            minutes = A["min_review_approve_only"]
        else:
            minutes = A["min_review_draft"]
            if ref["violations"]:
                flagged = bool(r["findings"]) and step >= 3
                miss = A["miss_with_flags"] if flagged else A["miss_without_flags"]
                correct = rng.random() >= miss
        if g["escalate"]:
            minutes += A["min_escalation_extra"]     # 規則が見逃した引き継ぎ: 人が気づいて回す
    if misroute and not auto:
        minutes += A["min_reroute"]
    return {"minutes": minutes, "correct": correct, "auto": auto, "misroute": misroute,
            "missed_escalation": g["escalate"] and r["action"] not in ("escalate", "human")}


def run_step(step: int, world: dict | None = None, rng_seed: int = 7) -> dict:
    w = world or seed.world()
    tickets = w["tickets"]
    base_kb = kbmod.default_kb()
    ctx = pipeline.Ctx.make("mock_flaky", step=step, defenses=True, world=w, kb=base_kb)
    kb_with_new = None
    if step >= 6:
        extra = kbmod._parse_text(NEW_ARTICLE)
        kb_with_new = kbmod.KB(kbmod.load_articles(extra=[extra]))
    rng = random.Random(rng_seed)
    results, plans = {}, {}
    for t in tickets:
        channel = t["channel"]
        if channel == "chat" and step < 5:
            channel = "form"              # チャットが無い間は、同じ人がフォームから問い合わせる
        if kb_with_new is not None and t["week"] >= 6:
            ctx.kb = kb_with_new          # Step 6: 第 5 週の傾向報告から作った記事を、第 6 週から使う
        else:
            ctx.kb = base_kb
        r = pipeline.process(t, ctx, channel=channel)
        results[t["id"]] = r
        plans[t["id"]] = _work_plan(step, t, r, random.Random(f"{rng_seed}-{t['id']}"))

    # 人の仕事の列（平日 9〜18 時・担当者 A["operators"] 人・優先度 → 到着順）
    prio = {"urgent": 0, "high": 1, "normal": 2}
    items = []
    for t in tickets:
        p = plans[t["id"]]
        created = datetime.strptime(t["created_at"], "%Y-%m-%dT%H:%M")
        if p["auto"]:
            p["first_reply"] = created + timedelta(minutes=1)
        else:
            items.append((created, prio.get(results[t["id"]]["priority"], 2), t["id"], p["minutes"]))
        # 誤った返信は再問い合わせ（翌日に同じ人から）になることがある
        reopen_p = A["reopen_if_wrong"] if not p["correct"] else A["reopen_base"]
        p["reopen"] = rng.random() < reopen_p
        if p["reopen"]:
            items.append((created + timedelta(days=1), 2, t["id"] + "#2", A["min_manual"]))
    items.sort()
    free = [_next_open(items[0][0])] * A["operators"] if items else []
    heapq.heapify(free)
    waiting: list = []
    i = 0
    finish = {}
    busy_minutes = 0.0
    while i < len(items) or waiting:
        op_free = heapq.heappop(free)
        while i < len(items) and items[i][0] <= op_free:
            c, pr, tid, mins = items[i]
            heapq.heappush(waiting, (pr, c, tid, mins))
            i += 1
        if not waiting:
            heapq.heappush(free, max(op_free, items[i][0]))
            continue
        pr, c, tid, mins = heapq.heappop(waiting)
        start = max(op_free, c)
        end = _add_work(start, mins)
        finish[tid] = end
        busy_minutes += mins
        heapq.heappush(free, end)

    frt, within24, fcr, reopen, wrong, auto, esc, missed, misroute = [], 0, 0, 0, 0, 0, 0, 0, 0
    for t in tickets:
        p = plans[t["id"]]
        created = datetime.strptime(t["created_at"], "%Y-%m-%dT%H:%M")
        first = p.get("first_reply") or finish[t["id"]]
        hours = (first - created).total_seconds() / 3600
        frt.append(hours)
        within24 += hours <= 24
        fcr += (not p["reopen"]) and p["correct"]
        reopen += p["reopen"]
        wrong += not p["correct"]
        auto += p["auto"]
        esc += results[t["id"]]["action"] == "escalate"
        missed += p["missed_escalation"]
        misroute += p["misroute"]
    frt.sort()
    n = len(tickets)
    q = lambda x: round(frt[min(n - 1, int(x * n))], 1)
    ai_usd = sum(r["usage"]["cost_usd"] for r in results.values())
    op_hours = busy_minutes / 60
    yen = op_hours * A["yen_per_operator_hour"] + ai_usd * A["yen_per_usd"]
    by_week = {}
    for t in tickets:
        wk = t["week"]
        created = datetime.strptime(t["created_at"], "%Y-%m-%dT%H:%M")
        p = plans[t["id"]]
        first = p.get("first_reply") or finish[t["id"]]
        by_week.setdefault(wk, []).append((first - created).total_seconds() / 3600)
    return {
        "step": step, "title": flagmod.STEP_TITLES[step], "tickets": n,
        "auto_send": ev.rate(auto, n), "escalated": ev.rate(esc, n), "missed_escalation": missed,
        "misrouted": ev.rate(misroute, n),
        "frt_p50_h": q(0.5), "frt_p90_h": q(0.9), "within_24h": ev.rate(within24, n),
        "fcr": ev.rate(fcr, n), "reopen": ev.rate(reopen, n), "wrong_first_reply": ev.rate(wrong, n),
        "operator_hours": round(op_hours, 1), "ai_usd_estimated": round(ai_usd, 3),
        "yen_per_ticket": round(yen / n, 1),
        "frt_p90_by_week": {wk: round(sorted(v)[int(0.9 * len(v))], 1) for wk, v in sorted(by_week.items())},
    }


def to_markdown(rows: list[dict]) -> str:
    head = ("| Step | 内容 | 自動送信 | 引き継ぎ | 引き継ぎの見逃し | 初回返信 p50/p90 (時間) | 24 時間以内 | 一次解決 | 再問い合わせ | 誤った初回返信 | 担当者の時間 | 1 件の費用 (円) |\n"
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|\n")
    fmt = lambda r: f"{r['rate'] * 100:.1f}%（{r['k']}/{r['n']}）"
    body = "".join(
        f"| {r['step']} | {r['title']} | {fmt(r['auto_send'])} | {fmt(r['escalated'])} | {r['missed_escalation']} | "
        f"{r['frt_p50_h']} / {r['frt_p90_h']} | {fmt(r['within_24h'])} | {fmt(r['fcr'])} | {fmt(r['reopen'])} | "
        f"{fmt(r['wrong_first_reply'])} | {r['operator_hours']} 時間 | {r['yen_per_ticket']} |\n" for r in rows)
    note = ("\n🔴 仮定（ASSUME）のもとでの値。AI は mock（筋書き）、AI の費用は見積もり。仮定: "
            + "、".join(f"{k}={v}" for k, v in A.items()) + "\n")
    weekly = "\n初回返信 p90（時間）の週ごとの推移:\n\n| Step | " + " | ".join(f"第{w}週" for w in rows[0]["frt_p90_by_week"]) + " |\n|---|" + "---:|" * len(rows[0]["frt_p90_by_week"]) + "\n"
    weekly += "".join(f"| {r['step']} | " + " | ".join(str(v) for v in r["frt_p90_by_week"].values()) + " |\n" for r in rows)
    return head + body + note + weekly


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", nargs="*", type=int, default=list(range(7)))
    a = ap.parse_args()
    config.ensure_dirs()
    rows = []
    for s in a.steps:
        r = run_step(s)
        rows.append(r)
        print(f"Step {s} {r['title']}: 自動送信 {r['auto_send']['rate']} 初回返信 p50 {r['frt_p50_h']}h p90 {r['frt_p90_h']}h "
              f"一次解決 {r['fcr']['rate']} 誤った初回返信 {r['wrong_first_reply']['k']} 担当者 {r['operator_hours']}h 1 件 {r['yen_per_ticket']} 円")
    with open(os.path.join(config.DATA_DIR, "sim_report.json"), "w", encoding="utf-8") as f:
        json.dump({"assume": A, "rows": rows}, f, ensure_ascii=False, indent=1)
    with open(os.path.join(config.DATA_DIR, "sim_report.md"), "w", encoding="utf-8") as f:
        f.write("# 導入の道筋 Step 0〜6 の模擬実験\n\n" + to_markdown(rows))
    print("書き出し: data/sim_report.md / data/sim_report.json")


if __name__ == "__main__":
    main()
