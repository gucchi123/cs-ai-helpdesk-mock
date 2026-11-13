"""例題の答え（講座の「電卓で確かめる」回で使う値）を、ラボの出力から書き出す。

python labs/worked_examples.py   → labs/out_mock/worked_examples.md
"""
import os

from _common import ROOT
from support import config, eval as ev, pipeline, seed, sim

w = seed.world()
es = seed.eval_set(w)
ctx = pipeline.Ctx.make("mock", step=4, world=w)
rs = [pipeline.process(t, ctx) for t in es]
m = ev.evaluate(rs, es)
A = config.ASSUME
e = m["escalation"]
s0, s4 = sim.run_step(0), sim.run_step(4)
lines = ["# 例題の答え（mock・2026-10-23 の版。数字はラボの出力から）", ""]
lines += ["## 1. 0 件でも安全とは言えない（3 の法則）",
          f"- 自動送信 {m['auto_send']['k']} 件のうち規程外の約束 {m['sent_with_forbidden_promise']['k']} 件。Wilson の 95% 上限 {m['sent_with_forbidden_promise']['ci95'][1] * 100:.1f}%。3 の法則なら 3/{m['auto_send']['k']} = {3 / m['auto_send']['k'] * 100:.1f}%。", ""]
lines += ["## 2. 引き継ぎの再現率と適合率",
          f"- 引き継ぐべき {e['tp'] + e['fn']} 件・引き継いだ {e['tp'] + e['fp']} 件・両方 {e['tp']} 件 → 再現率 {e['tp']}/{e['tp'] + e['fn']} = {e['recall']['rate'] * 100:.1f}%、適合率 {e['tp']}/{e['tp'] + e['fp']} = {e['precision']['rate'] * 100:.1f}%", ""]
manual = A["min_manual"] / 60 * A["yen_per_operator_hour"]
review = A["min_review_draft"] / 60 * A["yen_per_operator_hour"]
lines += ["## 3. 1 件の人の費用（仮定のもと）",
          f"- 一から書く: {A['min_manual']} 分 × {A['yen_per_operator_hour']} 円/時 ÷ 60 = {manual:.1f} 円",
          f"- 下書きを直して送る: {A['min_review_draft']} 分 → {review:.1f} 円",
          f"- 引き継ぎ: ({A['min_manual']} + {A['min_escalation_extra']}) 分 → {(A['min_manual'] + A['min_escalation_extra']) / 60 * A['yen_per_operator_hour']:.1f} 円", ""]
lines += ["## 4. 導入の前後（模擬実験・仮定のもと）",
          f"- Step 0: 担当者 {s0['operator_hours']} 時間 → 1 件 {s0['yen_per_ticket']} 円・初回返信 p50 {s0['frt_p50_h']} 時間",
          f"- Step 4: 担当者 {s4['operator_hours']} 時間 → 1 件 {s4['yen_per_ticket']} 円・初回返信 p50 {s4['frt_p50_h']} 時間・自動送信 {s4['auto_send']['k']} 件", ""]
p = os.path.join(config.LABS_OUT_MOCK, "worked_examples.md")
open(p, "w", encoding="utf-8").write("\n".join(lines))
print("\n".join(lines))
print(f"書き出し: {os.path.relpath(p, ROOT)}")
