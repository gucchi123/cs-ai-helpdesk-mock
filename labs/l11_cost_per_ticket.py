"""1 件あたりの費用: AI の費用（呼び出しごとのトークン）と、人の時間を足す。

🔴 mock の AI 費用は「本物で同じ長さの入出力だったら」の見積もり。本物の費用は labs/RUN_LOG.md の実測で置き換える。
"""
from collections import defaultdict

from _common import args, banner, save
from support import config, llm, pipeline, seed

a = args(__doc__, limit=40)
banner("1 件あたりの費用", a.provider)
w = seed.world()
ts = seed.eval_set(w)[: a.limit]
ctx = pipeline.Ctx.make(a.provider, step=4, world=w)
by_action = defaultdict(list)
for t in ts:
    r = pipeline.process(t, ctx)
    by_action[r["action"]].append(r["usage"])
A = config.ASSUME
minutes = {"auto_send": 0, "approve": A["min_review_draft"], "escalate": A["min_manual"] + A["min_escalation_extra"]}
print(f"モデル {llm.DEFAULT_MODEL} の単価 入力 {llm.price(llm.DEFAULT_MODEL)[0]} / 出力 {llm.price(llm.DEFAULT_MODEL)[1]} USD（100 万トークンあたり）")
print(f"仮定: 担当者 1 時間 {A['yen_per_operator_hour']} 円・1 USD = {A['yen_per_usd']} 円\n")
rows = []
for act, us in by_action.items():
    n = len(us)
    usd = sum(u["cost_usd"] for u in us) / n
    tin = sum(u["in"] for u in us) / n
    tout = sum(u["out"] for u in us) / n
    human = minutes.get(act, A["min_manual"]) / 60 * A["yen_per_operator_hour"]
    yen = usd * A["yen_per_usd"] + human
    rows.append({"action": act, "n": n, "in": round(tin), "out": round(tout), "ai_usd": round(usd, 5), "human_yen": round(human, 1), "total_yen": round(yen, 1)})
    print(f"{act:<10} {n:>3} 件  入力 {tin:>6.0f} / 出力 {tout:>5.0f} トークン  AI {usd:.5f} USD（{usd * A['yen_per_usd']:.1f} 円）＋ 人 {human:.0f} 円 ＝ {yen:.0f} 円")
manual = A["min_manual"] / 60 * A["yen_per_operator_hour"]
print(f"\n比べる: 人が一から書くと 1 件 {manual:.0f} 円（{A['min_manual']} 分）")
print("AI の費用は人の時間に比べて小さい。費用を決めるのは「人が何分かけるか」と「誤りの後始末」。")
save("l11_cost_per_ticket.json", a.provider, {"rows": rows, "assume": A, "estimated": a.provider.startswith("mock")})
