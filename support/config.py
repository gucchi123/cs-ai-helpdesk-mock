"""キット全体の設定と、模擬実験の仮定（ASSUME）。

🔴 ASSUME の値は「仮定」です。現実の予測ではありません。講座では「仮定を変えると数字がどう動くか」を見る道具として使います。
"""
from __future__ import annotations

import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KB_DIR = os.path.join(ROOT, "kb")
DATA_DIR = os.path.join(ROOT, "data")
RUNTIME_DIR = os.path.join(DATA_DIR, "runtime")
LABS_OUT = os.path.join(ROOT, "labs", "out")
LABS_OUT_MOCK = os.path.join(ROOT, "labs", "out_mock")
RECORDED_DIR = os.path.join(ROOT, "labs", "recorded")

COMPANY = "つゆはな家電"            # 架空の会社（家電の通販と定期便）
SHOP_PORT = 8800                     # お客様向けの通販サイト＋チャット
DESK_PORT = 8801                     # 窓口（ヘルプデスク・承認の列・ダッシュボード）

# 規程の数字（kb/ が正。ここはテストで kb と食い違わないことを確かめるための写し）
POLICY = {
    "return_days_unopened": 8,
    "defect_days": 30,
    "maker_warranty_years": 1,
    "extended_total_years": 3,
    "extended_join_days": 30,
    "free_shipping_yen": 5500,
    "shipping_fee_yen": 660,
    "refund_needs_lead_yen": 20000,
    "subscription_change_days_before": 10,
}

# 人の承認の境界（Step ごとの flags で上書きされる）
AUTO_SEND_CATEGORIES = ("shipping", "howto", "account")   # 自動送信を許してよい分類の候補
AUTO_SEND_MIN_CONFIDENCE = 0.80
CHAT_EXTRA_CATEGORIES = ("subscription", "refund", "warranty")   # Step 5 のチャットで足す分類

# 模擬実験の仮定（ASSUME）
ASSUME = {
    "operators": 2,                    # 窓口の担当者数（平日 9〜18 時）
    "business_hours": (9, 18),         # 窓口の受付時間
    "min_manual": 14.0,                # 人が一から書く 1 件の分数
    "min_triage": 1.0,                 # 人が読んで振り分ける分数（Step 0）
    "min_reroute": 4.0,                # 振り分け違いを直す分数
    "min_review_draft": 5.0,           # AI の下書きを読んで直して送る分数
    "min_review_approve_only": 2.5,    # 直さずに承認だけする分数
    "min_escalation_extra": 15.0,      # 上位の担当に回したときに足される分数
    "yen_per_operator_hour": 2600,     # 担当者 1 時間の費用（人件費＋間接費の仮定）
    "reopen_if_wrong": 0.70,           # 誤った返信を送ったとき再問い合わせになる率
    "reopen_base": 0.06,               # 正しい返信でも再問い合わせになる率
    "ai_flaky_rate": 0.10,             # 模擬実験の AI が「よくある失敗」をする率（mock_flaky。本物の失敗率ではない）
    "miss_without_flags": 0.15,        # 印の無い下書きの誤りを承認者が見落とす率（自動化への過信）
    "miss_with_flags": 0.02,           # 検査が印を付けた誤りを見落とす率
    "yen_per_usd": 150,                # 為替の仮定
}

# AI の呼び先（provider）。mock / recorded / anthropic
PROVIDER = os.environ.get("CSAI_PROVIDER", "mock")


def ensure_dirs() -> None:
    for d in (DATA_DIR, RUNTIME_DIR, LABS_OUT, LABS_OUT_MOCK, RECORDED_DIR):
        os.makedirs(d, exist_ok=True)
