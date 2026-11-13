"""1 件の問い合わせを、受付から「送る / 承認へ / 引き継ぐ」まで、段階ごとに見せる。

python labs/l02_first_ticket.py                 # 既定: 送料の質問（自動送信まで行く例）
python labs/l02_first_ticket.py --ticket T-00215 # 任意のチケット
python labs/l02_first_ticket.py --text "スミカゼから焦げたにおいがします"
"""
from _common import args, banner, save
from support import pipeline, seed

a = args(__doc__, ticket="", text="送料無料になる条件を教えてください。連絡先は090-0000-1234です。", step="4")
banner("1 件を通す", a.provider)
w = seed.world()
if a.ticket:
    t = next(x for x in w["tickets"] if x["id"] == a.ticket)
else:
    t = dict(w["tickets"][0])
    t.update({"id": "DEMO-1", "body": a.text, "channel": "mail"})
ctx = pipeline.Ctx.make(a.provider, step=int(a.step), world=w)
r = pipeline.process(t, ctx)
print(f"\n① 受付: {t['id']}  {t['body']}")
print(f"② 伏せ字: {r['masked_text']}  （伏せた項目: {', '.join(r['pii_found']) or 'なし'}）")
c = r["classification"]
print(f"③ 分類: {c['category']}  自信 {c['confidence']}  {c.get('reason', '')}")
print("④ 検索（根拠の候補）:")
for x in r["retrieval"]:
    print(f"     {x['cid']}  点 {x['score']}  {x['title']} / {x['heading']}")
print(f"⑤ 引き継ぎの規則: {'・'.join(r['escalation']['labels']) or '当たりなし'}")
if r["draft"]:
    print(f"⑥ 下書き:\n     {r['draft']['reply']}")
    print(f"   引用: {r['draft']['citations']}")
print(f"⑦ 検査: {[f['msg'] for f in r['findings']] or '問題なし'}")
print(f"⑧ 決定: {r['action']}  → {r['why']}  振り分け先 {seed.QUEUES.get(r['queue'])}")
u = r["usage"]
print(f"   AI の呼び出し {u['calls']} 回・{u['cost_usd']:.5f} USD{'（見積もり）' if u['estimated'] else ''}・{u['seconds']} 秒")
save("l02_first_ticket.json", a.provider, r)
