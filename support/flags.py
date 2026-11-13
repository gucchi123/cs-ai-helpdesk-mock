"""機能の切り替え: 導入の段階（Step 0〜6）と、守り（defenses）。

Step（経営判断の道筋。§ 設計ページの判断シートと対応）:
  0 現状把握         AI は使わない。数字を測るだけ
  1 分類と振り分け   AI が分類し、振り分け先を提案。返信は人が一から書く
  2 回答の下書き     ナレッジベースの根拠つきの下書き。全件、人が読んで承認する
  3 送る前の検査     根拠・口調・個人情報の検査が問題箇所に印を付ける（人の確認が速くなる）＋品質の関門
  4 限定の自動送信   配送・使い方・アカウントの、条件を満たすものだけ自動で送る
  5 お客様向けチャット 通販サイトのチャットで AI が答え、だめなら人に引き継ぐ
  6 ナレッジの循環   解決した記録から記事の候補を作り、週ごとの傾向を報告する
"""
from __future__ import annotations

DEFENSES = ("mask_pii", "spotlight", "detect_injection", "grounding", "checks", "escalation_rules",
            "approval_boundary", "isolate_context")

STEP_FEATURES = {
    0: dict(classify=False, draft=False, checks_ui=False, auto_send=False, chat=False, knowledge=False),
    1: dict(classify=True, draft=False, checks_ui=False, auto_send=False, chat=False, knowledge=False),
    2: dict(classify=True, draft=True, checks_ui=False, auto_send=False, chat=False, knowledge=False),
    3: dict(classify=True, draft=True, checks_ui=True, auto_send=False, chat=False, knowledge=False),
    4: dict(classify=True, draft=True, checks_ui=True, auto_send=True, chat=False, knowledge=False),
    5: dict(classify=True, draft=True, checks_ui=True, auto_send=True, chat=True, knowledge=False),
    6: dict(classify=True, draft=True, checks_ui=True, auto_send=True, chat=True, knowledge=True),
}
STEP_TITLES = {0: "現状把握", 1: "分類と振り分け", 2: "回答の下書き（全件承認）", 3: "送る前の検査と品質の関門",
               4: "限定の自動送信", 5: "お客様向けチャット", 6: "ナレッジの循環と傾向報告"}


def make(step: int = 4, defenses: bool | dict = True) -> dict:
    f = {"step": step, **STEP_FEATURES[step]}
    if isinstance(defenses, dict):
        f.update({d: bool(defenses.get(d, True)) for d in DEFENSES})
    else:
        f.update({d: bool(defenses) for d in DEFENSES})
    return f


def naive(step: int = 4) -> dict:
    """よくある「素朴な作り」: 守りを全部外し、自動送信は AI が needs_human=false と言えば送る。"""
    return make(step, defenses=False)
