"""人への引き継ぎ: 見逃し（再現率）と、回しすぎ（適合率）を測る。どの規則が当たったかも数える。"""
from collections import Counter

from _common import args, banner, pct, save
from support import eval as ev, pipeline, seed

a = args(__doc__)
banner("引き継ぎ", a.provider)
w = seed.world()
es = seed.eval_set(w)[: a.limit] if a.limit else seed.eval_set(w)
ctx = pipeline.Ctx.make(a.provider, step=4, world=w)
rs = [pipeline.process(t, ctx) for t in es]
m = ev.evaluate(rs, es)
e = m["escalation"]
print(f"引き継ぐべきもの {e['tp'] + e['fn']} 件のうち引き継いだ（再現率）: {pct(e['recall'])}")
print(f"引き継いだもののうち正しかった（適合率）: {pct(e['precision'])}")
print("当たった規則:", dict(Counter(x for r in rs for x in r["escalation"]["reasons"]).most_common()))
print("\n見逃し:")
for x in e["misses"]:
    print(f"  {x['id']} 理由 {x['reason']} → AI は {x['action']}  {x['text']}")
print("\n回しすぎ:")
for x in e["false_alarms"]:
    print(f"  {x['id']} {x['why']}")
print("\n決定の内訳:", m["actions"])
save("l05_escalation.json", a.provider, {"escalation": e, "actions": m["actions"]})
