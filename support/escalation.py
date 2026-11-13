"""人への引き継ぎ（エスカレーション）の規則。

🔴 引き継ぐかどうかは AI の自信だけで決めない。決まった規則（コード）が先に見る。
規則は「見逃すと被害が大きいもの」から並べる。複数当たれば全部を理由に残す（あとで監査できるように）。
"""
from __future__ import annotations

import re

from support import config, injection

RULES = [
    # (理由のキー, 表示名, 正規表現, 振り分け先, 優先度)
    ("safety", "安全に関わる症状", r"煙|焦げ|火花|発火|熱くなっ|やけど|けが|異臭", "quality", "urgent"),
    ("legal", "法的な言及・外部機関", r"弁護士|法的|訴え|訴訟|消費生活センター|消費者センター", "lead", "high"),
    ("complaint", "強い不満・責任者の要求", r"責任者|ひどすぎ|どうしてくれる|何度問い合わせ|説明が間違", "lead", "high"),
    ("product_issue", "記事に無い製品の不具合の兆し", r"K-2609|水量は十分|たっぷり入れても|満水にしても", "tech", "high"),
]
REASON_LABEL = {
    "safety": "安全に関わる症状", "legal": "法的な言及・外部機関", "complaint": "強い不満・責任者の要求",
    "product_issue": "記事に無い製品の不具合の兆し", "refund_over_threshold": "返金額が承認の閾値以上",
    "injection": "AI への指示らしい文", "no_grounding": "根拠の記事が無い", "low_confidence": "分類の自信が低い",
    "repeat": "同じお客様から 3 回目以上", "refusal": "AI が回答を断った", "draft_flagged": "下書きの検査で問題",
}


def evaluate(text: str, cls: dict, ctx: dict) -> dict:
    """text: お客様の文（伏せ字の前でも後でもよい） / cls: 分類の結果 / ctx: order・contact_count・retrieval など"""
    reasons, queue, prio = [], None, "normal"
    for key, _label, rx, q, p in RULES:
        if re.search(rx, text):
            reasons.append(key)
            if queue is None:
                queue, prio = q, p
    order = ctx.get("order") or {}
    if cls.get("category") in ("refund", "return") and ("返金" in text) and order.get("total", 0) >= config.POLICY["refund_needs_lead_yen"]:
        reasons.append("refund_over_threshold")
        queue = queue or "lead"
        prio = "high" if prio == "normal" else prio
    if injection.detect(text):
        reasons.append("injection")
        queue = queue or "lead"
    if ctx.get("contact_count", 1) >= 3:
        reasons.append("repeat")
        queue = queue or "lead"
    if cls.get("confidence", 1.0) < 0.5:
        reasons.append("low_confidence")
    if not ctx.get("has_grounding", True):
        reasons.append("no_grounding")
    return {"escalate": bool(reasons), "reasons": reasons, "queue": queue, "priority": prio,
            "labels": [REASON_LABEL.get(r, r) for r in reasons]}
