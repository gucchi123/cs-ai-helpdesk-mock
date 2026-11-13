"""根拠の検査: 返信の中の「規程らしい文」が、引用した節に本当に書いてあるかを確かめる。

考え方:
- 返信を文に分け、数字（30日・5,500円・3年…）か規程の語（返金・交換・無料・保証・クーポン・必ず…）を含む文を「規程らしい文」とする。
- 規程らしい文には [記事ID#節] の引用が要る。引用先の節に、その文の数字と規程の語がすべて出てくるかを確かめる。
- 出てこないものは unsupported（根拠なし）。🔴 これは「作り話の返金規程」を止めるための守り。

限界（講座で正直に言う）: 語が節に出てくれば通るので、「開封済みでも 30 日以内なら返品できる」のように、
節の語を使って条件だけを入れ替えた文は通り抜けることがある。返金などの言い回しは checks.py でも止めるが、この形の文は言い回しにも当たらない。最後に止めるのは自動送信の境界と人の承認。
"""
from __future__ import annotations

import re

CITE = re.compile(r"\[(KB-[A-Z0-9\-]+#\d+)\]")
NUM = re.compile(r"\d[\d,]*(?:営業日|日|年|か月|円|%|件|GHz|cm|秒|分)")
POLICY_WORDS = ["返金", "返品", "交換", "無料", "負担", "保証", "クーポン", "補償", "全額", "送料", "手数料",
                "必ず", "お届けします", "延長", "特別"]


def sentences(reply: str) -> list[str]:
    parts = re.split(r"(?<=。)", reply)
    return [p.strip() for p in parts if p.strip()]


def _norm(s: str) -> str:
    return s.replace(",", "").replace("，", "")


def check(reply: str, chunk_texts: dict[str, str]) -> dict:
    unsupported, details, n_policy = [], [], 0
    for s in sentences(reply):
        cites = CITE.findall(s)
        body = CITE.sub("", s)
        nums = NUM.findall(body)
        kws = [k for k in POLICY_WORDS if k in body]
        if not nums and not kws:
            continue
        n_policy += 1
        problems = []
        if not cites:
            problems.append("根拠の引用が無い")
        else:
            missing = [c for c in cites if c not in chunk_texts]
            if missing:
                problems.append(f"渡していない節を引用: {', '.join(missing)}")
            src = _norm("".join(chunk_texts.get(c, "") for c in cites))
            for n in nums:
                if _norm(n) not in src:
                    problems.append(f"数字「{n}」が引用先に無い")
            for k in kws:
                if k not in src:
                    problems.append(f"「{k}」が引用先に無い")
        details.append({"sentence": s, "cites": cites, "nums": nums, "words": kws, "problems": problems})
        if problems:
            unsupported.append(f"{body[:40]}… → {' / '.join(problems)}")
    return {"unsupported": unsupported, "policy_sentences": n_policy, "details": details}
