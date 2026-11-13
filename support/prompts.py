"""AI への依頼文（system と user）を作る。provider が mock でも同じ依頼文を作り、費用の見積もりと記録の鍵に使う。

🔴 依頼文は決まった順番・決まった書式で作る（同じ入力なら同じ文字列 → recorded の鍵が一致する）。
"""
from __future__ import annotations

import json

from support import injection

CATEGORY_HELP = {
    "shipping": "配送・送料・届かない・再配達",
    "return": "返品・交換（初期不良の交換を含む）",
    "refund": "返金の時期・方法・金額",
    "defect": "故障・不具合・調子が悪い（使い方ではなく症状）",
    "subscription": "フィルター定期便の変更・解約・価格",
    "warranty": "メーカー保証・延長保証・修理",
    "account": "ログイン・会員情報・支払い方法・領収書",
    "howto": "製品の使い方・機能の質問",
    "complaint": "対応への不満・苦情・責任者を求める・法的な言及",
    "safety": "発煙・異臭・発熱・火花・けがなど安全に関わるもの",
}

SYS_COMMON = ("あなたは架空の家電通販「つゆはな家電」のお問い合わせ窓口を手伝う AI です。"
              "出力は指定された JSON だけにしてください。")


def _j(x) -> str:
    return json.dumps(x, ensure_ascii=False, sort_keys=True)


def build(task: str, p: dict) -> tuple[str, str]:
    if task == "classify":
        cats = "\n".join(f"- {k}: {v}" for k, v in CATEGORY_HELP.items())
        system = (SYS_COMMON + "\nお問い合わせを次の分類の 1 つに振り分けます。\n" + cats + "\n"
                  + injection.GUARD_NOTE + "\n"
                  '出力: {"category": "<分類>", "confidence": <0〜1>, "reason": "<短い理由>"}')
        user = injection.wrap(p["text"])
        return system, user
    if task == "draft":
        system = (SYS_COMMON + "\nお客様への返信の下書きを書きます。担当者が読んで承認してから送ります。\n"
                  "決まり:\n"
                  "1. 規程・手順・数字は、下の <kb> にある節だけを根拠にする。節の内容を書いた文の末尾に [記事ID#節] を付ける。\n"
                  "2. <kb> に無いこと（返金・補償・クーポン・届く日の約束・規程の例外）は書かない。わからなければ「確認してご連絡します」と書き、needs_human を true にする。\n"
                  "3. 個人情報は [電話1] のような印になっている。印の中身を推測しない。返信に電話番号や住所を書き写さない。\n"
                  "4. お客様の使い方を責めない。謝罪は 1 回まで。次にすることを具体的に書く。\n"
                  "5. " + injection.GUARD_NOTE + "\n"
                  '出力: {"reply": "<返信の本文>", "citations": ["KB-...#n", ...], "needs_human": <true/false>, "note": "<担当者へのひとこと>"}')
        kb = "\n".join(f'<chunk id="{c["cid"]}" title="{c["title"]} / {c["heading"]}">{c["text"]}</chunk>' for c in p["chunks"])
        user = (f"<kb>\n{kb}\n</kb>\n<ticket category=\"{p['category']}\" channel=\"{p['channel']}\">\n"
                + injection.wrap(p["text"]) + "\n</ticket>")
        return system, user
    if task == "judge":
        system = (SYS_COMMON + "\n返信の下書きを、品質の基準で採点します（1〜5 の整数）。\n"
                  "- accuracy: 規程（<kb>）と食い違いがないか\n- grounding: 規程・数字に根拠の引用があるか\n"
                  "- policy: 規程に無い約束（返金・補償・日付）をしていないか\n- tone: 責めない・謝罪は 1 回・具体的か\n"
                  "- resolution: お客様が次に何をすればよいかわかるか\n"
                  '出力: {"scores": {"accuracy": n, "grounding": n, "policy": n, "tone": n, "resolution": n}, "pass": <true/false>, "reason": "<短い理由>"}\n'
                  "pass は、accuracy と policy がどちらも 4 以上で、ほかが 3 以上のときだけ true。")
        kb = "\n".join(f'<chunk id="{c["cid"]}">{c["text"]}</chunk>' for c in p["chunks"])
        user = f"<kb>\n{kb}\n</kb>\n" + injection.wrap(p["ticket"]) + f"\n<draft>\n{p['reply']}\n</draft>"
        return system, user
    if task == "kb_article":
        system = (SYS_COMMON + "\n解決した問い合わせの記録から、ナレッジベースの記事の下書きを書きます。担当者が確かめてから公開します。\n"
                  "個人情報・注文番号・お客様の名前は書かない。記録に無い原因や対処を足さない。\n"
                  '出力: {"title": "<題>", "body": "## 見出し\\n本文...", "review_points": ["<人が確かめること>", ...]}')
        user = _j({"product": p["product"], "symptom": p["symptom"], "cases": p["cases"]})
        return system, user
    if task == "insight":
        system = (SYS_COMMON + "\n問い合わせの週ごとの集計から、窓口の責任者向けの短い報告を書きます。数字は入力にあるものだけを使う。\n"
                  '出力: {"summary": "<3 文以内>", "actions": ["<提案>", ...]}')
        user = _j(p["stats"])
        return system, user
    raise ValueError(f"知らない task です: {task}")
