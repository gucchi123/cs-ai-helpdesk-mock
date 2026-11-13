"""個人情報の伏せ字と、返信からの漏れの検査。

- AI に渡す前: 電話・メール・住所・生年月日を [電話1] のような印に置き換える。元の値は窓口のシステムだけが持つ（Vault）。
- 返信を送る前: 返信に「別のお客様の値」や「伏せ字の元の値」が入っていないかを確かめる。
🔴 正規表現は完全ではない（例: 住所の書き方はいくらでもある）。だから「入口で伏せる」と「出口で確かめる」の二重にする。
"""
from __future__ import annotations

import re

PATTERNS = [
    ("電話", re.compile(r"0\d{1,4}-\d{1,4}-\d{3,4}")),
    ("メール", re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")),
    ("住所", re.compile(r"[ぁ-んァ-ヶ一-龥ー]{1,8}[市町村]\s?[ぁ-んァ-ヶ一-龥ー]{1,8}\d{1,3}-\d{1,3}-\d{1,3}")),
    ("生年月日", re.compile(r"(19|20)\d{2}年\d{1,2}月\d{1,2}日生")),
]


class Vault:
    """伏せ字の元の値を持つ。AI 側には印だけを渡す。"""

    def __init__(self):
        self.values: dict[str, str] = {}

    def mask(self, text: str) -> str:
        counters: dict[str, int] = {}
        out = text
        for label, rx in PATTERNS:
            def rep(m):
                v = m.group(0)
                for k, old in self.values.items():
                    if old == v:
                        return k
                counters[label] = counters.get(label, 0) + 1
                key = f"[{label}{counters[label]}]"
                self.values[key] = v
                return key
            out = rx.sub(rep, out)
        return out

    def found(self) -> list[str]:
        return sorted({k.strip("[]").rstrip("0123456789") for k in self.values})


def mask(text: str) -> tuple[str, Vault]:
    v = Vault()
    return v.mask(text), v


def detect(text: str) -> list[tuple[str, str]]:
    return [(label, m.group(0)) for label, rx in PATTERNS for m in rx.finditer(text)]


def leak_check(reply: str, own: dict | None, others: list[dict]) -> list[str]:
    """返信に、問い合わせた本人以外の個人情報が入っていないか。本人の値でも、電話・住所の書き写しは指摘する。"""
    problems = []
    for c in others:
        if own and c.get("id") == own.get("id"):
            continue
        for k in ("phone", "email", "address"):
            v = c.get(k)
            if v and v in reply:
                problems.append(f"別のお客様の{ {'phone': '電話', 'email': 'メール', 'address': '住所'}[k] }が返信に入っている")
    if own:
        for k, lab in (("phone", "電話"), ("address", "住所")):
            v = own.get(k)
            if v and v in reply:
                problems.append(f"ご本人の{lab}を返信に書き写している（規程: 必要な範囲を超えて書き写さない）")
    for label, val in detect(reply):
        if own and val == own.get("email"):
            continue          # ご本人のメールアドレスへの言及は許す
        problems.append(f"返信に{label}らしい値がある")
    # 重複を除く
    seen, uniq = set(), []
    for p in problems:
        if p not in seen:
            uniq.append(p)
            seen.add(p)
    return uniq
