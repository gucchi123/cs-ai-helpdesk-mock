"""個人情報の伏せ字と、送る前の検査（口調・約束・個人情報・社内記事）。"""
from _common import args, banner, save
from support import checks, pii, seed
from support.kb import KB

a = args(__doc__)
banner("伏せ字と送る前の検査", a.provider)
w = seed.world()
samples = [t for t in w["tickets"] if t["pii"]][: (a.limit or 4)]
out = {"mask": [], "checks": []}
for t in samples:
    m, v = pii.mask(t["body"])
    print(f"\n元: {t['body']}\nAI へ: {m}\n伏せた値は窓口だけが持つ: {list(v.values)}")
    out["mask"].append({"id": t["id"], "masked": m, "keys": list(v.values)})
kb = KB()
replies = [
    "お問い合わせいただき、ありがとうございます。マイページの「ご注文履歴」から確認できます[KB-SHP-02#1]。",
    "必ず明日お届けします。お詫びとして1,000円分のクーポンをお送りします。",
    "取扱説明書をよくお読みのうえ、正しくお使いください。",
    "申し訳ございません。大変申し訳ございません。",
    f"前のお客様のご住所は{w['customers'][1]['address']}です。",
]
print("\n--- 送る前の検査 ---")
for rep in replies:
    f = checks.run(rep, channel="mail") + [{"kind": "pii", "msg": m} for m in pii.leak_check(rep, w["customers"][0], w["customers"][:5])]
    print(f"  {rep[:40]}… → {[x['msg'] for x in f] or '問題なし'}")
    out["checks"].append({"reply": rep, "findings": f})
f = checks.run("担当者が判断します[KB-REF-02#2]。", channel="chat", cited=["KB-REF-02#2"], kb=kb)
print(f"  チャットで社内記事を引用 → {[x['msg'] for x in f]}")
save("l06_checks_pii.json", a.provider, out)
