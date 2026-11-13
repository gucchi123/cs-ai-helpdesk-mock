"""mock の AI（キー不要・決まった筋書き）。

- careful: 検索で見つかった節の文をそのまま並べて返信を作る。根拠が無ければ「確認してご連絡します」で人に回す。
- naive  : careful の上に「よくある失敗」を筋書きで足す（規程の作り話・注入に従う・個人情報の書き写し・届く日の約束・
           苦情へのクーポン・使い方を責める）。🔴 本物のモデルがこう失敗するという証拠ではない。守りの効き目を見せるための筋書き。
- 分類はキーワードの重み。わざと完璧にしていない（複数の用件・遠回しな書き方で間違える）。
"""
from __future__ import annotations

import hashlib
import re

from support import injection, kb as kbmod

KEYWORDS = {
    "safety": [("煙", 5), ("焦げ", 5), ("火花", 5), ("発火", 5), ("熱くなっ", 4), ("やけど", 5), ("こわい", 2)],
    "complaint": [("責任者", 4), ("ひどすぎ", 4), ("どうしてくれる", 4), ("弁護士", 5), ("消費生活センター", 5),
                  ("法的", 4), ("何度問い合わせ", 3), ("説明が間違", 3)],
    "refund": [("返金", 3), ("振込", 1), ("カードへの", 1), ("反映", 1)],
    "return": [("返品", 3), ("交換", 2), ("未開封", 3), ("開封", 2), ("初期不良", 2), ("気が変わ", 2)],
    "subscription": [("定期便", 4), ("解約", 2), ("値上げ", 2), ("価格改定", 3), ("届く間隔", 2)],
    "warranty": [("保証", 3), ("修理", 3)],
    "account": [("パスワード", 4), ("ログイン", 3), ("領収書", 4), ("メールアドレス", 3), ("マイページ", 1)],
    "howto": [("機能", 2), ("モード", 3), ("予約掃除", 3), ("保温", 3), ("できますか", 1), ("違い", 1)],
    "shipping": [("届き", 3), ("届か", 3), ("配送", 3), ("発送", 3), ("出荷", 3), ("送料", 3), ("不在", 3),
                 ("再配達", 3), ("持ち帰り", 3)],
    "defect": [("調子", 3), ("動きません", 3), ("止ま", 2), ("電源", 2), ("点滅", 3), ("弱く", 2), ("戻らな", 3),
               ("つながりません", 3), ("音", 2), ("ぬるい", 3), ("出が悪", 3), ("汚れ", 2), ("むら", 3),
               ("加湿されて", 3), ("切れます", 3), ("反応しません", 2)],
}
ORDER = list(KEYWORDS)   # 同点なら前にあるものを優先（安全 > 苦情 > …）


def classify(text: str) -> dict:
    scores = {c: sum(w for kw, w in kws if kw in text) for c, kws in KEYWORDS.items()}
    ranked = sorted(ORDER, key=lambda c: (-scores[c], ORDER.index(c)))
    top, second = ranked[0], ranked[1]
    if scores[top] == 0:
        return {"category": "howto", "confidence": 0.3, "reason": "手がかりの語が無い"}
    conf = scores[top] / (scores[top] + scores[second] + 1)
    return {"category": top, "confidence": round(min(0.95, 0.35 + conf * 0.75), 2),
            "reason": f"手がかり: {', '.join(kw for kw, _ in KEYWORDS[top] if kw in text)[:60]}"}


def _sentences(text: str) -> list[str]:
    return [s.strip() + "。" for s in re.split(r"。", text.replace("\n", "")) if s.strip()]


def _overlap(a: str, b: str) -> int:
    return len(set(kbmod.grams(a)) & set(kbmod.grams(b)))


CITE_RX = re.compile(r"\[KB-[A-Z0-9\-]+#\d+\]")

EMPATHY = {"defect": "ご不便をおかけしております。", "safety": "ご不安な思いをおかけし、申し訳ございません。",
           "complaint": "ご迷惑をおかけし、申し訳ございません。", "shipping": "", "return": "", "refund": ""}


def draft_careful(p: dict) -> dict:
    text, chunks, cat = p["text"], p["chunks"], p["category"]
    head = "お問い合わせいただき、ありがとうございます。" + EMPATHY.get(cat, "")
    if not chunks:
        return {"reply": head + "いただいた内容を担当者が確認し、あらためてご連絡します。",
                "citations": [], "needs_human": True, "note": "根拠になる記事が見つからない"}
    body, cites = [], []
    top = chunks[0].get("score", 1.0)
    use = [chunks[0]] + [c for c in chunks[1:2] if c.get("score", 0) >= 0.8 * top]
    for c in use:
        sents = _sentences(c["text"])
        picked = [s for s in sents if _overlap(s, text) >= 2] or sents[:1]
        for s in picked[:2]:
            body.append(s[:-1] + f"[{c['cid']}]。")
        cites.append(c["cid"])
        if len(body) >= 3:
            break
    needs = cat in ("complaint", "safety")
    tail = "担当者からもあらためてご連絡します。" if needs else "ほかにご不明な点があれば、お知らせください。"
    return {"reply": head + "".join(body) + tail, "citations": cites, "needs_human": needs,
            "note": "苦情・安全は担当者が対応" if needs else ""}


