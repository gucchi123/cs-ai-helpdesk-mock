"""問い合わせの記録から、傾向・急増・ナレッジの穴を見つける（小さなナレッジグラフつき）。

- 週ごと × 分類（AI の分類を使う。正解ラベルは使わない＝本番と同じ条件）
- 急増の検出: 前の週までの平均と比べ、比が 1.8 倍以上かつ 10 件以上を「急増」とする（ポアソンの z 値も出す）
- 症状の言い回しを決まった語彙で拾い、製品 × 症状 の組で急増を見る
- グラフ: 製品 → 症状 → 原因（解決の記録）/ 記事（引用）/ ロット。記事につながらない症状＝ナレッジの穴
🔴 急増は「原因」ではない。記録を読んで確かめるのは人の仕事（講座では毎回そう言う）。
"""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict

SYMPTOM_VOCAB = [
    ("途中で電源が切れる", r"途中で(電源が)?(切れ|止ま)|沸く前に勝手に切れ|勝手に切れ"),
    ("電源が入らない", r"電源が入りません|反応しません|動きません"),
    ("ランプが点滅", r"点滅"),
    ("充電台に戻らない", r"充電台に戻らな"),
    ("アプリにつながらない", r"アプリにつながりません"),
    ("お湯の出が悪い", r"お湯の出が悪"),
    ("加湿されない", r"加湿されていない"),
    ("異音", r"変な音|異音"),
    ("焼きむら", r"焼きむら"),
    ("発煙・異臭・発熱", r"煙|焦げ|熱くなっ|火花"),
    ("出荷の遅れ", r"発送の連絡がありません|出荷予定日を過ぎ|出荷準備中のまま"),
    ("定期便の価格改定", r"値上げ|価格改定|2,780円"),
]
LOT_RX = re.compile(r"K-\d{4}")


def symptom_of(text: str) -> str | None:
    for name, rx in SYMPTOM_VOCAB:
        if re.search(rx, text):
            return name
    return None


def weekly(rows: list[dict], key) -> dict[int, Counter]:
    out: dict[int, Counter] = defaultdict(Counter)
    for r in rows:
        k = key(r)
        if k:
            out[r["week"]][k] += 1
    return out


def spikes(wk: dict[int, Counter], min_count: int = 10, ratio: float = 1.8) -> list[dict]:
    weeks = sorted(wk)
    found = []
    for i, w in enumerate(weeks):
        if i < 2:
            continue
        for k, now in wk[w].items():
            prev = [wk[x].get(k, 0) for x in weeks[:i]]
            base = sum(prev) / len(prev)
            r = now / base if base > 0 else float("inf")
            z = (now - base) / math.sqrt(base) if base > 0 else float("inf")
            if now >= min_count and r >= ratio:
                found.append({"week": w, "key": k, "now": now, "baseline": round(base, 1),
                              "ratio": (round(r, 2) if r != float("inf") else None), "z": (round(z, 1) if z != float("inf") else None)})
    found.sort(key=lambda x: (x["week"], -x["now"]))
    return found


def build_rows(tickets: list[dict], results: dict[str, dict] | None = None) -> list[dict]:
    """分析用の行。results（pipeline の結果）があれば AI の分類と引用を使う。"""
    rows = []
    for t in tickets:
        r = (results or {}).get(t["id"]) or {}
        cat = (r.get("classification") or {}).get("category") or t["gold"]["category"]
        cites = (r.get("draft") or {}).get("citations") or []
        rows.append({"id": t["id"], "week": t["week"], "category": cat, "product": t["product"],
                     "symptom": symptom_of(t["body"]), "lot": (LOT_RX.findall(t["body"]) or [None])[0],
                     "cause": t["resolution"]["cause"], "articles": cites})
    return rows


def _answers(cid: str, symptom: str) -> bool:
    from support.kb import default_kb, grams
    c = default_kb().by_cid.get(cid)
    if c is None:
        return False
    return len(set(grams(symptom)) & set(grams(c.heading + c.text))) >= 2


def graph(rows: list[dict]) -> dict:
    """製品・症状・原因・記事・ロットの小さなグラフ（辺に件数）。"""
    edges = Counter()
    for r in rows:
        if not r["symptom"]:
            continue
        p, s = f"製品:{r['product']}", f"症状:{r['symptom']}"
        edges[(p, "HAS_SYMPTOM", s)] += 1
        if r["cause"]:
            edges[(s, "CAUSED_BY", f"原因:{r['cause']}")] += 1
        for a in r["articles"][:1]:
            if _answers(a, r["symptom"]):      # 引用した節が、その症状のことを本当に書いているときだけ
                edges[(s, "ANSWERED_BY", f"記事:{a.split('#')[0]}")] += 1
        if r["lot"]:
            edges[(s, "SEEN_IN_LOT", f"ロット:{r['lot']}")] += 1
    nodes = sorted({n for (a, _, b) in edges for n in (a, b)})
    sym_with_article = {a for (a, rel, _) in edges if rel == "ANSWERED_BY"}
    sym_counts = Counter()
    for (a, rel, b), n in edges.items():
        if rel == "HAS_SYMPTOM":
            sym_counts[b] += n
    gaps = [{"symptom": s, "count": n} for s, n in sym_counts.most_common() if s not in sym_with_article and n >= 5]
    return {"nodes": nodes, "edges": [{"src": a, "rel": rel, "dst": b, "count": n} for (a, rel, b), n in edges.most_common()],
            "knowledge_gaps": gaps}


def mermaid(g: dict, top: int = 18) -> str:
    lines = ["graph LR"]
    ids = {}
    for e in g["edges"][:top]:
        for n in (e["src"], e["dst"]):
            ids.setdefault(n, f"n{len(ids)}")
        lines.append(f'  {ids[e["src"]]}["{e["src"]}"] -- "{e["rel"]} {e["count"]}" --> {ids[e["dst"]]}["{e["dst"]}"]')
    return "\n".join(lines)


def report(tickets: list[dict], results: dict[str, dict] | None = None) -> dict:
    rows = build_rows(tickets, results)
    by_cat = weekly(rows, lambda r: r["category"])
    by_sym = weekly(rows, lambda r: r["symptom"])
    by_ps = weekly(rows, lambda r: f"{r['product']}×{r['symptom']}"
                   if r["symptom"] and r["category"] in ("defect", "safety", "return") else None)
    g = graph(rows)
    lots = Counter(r["lot"] for r in rows if r["lot"])
    return {"weeks": sorted(by_cat), "weekly_category": {w: dict(c) for w, c in sorted(by_cat.items())},
            "weekly_symptom": {w: dict(c) for w, c in sorted(by_sym.items())},
            "spikes_category": spikes(by_cat), "spikes_symptom": spikes(by_sym, min_count=8),
            "spikes_product_symptom": spikes(by_ps, min_count=8),
            "lots": dict(lots), "graph": g}
