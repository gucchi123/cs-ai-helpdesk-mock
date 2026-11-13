"""根拠つきの下書き（RAG）と、根拠の検査。引用した節に本当に書いてあるかを 1 文ずつ見る。"""
from _common import args, banner, save
from support import grounding, pipeline, seed
from support.kb import KB

a = args(__doc__, limit=6)
banner("根拠つきの下書き", a.provider)
w = seed.world()
kb = KB()
picks = [t for t in seed.eval_set(w) if t["gold"]["category"] in ("shipping", "return", "warranty", "subscription")][: a.limit]
ctx = pipeline.Ctx.make(a.provider, step=3, world=w)
out = []
for t in picks:
    r = pipeline.process(t, ctx)
    print(f"\n{t['id']} {t['body'][:60]}")
    for x in r["retrieval"]:
        print(f"   検索 {x['cid']} 点 {x['score']}")
    print(f"   下書き: {r['draft']['reply'][:200]}")
    for d in r["grounding"]["details"]:
        print(f"   文: {d['sentence'][:40]}… 引用 {d['cites']} 数字 {d['nums']} 語 {d['words']} → {'OK' if not d['problems'] else d['problems']}")
    out.append({"id": t["id"], "retrieval": r["retrieval"], "draft": r["draft"], "grounding": r["grounding"]})

print("\n--- 作り話の検査（筋書きの悪い下書き）---")
bad = "開封済みの商品でも、到着後30日以内であれば全額返金いたします[KB-RET-01#2]。"
g = grounding.check(bad, {c.cid: c.text for c in kb.chunks})
print(f"  {bad}\n  → {g['unsupported']}")
lim = "開封済みの商品も返品をお受けします[KB-RET-01#1]。"
print(f"  限界: {lim} → 根拠の検査は {grounding.check(lim, {c.cid: c.text for c in kb.chunks})['unsupported'] or '通ってしまう'}（この一文は約束の検査の言い回しにも当たらない。止めるのは自動送信の境界（返品は自動で送らない）と人の承認）")
save("l04_rag_citations.json", a.provider, {"items": out, "invented": g})
