"""問い合わせの記録から、急増とナレッジの穴を見つける（製品・症状・原因・記事・ロットのグラフ）。"""
from _common import args, banner, save
from support import analytics, pipeline, seed

a = args(__doc__)
banner("傾向とグラフ", a.provider)
w = seed.world()
ts = w["tickets"][: a.limit] if a.limit else w["tickets"]
ctx = pipeline.Ctx.make(a.provider, step=4, world=w)
rs = {t["id"]: pipeline.process(t, ctx) for t in ts}
rep = analytics.report(ts, rs)
print("急増（症状）:")
for s in rep["spikes_symptom"]:
    print(f"  第{s['week']}週 {s['key']}: {s['now']} 件（それまでの平均 {s['baseline']}・{s['ratio'] or '新規'} 倍・z {s['z']}）")
print("急増（製品 × 症状）:")
for s in rep["spikes_product_symptom"]:
    print(f"  第{s['week']}週 {s['key']}: {s['now']} 件")
print("ロット:", rep["lots"])
print("\nナレッジの穴（記事につながらない症状）:")
for g in rep["graph"]["knowledge_gaps"]:
    print(f"  {g['symptom']} {g['count']} 件")
print("\nグラフ（Mermaid）:\n" + analytics.mermaid(rep["graph"], top=14))
save("l09_trends_graph.json", a.provider, rep)
