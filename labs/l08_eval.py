"""返信の品質を測る（評価講座の方法を借りる）: 正解に照らした採点（人の採点の代わり）と、判定役の一致。

🔴 「正解に照らした採点」は講座の作成者が規程から決めた正解。実在の QA 担当の採点ではない（人の採点の代わり＝proxy）。
"""
from _common import args, banner, pct, save
from support import eval as ev, llm, pipeline, seed

a = args(__doc__)
banner("品質の評価", a.provider)
w = seed.world()
es = seed.eval_set(w)[: a.limit] if a.limit else seed.eval_set(w)
res = {}
for label, prov, d in (("守りあり", a.provider, True), ("素朴な作り", "mock_naive", None)):
    ctx = pipeline.Ctx.make(prov, step=4, defenses=d, world=w)
    rs = [pipeline.process(t, ctx) for t in es]
    m = ev.evaluate(rs, es)
    res[label] = m
    print(f"\n[{label}] AI: {prov}")
    print(f"  下書きの合格（正解に照らした採点）: {pct(m['draft_quality_reference'])}")
    print(f"  自動送信: {pct(m['auto_send'])}")
    print(f"  送ったうち誤り: {pct(m['sent_wrong'])}")
    print(f"  送ったうち規程外の約束: {pct(m['sent_with_forbidden_promise'])}")
    print(f"  送ったうち個人情報: {pct(m['sent_with_pii'])}")
    print(f"  引き継ぎの再現率: {pct(m['escalation']['recall'])}")
    print(f"  AI の費用: {m['cost_usd_per_ticket']:.5f} USD / 件")
    if label == "守りあり":
        ja = ev.judge_agreement(rs, es, llm.get(a.provider))
        res["judge"] = ja
        print(f"\n  判定役（{a.provider}）と正解に照らした採点の一致: {pct(ja['agreement'])}  κ={ja['kappa']}")
        print(f"   合格を合格と言えた（TPR）: {pct(ja['tpr'])}")
        print(f"   不合格を不合格と言えた（TNR）: {pct(ja['tnr'])}")
        for x in ja["disagreements"][:5]:
            print(f"   食い違い {x['id']} 正解 {'合格' if x['ref'] else '不合格'} 判定役 {'合格' if x['judge'] else '不合格'}  足りない: {x['missing']} 約束: {x['violations']}")
save("l08_eval.json", a.provider, res)
