# カスタマーサポート×AI ― 架空の窓口一式（講座の配布キット）

架空の家電通販「つゆはな家電」のお問い合わせ窓口を、手元だけで動かす一式です。
8 週間ぶん・1,349 件の問い合わせの流れを AI が受け、**分類 → 根拠つきの下書き → 送る前の検査 → 送る / 人の承認へ / 人に引き継ぐ** を決めます。
外部のサービスにはつながりません。API キーが無くても全部動きます（AI は mock）。

## 1. 動かす

```
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python run_all.py            # 通販サイト http://127.0.0.1:8800/ ・窓口 http://127.0.0.1:8801/
.venv\Scripts\python -m pytest             # テスト（キー不要）
.venv\Scripts\python tools\selfcheck.py    # きれいなコピーで全部を回す → SELFCHECK.md
```

窓口のダッシュボードで「次の件数を流す」を押すと、問い合わせが時刻の順に受信箱へ入ります。

## 2. 中身

| 部品 | 場所 | 講座 |
|---|---|---|
| 通販サイト（商品・ヘルプ・お問い合わせフォーム・右下のチャット） | `support/web/shop.py`・`templates/shop/` | P3・P10 |
| 窓口（ダッシュボード・受信箱・チケット・承認の列・傾向・記事の候補・設定・監査ログ） | `support/web/desk.py`・`templates/desk/` | P3〜P13 |
| ナレッジベース（記事 19・節 48。お客様向け / 社内向け） | `kb/*.md` | P5 |
| 架空のデータ（製品 6・お客様 160・注文 900・問い合わせ 1,349・試験セット 120） | `support/seed.py` | P3・P11 |
| 1 件の流れ（伏せ字 → 分類 → 検索 → 引き継ぎの規則 → 下書き → 検査 → 決定） | `support/pipeline.py` | P4〜P9 |
| 根拠の検査・口調と約束の検査・個人情報・注入の扱い・引き継ぎの規則 | `support/grounding.py`・`checks.py`・`pii.py`・`injection.py`・`escalation.py` | P5〜P9 |
| 評価（件数と区間・判定役の一致・κ） | `support/eval.py` | P11 |
| 失敗の対戦表（9 シナリオ × 守りなし / あり、層ごとの効き目） | `support/attacks.py` | P10 |
| 傾向・急増・グラフ・ナレッジの穴、記事の候補 | `support/analytics.py`・`knowledge.py` | P12 |
| 導入の道筋 Step 0〜6 の模擬実験（運用の数字・1 件の費用） | `support/sim.py`・`data/sim_report.md` | P13・P14 |
| AI の呼び先の切り替え（mock / mock_naive / mock_flaky / recorded / anthropic）と費用の台帳 | `support/llm.py`・`prompts.py`・`mock_brain.py` | P2・P14 |

## 3. AI の呼び先（provider）

| 名前 | キー | 中身 |
|---|---|---|
| `mock`（既定） | 不要 | 検索した節の文を並べて返信を作る筋書き。根拠が無ければ人に回す |
| `mock_naive` | 不要 | よくある失敗（規程の作り話・注入に従う・個人情報の書き写し・届く日の約束・クーポン・使い方を責める）を筋書きで起こす |
| `mock_flaky` | 不要 | 一定の割合（ASSUME の ai_flaky_rate）で mock_naive と同じ失敗をする。模擬実験で使う |
| `recorded` | 不要 | 本物のモデルで回した応答（`labs/recorded/`）を再生する |
| `anthropic` | 要 | 本物の Claude（既定 `claude-opus-5-5`・effort `high`）。応答は `labs/recorded/` にも保存される |
| `agent-sdk` | 不要（Claude のログイン） | 講師の収録用。本物の Claude を Claude Agent SDK で呼ぶ（`pip install claude-agent-sdk`）。記録の形は `anthropic` と同じで、provider 欄が `agent-sdk`。費用は API 換算の参考値（予算には数えない） |

切り替えは環境変数 `CSAI_PROVIDER`。🔴 **mock の数字は性能の証拠ではありません。** 「AI がこう答えた」と言えるのは `anthropic`（またはその記録の再生）だけです。

## 4. API キー（本物で回すとき）

- キーは各自で用意し、環境変数 `ANTHROPIC_API_KEY` に置きます。画面・ログ・記録には出しません（エラー文も伏せ字）。
- 費用は `_api_cost_ledger.jsonl` に 1 呼び出し 1 行。予算の上限は `LLM_BUDGET_USD`（既定 3 USD）。
- `labs/l13_live_run.py` は既定で計画と見積もりだけを出します（API を呼ばない）。
- 講師が 2026-11-01 に本物のモデルで 1 回回した記録が `labs/recorded/anthropic_runs.jsonl` にあります。`python labs/l13_live_run.py --replay --detail` でキー無しに同じ表を出せます（経緯と読み方は `labs/RUN_LOG.md`）。
- 自社の問い合わせを送る前に、社内の規程（個人情報・委託先）を確かめてください。

## 5. 約束

- 会社・人物・製品はすべて架空です。電話は `090-0000-xxxx`、メールは `@example.com`、住所は架空の市町村。カード番号のような値は作りません。
- 画像に文字・ロゴは入れません（`tests/test_hygiene.py` が確かめます）。
- 模擬実験の数字は `support/config.py` の ASSUME（仮定）のもとでの値です。現実の予測ではありません。
- 法的な助言ではありません。

## 6. 本物の窓口との違い（このキットが省いたもの）

ログインと権限（画面の役割は切り替えだけ）、メールの送受信、電話、多言語、本番の検索（ベクトル DB など）、監視と障害対応、個人情報の保管期間と削除、委託先の管理。

## ライセンス

MIT License (`LICENSE`)。
