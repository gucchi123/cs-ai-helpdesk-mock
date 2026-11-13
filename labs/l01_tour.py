"""架空の会社「つゆはな家電」と、8 週間の問い合わせの流れを眺める。"""
from collections import Counter

from _common import args, banner, save
from support import seed
from support.kb import KB

a = args(__doc__)
banner("会社とデータの全体", a.provider)
w = seed.world()
kb = KB()
t = w["tickets"]
print(f"製品 {len(w['products'])}・お客様 {len(w['customers'])}・注文 {len(w['orders'])}・問い合わせ {len(t)} 件（8 週間）")
print(f"ナレッジベース: 記事 {len(kb.articles)}（お客様向け {sum(x.public for x in kb.articles)}・社内向け {sum(not x.public for x in kb.articles)}）・節 {len(kb.chunks)}")
print("\n週ごとの件数:", dict(sorted(Counter(x["week"] for x in t).items())))
print("分類（正解ラベル）:", dict(Counter(x["gold"]["category"] for x in t).most_common()))
print("経路:", dict(Counter(x["channel"] for x in t)))
print(f"個人情報を書いてきた問い合わせ: {sum(bool(x['pii']) for x in t)} 件・AI への指示らしい文: {sum(x['injection'] for x in t)} 件")
print(f"人に引き継ぐのが正解: {sum(x['gold']['escalate'] for x in t)} 件", dict(Counter(x['gold']['reason'] for x in t if x['gold']['reason'])))
print("\n例（最初の 5 件）:")
for x in t[: (a.limit or 5)]:
    print(f"  {x['id']} {x['created_at']} [{x['channel']}] {x['body'][:60]}")
save("l01_tour.json", a.provider, {"tickets": len(t), "weeks": dict(Counter(x["week"] for x in t)),
                                   "gold_category": dict(Counter(x["gold"]["category"] for x in t))})
