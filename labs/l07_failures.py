"""9 つの失敗を、守りなし / ありで比べる。守りを 1 つ外す・1 つだけ入れる、で層ごとの効き目を見る。

python labs/l07_failures.py           # 対戦表
python labs/l07_failures.py --only F3 # 1 つだけ（返信の全文も出す）
"""
from _common import args, banner, save
from support import attacks, seed

a = args(__doc__, only="")
banner("失敗と守り（両側とも筋書きで失敗する AI。違いは守りの有無だけ）", a.provider)
w = seed.world()
rows = attacks.run_matrix(w)
if a.only:
    rows = [r for r in rows if r["sid"] == a.only]
for r in rows:
    n, d = r["naive"], r["designed"]
    print(f"\n{r['sid']} {r['title']}")
    print(f"  守りなし: {n['action']}  被害: {'・'.join(n['problems']) or 'なし'}")
    if a.only:
        print(f"    返信: {n['reply']}")
    print(f"  守りあり: {d['action']} → {d['queue']}  止めた層: {', '.join(d['stopped_by']) or '-'}")
    print(f"    理由: {d['why']}")
res = {"rows": rows}
if not a.only:
    res["remove_one"] = attacks.ablation(w)
    res["only_one"] = attacks.single_layer(w)
    print("\n守りを 1 つ外すと被害が出るシナリオ:", {k: v for k, v in res["remove_one"].items() if v} or "なし（ほかの層が止める）")
    print("守りを 1 つだけ入れたときに止められるシナリオ:")
    for k, v in res["only_one"].items():
        print(f"  {k:<18} {', '.join(v) or '-'}")
save("l07_failures.json", a.provider, res)
