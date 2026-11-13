# ラボ

すべて `python labs/<名前>.py`。既定は mock（キー不要）。`--provider recorded|anthropic|agent-sdk` で切り替え（agent-sdk は講師の収録用）。`--limit` で件数を絞る。
書き出しは mock 系が `labs/out_mock/`、本物が `labs/out/`。

| ラボ | 中身 | 講座 |
|---|---|---|
| l01_tour | 会社とデータの全体 | P3 |
| l02_first_ticket | 1 件を段階ごとに通す | P1・P3 |
| l03_classify_route | 分類と振り分けの正解率・混同行列 | P4 |
| l04_rag_citations | 根拠つきの下書きと根拠の検査 | P5 |
| l05_escalation | 引き継ぎの再現率・適合率 | P7 |
| l06_checks_pii | 伏せ字と送る前の検査 | P6・P9 |
| l07_failures | 9 つの失敗 × 守りなし / あり・層ごとの効き目 | P10 |
| l08_eval | 品質の評価（正解に照らした採点・判定役の一致） | P11 |
| l09_trends_graph | 急増・ロット・グラフ・ナレッジの穴 | P12 |
| l10_knowledge | 記事の候補 | P12 |
| l11_cost_per_ticket | 1 件の費用（AI と人） | P14 |
| l12_journey | 導入の道筋 Step 0〜6（仮定を変えられる） | P13・P14 |
| l13_live_run | 本物のモデルで 1 回（既定は見積もりだけ） | P2・P11・P14 |
| worked_examples | 例題の答え | 各部の例題 |
