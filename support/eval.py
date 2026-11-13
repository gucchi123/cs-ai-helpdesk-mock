"""評価: 分類・振り分け・引き継ぎ・返信の品質・誤送信・個人情報・費用を、件数と区間つきで出す。

返信の品質は 2 つの物差しで測る（評価講座の方法を借りる）:
- 正解に照らした採点（reference）: 規程から決めた「入るべき事実」と「入ってはいけない約束」で 1〜5 点。
  🔴 これは「人の採点の代わり（proxy）」。講座の作成者が規程に照らして決めた正解で、実在の QA 担当の採点ではない。
- 判定役の採点（judge）: 正解を見ない判定役（mock はルール、本物は LLM）。reference とどれだけ一致するか（TPR・TNR・κ）を測る。
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict

from support import pii


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (round(max(0.0, c - h), 3), round(min(1.0, c + h), 3))


def rate(k: int, n: int) -> dict:
    lo, hi = wilson(k, n)
    return {"k": k, "n": n, "rate": round(k / n, 3) if n else None, "ci95": [lo, hi]}


def kappa(a: list[bool], b: list[bool]) -> float | None:
    n = len(a)
    if n == 0:
        return None
    po = sum(x == y for x, y in zip(a, b)) / n
    pa, pb = sum(a) / n, sum(b) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    return round((po - pe) / (1 - pe), 3) if pe < 1 else None


def reference_score(reply: str, gold: dict) -> dict:
    """正解に照らした採点（人の採点の代わり）。"""
    if not reply:
        return {"score": 1, "pass": False, "missing": gold["must_include"], "violations": []}
    missing = [m for m in gold["must_include"] if m not in reply]
    violations = [m for m in gold["must_not"] if m in reply]
    score = 5 - min(3, len(missing))
    if violations:
        score = 1
    return {"score": score, "pass": score >= 4, "missing": missing, "violations": violations}


def evaluate(results: list[dict], tickets: list[dict]) -> dict:
    byid = {t["id"]: t for t in tickets}
    n = len(results)
    cls_ok = 0
    conf = defaultdict(Counter)
    q_ok = 0
    tp = fp = fn = tn = 0
    misses, false_alarms = [], []
    drafts = ref_pass = 0
    sent = sent_bad = sent_violation = sent_pii = 0
    bad_examples = []
    actions = Counter()
    cost = 0.0
    for r in results:
        t = byid[r["ticket_id"]]
        g = t["gold"]
        actions[r["action"]] += 1
        cost += r["usage"]["cost_usd"]
        c = r["classification"].get("category")
        conf[g["category"]][c] += 1
        cls_ok += c == g["category"]
        q_ok += r["queue"] == g["queue"]
        esc = r["action"] == "escalate"
        if g["escalate"] and esc:
            tp += 1
        elif g["escalate"] and not esc:
            fn += 1
            misses.append({"id": t["id"], "reason": g["reason"], "action": r["action"], "text": t["body"][:60]})
        elif esc:
            fp += 1
            false_alarms.append({"id": t["id"], "why": r["why"][:60]})
        else:
            tn += 1
        reply = (r.get("draft") or {}).get("reply", "")
        if r.get("draft") is not None:
            drafts += 1
            ref = reference_score(reply, g)
            ref_pass += ref["pass"]
            r["_ref"] = ref
        if r["action"] == "auto_send":
            sent += 1
            ref = reference_score(reply, g)
            leaks = pii.detect(reply)
            bad = (not ref["pass"]) or g["escalate"]
            sent_bad += bad
            sent_violation += bool(ref["violations"])
            sent_pii += bool(leaks)
            if bad and len(bad_examples) < 8:
                bad_examples.append({"id": t["id"], "template": t["template"], "violations": ref["violations"],
                                     "missing": ref["missing"], "gold_escalate": g["escalate"], "reply": reply[:160]})
    return {
        "n": n, "actions": dict(actions),
        "classification": rate(cls_ok, n), "routing": rate(q_ok, n),
        "confusion": {k: dict(v) for k, v in conf.items()},
        "escalation": {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "recall": rate(tp, tp + fn), "precision": rate(tp, tp + fp),
                       "misses": misses[:10], "false_alarms": false_alarms[:10]},
        "draft_quality_reference": rate(ref_pass, drafts),
        "auto_send": rate(sent, n), "sent_wrong": rate(sent_bad, sent), "sent_with_forbidden_promise": rate(sent_violation, sent),
        "sent_with_pii": rate(sent_pii, sent), "bad_sent_examples": bad_examples,
        "cost_usd_total": round(cost, 4), "cost_usd_per_ticket": round(cost / n, 5) if n else 0,
    }


def judge_agreement(results: list[dict], tickets: list[dict], provider) -> dict:
    """判定役（provider.judge）と、正解に照らした採点（人の採点の代わり）の一致。"""
    byid = {t["id"]: t for t in tickets}
    ref, jud, rows = [], [], []
    for r in results:
        d = r.get("draft")
        if not d or not d.get("reply"):
            continue
        t = byid[r["ticket_id"]]
        rs = reference_score(d["reply"], t["gold"])
        j = provider.run("judge", {"ticket": r["masked_text"], "reply": d["reply"],
                                   "chunks": [{"cid": c["cid"], "text": c["text"]} for c in r["retrieval"]]})
        j.pop("_meta", None)
        ref.append(rs["pass"])
        jud.append(bool(j.get("pass")))
        rows.append({"id": t["id"], "ref": rs["pass"], "judge": bool(j.get("pass")), "ref_score": rs["score"],
                     "judge_reason": j.get("reason", "")[:80], "missing": rs["missing"], "violations": rs["violations"]})
    pos = [i for i, x in enumerate(ref) if x]
    neg = [i for i, x in enumerate(ref) if not x]
    tpr = rate(sum(jud[i] for i in pos), len(pos))
    tnr = rate(sum(not jud[i] for i in neg), len(neg))
    disagree = [x for x in rows if x["ref"] != x["judge"]]
    return {"n": len(rows), "tpr": tpr, "tnr": tnr, "kappa": kappa(ref, jud),
            "agreement": rate(sum(a == b for a, b in zip(ref, jud)), len(rows)), "disagreements": disagree[:12]}
