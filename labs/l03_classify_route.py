"""分類と振り分けを、試験セット 120 件で測る（正解率・混同行列・間違えた例）。"""
from collections import Counter

from _common import args, banner, pct, save
from support import eval as ev, pipeline, seed

a = args(__doc__)
banner("分類と振り分け", a.provider)
w = seed.world()
es = seed.eval_set(w)[: a.limit] if a.limit else seed.eval_set(w)
ctx = pipeline.Ctx.make(a.provider, step=1, world=w)
rs = [pipeline.process(t, ctx) for t in es]
m = ev.evaluate(rs, es)
print(f"分類の正解率: {pct(m['classification'])}")
print(f"振り分けの正解率: {pct(m['routing'])}")
print("\n間違えた例:")
for r, t in zip(rs, es):
    if r["classification"]["category"] != t["gold"]["category"]:
        print(f"  {t['id']} 正解 {t['gold']['category']:<12} AI {r['classification']['category']:<12} 自信 {r['classification']['confidence']}  {t['body'][:50]}")
print("\n混同行列（行=正解、列=AI）:")
cats = list(seed.CATEGORY_QUEUE)
print("            " + " ".join(f"{c[:6]:>7}" for c in cats))
for g in cats:
    row = m["confusion"].get(g, {})
    print(f"{g[:11]:<12}" + " ".join(f"{row.get(c, 0):>7}" for c in cats))
low = [r for r in rs if r["classification"]["confidence"] < 0.5]
print(f"\n自信が 0.5 未満: {len(low)} 件（引き継ぎの規則 low_confidence で人に回る）")
save("l03_classify_route.json", a.provider, {"metrics": {k: m[k] for k in ("classification", "routing", "confusion")}})
