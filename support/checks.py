"""送る前の口調・規程の検査（ルールで決まるものはルールで判定する）。

kind:
- promise : 規程に無い約束（返金・クーポン・届く日・特別扱い）。AI の下書きでは常に止める（人の承認へ）
- tone    : 使い方を責める・否定する・謝りすぎ
- pii     : 個人情報らしい値（pii.leak_check の結果をここに合流させる）
- internal: お客様向けの返信に社内向けの記事を引用している
- length  : 長すぎる
"""
from __future__ import annotations

import re

PROMISE = [
    (r"必ず", "「必ず」と言い切っている"),
    (r"確約", "確約している"),
    (r"絶対に", "「絶対に」と言い切っている"),
    (r"(全額)?返金(いた)?します", "返金を約束している（返金の判断は人）"),
    (r"クーポンをお送り", "クーポンを約束している（お詫びの判断は責任者だけ）"),
    (r"補償いたします", "補償を約束している"),
    (r"明日(お届け|届きます)", "届く日を約束している"),
    (r"特別に", "規程外の特別扱いを約束している"),
]
TONE = [
    (r"取扱説明書をよくお読み", "お客様の使い方を責める書き方"),
    (r"正しくお使いください", "お客様の使い方を責める書き方"),
    (r"お客様の(使い方|操作)(が|に)(悪|問題|誤)", "お客様の使い方を責める書き方"),
    (r"そのようなことはありません", "お客様の言葉を否定している"),
]


def run(reply: str, channel: str = "mail", cited: list[str] | None = None, kb=None) -> list[dict]:
    out = []
    for rx, msg in PROMISE:
        if re.search(rx, reply):
            out.append({"kind": "promise", "msg": msg})
    for rx, msg in TONE:
        if re.search(rx, reply):
            out.append({"kind": "tone", "msg": msg})
    if reply.count("申し訳") >= 2:
        out.append({"kind": "tone", "msg": "謝罪が 2 回以上ある"})
    if kb is not None and cited:
        internal = [c for c in cited if c in kb.by_cid and not kb.by_cid[c].public]
        if internal:
            out.append({"kind": "internal", "msg": f"社内向けの記事を引用している: {', '.join(internal)}"})
    if len(reply) > 700:
        out.append({"kind": "length", "msg": f"長すぎる（{len(reply)} 文字）"})
    return out
