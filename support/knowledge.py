"""解決した問い合わせを、ナレッジベースの記事の「候補」にする（公開は人が決める）。

流れ: 記事につながらない症状（ナレッジの穴）を見つける → 同じ症状の解決記録を集める（個人情報は伏せ字）
     → AI が下書き → 既存記事との重なりを確かめる → 個人情報が無いかを確かめる → 「要確認」で候補の列へ
🔴 候補は自動で公開しない。原因の書き方（調査中の不具合など）は品質保証・法務の確認が要る。
"""
from __future__ import annotations

from support import analytics, pii
from support.kb import KB


def candidates(tickets: list[dict], results: dict[str, dict], kb: KB, provider, min_cases: int = 5,
               max_items: int = 3) -> list[dict]:
    rep = analytics.report(tickets, results)
    # きっかけは 2 つ: 急増した「製品 × 症状」（既存の記事が条件に合っていないかもしれない）と、記事につながらない症状
    gaps = []
    for s in rep["spikes_product_symptom"]:
        sym = "症状:" + s["key"].split("×", 1)[1]
        if all(g["symptom"] != sym for g in gaps):
            gaps.append({"symptom": sym, "count": s["now"], "why": f"第{s['week']}週に急増", "product": s["key"].split("×", 1)[0]})
    for g in rep["graph"]["knowledge_gaps"]:
        if all(x["symptom"] != g["symptom"] for x in gaps):
            gaps.append({**g, "why": "記事につながらない"})
    rows = analytics.build_rows(tickets, results)
    by_id = {t["id"]: t for t in tickets}
    out = []
    for gap in gaps:
        sym = gap["symptom"].split(":", 1)[1]
        cases = [r for r in rows if r["symptom"] == sym and r["cause"] and r["product"] == gap.get("product", r["product"])]
        if len(cases) < min_cases or sym in ("出荷の遅れ", "定期便の価格改定", "発煙・異臭・発熱"):
            continue          # 遅延・価格はお知らせで、安全は品質保証が扱う（記事の候補にしない）
        products = sorted({r["product"] for r in cases})
        sample = [{"cause": r["cause"], "note": pii.mask(by_id[r["id"]]["body"])[0][:80]} for r in cases[:12]]
        draft = provider.run("kb_article", {"product": "・".join(products), "symptom": sym, "cases": sample})
        meta = draft.pop("_meta", {})
        overlap = kb.search(draft.get("title", "") + " " + draft.get("body", ""), k=1)
        leaks = pii.detect(draft.get("body", ""))
        out.append({"symptom": sym, "trigger": gap.get("why", ""), "cases": len(cases), "products": products, "title": draft.get("title"),
                    "body": draft.get("body"), "review_points": draft.get("review_points", []),
                    "closest_existing": overlap[0][0].cid if overlap else None,
                    "closest_score": overlap[0][1] if overlap else 0.0,
                    "pii_in_draft": [x[0] for x in leaks], "status": "要確認", "usage": meta})
        if len(out) >= max_items:
            break
    return out