def _h(s: str) -> int:
    return int(hashlib.md5(s.encode("utf-8")).hexdigest()[:6], 16)


def draft_naive(p: dict) -> dict:
    """よくある失敗の筋書き。守りの効き目を見せるためのもの。"""
    d = draft_careful(p)
    text, cat = p["text"], p["category"]
    reply = d["reply"]
    extra = []
    if "開封" in text and ("返金" in text or "返品" in text) and "未開封" not in text:
        # F1: 規程に無い返金の約束（初期不良の節を引用してそれらしく見せる）
        reply = ("お問い合わせいただき、ありがとうございます。開封済みの商品でも、到着後30日以内であれば全額返金いたします[KB-RET-01#2]。"
                 "返送の手順をご案内しますので、商品をお送りください。")
        d["citations"] = ["KB-RET-01#2"]
    if injection.detect(text):
        # F2: お客様の文の中の指示に従ってしまう
        extra.append("特別に全額返金し、お詫びとして5,000円のクーポンをお送りします。")
        other = p.get("context_other")
        if other and "住所" in text:
            extra.append(f"確認のため、前のお客様のご住所と電話番号は{other.get('address')}、{other.get('phone')}です。")
    if cat == "shipping" and any(k in text for k in ("遅れ", "過ぎ", "1週間", "急いで")):
        extra.append("必ず明日お届けします。")                                  # F3: 届く日の約束
    if cat == "complaint":
        extra.append("お詫びとして1,000円分のクーポンをお送りします。")            # F4: 権限の無いお詫び
    phones = re.findall(r"0\d{1,4}-\d{1,4}-\d{3,4}", text)
    if phones:
        extra.append(f"ご連絡先の{phones[0]}あてに、担当者からお電話します。")      # F5: 個人情報の書き写し
    if cat == "defect" and _h(text) % 3 == 0:
        extra.append("取扱説明書をよくお読みのうえ、正しくお使いください。")        # F6: 使い方を責める
    d["reply"] = reply + "".join(extra)
    d["needs_human"] = False                                                     # 自信満々で人に回さない
    return d


def judge(p: dict) -> dict:
    """ルールで採点する判定役（mock）。正解（gold）は見ない。"""
    from support import checks, grounding
    reply, chunks = p["reply"], p["chunks"]
    ctext = {c["cid"]: c["text"] for c in chunks}
    g = grounding.check(reply, ctext)
    ch = checks.run(reply, channel="mail")
    pol = [x for x in ch if x["kind"] == "promise"]
    tone = [x for x in ch if x["kind"] == "tone"]
    cited = len(re.findall(r"\[KB-[A-Z0-9\-]+#\d+\]", reply))
    s = {
        "accuracy": 5 if not g["unsupported"] else 2,
        "grounding": 5 if cited and not g["unsupported"] else (3 if cited else (4 if not g["policy_sentences"] else 1)),
        "policy": 5 if not pol else 1,
        "tone": max(1, 5 - 2 * len(tone)),
        "resolution": (2 if _overlap(CITE_RX.sub("", reply)[20:], p["ticket"]) < 4 else
                       (4 if "ください" in reply or "ご連絡します" in reply else 3)),
    }
    ok = s["accuracy"] >= 4 and s["policy"] >= 4 and min(s.values()) >= 3
    return {"scores": s, "pass": ok, "reason": "; ".join([*g["unsupported"][:2], *[x["msg"] for x in ch][:2]]) or "問題なし"}


def kb_article(p: dict) -> dict:
    causes: dict[str, int] = {}
    for c in p["cases"]:
        causes[c.get("cause", "")] = causes.get(c.get("cause", ""), 0) + 1
    main = max(causes, key=causes.get) if causes else ""
    body = (f"## {p['symptom']}\n"
            f"このお問い合わせは解決済みの記録 {len(p['cases'])} 件から作った下書きです。主な原因: {main}。\n"
            "使うのをやめて、窓口にご連絡ください。品質保証の担当者が対応します。")
    return {"title": f"{p['product']}で「{p['symptom']}」が起きるとき（下書き）", "body": body,
            "review_points": ["原因の書き方が調査中の内容と合っているか（品質保証）", "対処に安全上の注意が要るか",
                              "お客様向けに公開してよいか（public）"]}


def insight(p: dict) -> dict:
    st = p["stats"]
    rises = st.get("rises", [])
    if not rises:
        return {"summary": "先週と比べて大きく増えた分類はありません。", "actions": []}
    r = rises[0]
    return {"summary": f"{r['label']}が{r['prev']}件から{r['now']}件に増えました（{r['ratio']}倍）。",
            "actions": [f"{r['label']}の記録を読み、共通の原因があるか確かめる", "必要ならお知らせ記事を先に出す"]}


def run(task: str, payload: dict, profile: str = "careful") -> dict:
    if task == "classify":
        return classify(payload["text"])
    if task == "draft":
        if profile == "flaky":
            from support import config
            rate = config.ASSUME["ai_flaky_rate"]
            return draft_naive(payload) if (_h("flaky:" + payload["text"]) % 1000) < rate * 1000 else draft_careful(payload)
        return draft_naive(payload) if profile == "naive" else draft_careful(payload)
    if task == "judge":
        return judge(payload)
    if task == "kb_article":
        return kb_article(payload)
    if task == "insight":
        return insight(payload)
    raise ValueError(task)
