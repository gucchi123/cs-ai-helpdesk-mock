"""解決した問い合わせから、ナレッジベースの記事の候補を作る（公開は人が決める）。"""
from _common import args, banner, save
from support import knowledge, pipeline, seed
from support.kb import KB

a = args(__doc__)
banner("ナレッジ化", a.provider)
w = seed.world()
ctx = pipeline.Ctx.make(a.provider, step=4, world=w)
rs = {t["id"]: pipeline.process(t, ctx) for t in w["tickets"]}
cands = knowledge.candidates(w["tickets"], rs, KB(), ctx.provider, max_items=a.limit or 3)
for c in cands:
    print(f"\n[{c['status']}] {c['title']}  （きっかけ: {c['trigger']}・元の記録 {c['cases']} 件）")
    print("  " + c["body"].replace("\n", "\n  "))
    print(f"  いちばん近い既存の節: {c['closest_existing']}（点 {c['closest_score']}）・下書きの個人情報: {c['pii_in_draft'] or 'なし'}")
    print("  人が確かめること: " + " / ".join(c["review_points"]))
save("l10_knowledge.json", a.provider, cands)
