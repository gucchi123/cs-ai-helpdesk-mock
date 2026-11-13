"""ナレッジベース（kb/*.md）の読み込み・分割・検索。

- 記事は「## 見出し」ごとの節（chunk）に分ける。引用の単位は節で、書き方は [KB-RET-01#2]（2 番目の節）。
- 検索は日本語の文字 2-gram の BM25。外部のサービスもベクトル DB も使わない（仕組みを見せるため）。
- public: false の記事は社内向け。お客様向けのチャットでは引用しない（下書きの判断には使う）。
"""
from __future__ import annotations

import math
import os
import re
from collections import Counter
from dataclasses import dataclass, field

from support import config


@dataclass
class Chunk:
    cid: str            # "KB-RET-01#2"
    article_id: str
    title: str
    heading: str
    text: str
    category: str
    public: bool
    product: str | None = None


@dataclass
class Article:
    id: str
    title: str
    category: str
    public: bool
    updated: str
    product: str | None
    body: str
    chunks: list[Chunk] = field(default_factory=list)


def _parse(path: str) -> Article:
    return _parse_text(open(path, encoding="utf-8").read(), path)


def _parse_text(raw: str, where: str = "(文字列)") -> Article:
    m = re.match(r"---\n(.*?)\n---\n(.*)", raw, re.S)
    if not m:
        raise ValueError(f"frontmatter がありません: {where}")
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    body = m.group(2).strip()
    art = Article(id=meta["id"], title=meta["title"], category=meta.get("category", ""),
                  public=meta.get("public", "true") == "true", updated=meta.get("updated", ""),
                  product=meta.get("product"), body=body)
    parts = re.split(r"^## ", body, flags=re.M)
    n = 0
    for p in parts:
        p = p.strip()
        if not p:
            continue
        heading, _, text = p.partition("\n")
        n += 1
        art.chunks.append(Chunk(cid=f"{art.id}#{n}", article_id=art.id, title=art.title, heading=heading.strip(),
                                text=text.strip(), category=art.category, public=art.public, product=art.product))
    return art


def load_articles(kb_dir: str | None = None, extra: list[Article] | None = None) -> list[Article]:
    d = kb_dir or config.KB_DIR
    arts = [_parse(os.path.join(d, f)) for f in sorted(os.listdir(d)) if f.endswith(".md")]
    return arts + list(extra or [])


def grams(s: str) -> list[str]:
    s = re.sub(r"[\s、。「」（）()・,.!?！？:：#\-]+", " ", s.lower())
    out = []
    for w in s.split():
        if len(w) == 1:
            out.append(w)
        out.extend(w[i:i + 2] for i in range(len(w) - 1))
    return out


class KB:
    def __init__(self, articles: list[Article] | None = None):
        self.articles = articles if articles is not None else load_articles()
        self.chunks = [c for a in self.articles for c in a.chunks]
        self.by_cid = {c.cid: c for c in self.chunks}
        self.by_article = {a.id: a for a in self.articles}
        self._docs = [Counter(grams(c.title + " " + c.heading + " " + c.text)) for c in self.chunks]
        self._len = [sum(d.values()) for d in self._docs]
        self._avg = sum(self._len) / max(1, len(self._len))
        df = Counter()
        for d in self._docs:
            df.update(d.keys())
        n = len(self._docs)
        self._idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def search(self, query: str, k: int = 4, public_only: bool = False, product: str | None = None, category: str | None = None,
               k1: float = 1.4, b: float = 0.75) -> list[tuple[Chunk, float]]:
        q = Counter(grams(query))
        scored = []
        for i, c in enumerate(self.chunks):
            if public_only and not c.public:
                continue
            d = self._docs[i]
            s = 0.0
            for t in q:
                if t in d:
                    tf = d[t]
                    s += self._idf.get(t, 0) * tf * (k1 + 1) / (tf + k1 * (1 - b + b * self._len[i] / self._avg))
            if product and c.product == product:
                s *= 1.3
            if category and (c.category == category or (category == "warranty" and c.category == "defect")):
                s *= 1.6       # 分類で検索を寄せる（分類が間違っていれば検索も外れる。だから分類の精度も測る）
            if s > 0:
                scored.append((c, round(s, 3)))
        scored.sort(key=lambda x: -x[1])
        return scored[:k]

    def text_of(self, cids: list[str]) -> str:
        return "\n".join(self.by_cid[c].text for c in cids if c in self.by_cid)


_default: KB | None = None


def default_kb() -> KB:
    global _default
    if _default is None:
        _default = KB()
    return _default
