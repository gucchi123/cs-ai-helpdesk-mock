"""本物のモデル（claude-opus-5-5・effort high）で 1 回だけ回す実行記録。既定は計画と費用の見積もりだけ（--dry-run）。

python labs/l13_live_run.py                       # 計画と見積もり（API を呼ばない）
python labs/l13_live_run.py --go --budget 1.5     # 本物で回す（キーは環境変数 ANTHROPIC_API_KEY。表示しない）
python labs/l13_live_run.py --replay              # 記録（labs/recorded/）を再生して同じ表を作る（キー不要）
python labs/l13_live_run.py --go --provider agent-sdk   # 講師の収録用: Claude Agent SDK（プランのログイン）で回す。記録の形は同じ
                                                        #   途中で止まっても、同じコマンドで回し直せば記録済みの呼び出しは飛ばす

回すもの（小さく）: 試験セットから層別に 24 件（分類＋下書き）・失敗の 9 シナリオ（守りあり）・判定役 24 件・記事の候補 1 件
2026-11-01 に 1 回回した（講師の収録: --provider agent-sdk・プランのログイン）。記録は labs/recorded/anthropic_runs.jsonl、結果は labs/out/l13_live_run.json。
再生は labs/out/l13_replay.json に書く（本物の記録を上書きしない）。--replay --detail で一件ずつ・失敗の返信・記録の中身を出す。
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _common import pct, save  # noqa: E402
from support import attacks, eval as ev, knowledge, llm, pipeline, prompts, seed  # noqa: E402
from support.kb import KB  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--go", action="store_true", help="本物の API を呼ぶ")
ap.add_argument("--replay", action="store_true", help="記録を再生する")
ap.add_argument("--n", type=int, default=24)
ap.add_argument("--budget", type=float, default=1.5)
ap.add_argument("--provider", default="anthropic", choices=["anthropic", "agent-sdk"], help="--go のときの呼び先")
ap.add_argument("--detail", action="store_true", help="--replay のとき、一件ずつ・失敗の 9 シナリオ・記録の中身も出す")
ap.add_argument("--reply", nargs="*", default=[], metavar="ID", help="--replay のとき、失敗のシナリオ（F1〜F9）か試験の番号（T-00066 など）の返信を全文で出す")
a = ap.parse_args()
if (a.detail or a.reply) and not a.replay:
    ap.error("--detail / --reply は --replay と一緒に使います（本物を呼び直さないため）")

w = seed.world()
es = seed.eval_set(w)
picked, seen = [], {}
for t in es:                                   # 分類ごとに 2〜3 件ずつ（層別）
    c = t["gold"]["category"]
    if seen.get(c, 0) < 3 and len(picked) < a.n:
        picked.append(t)
        seen[c] = seen.get(c, 0) + 1

# 見積もり: mock と同じ依頼文の長さから（出力は本物の方が長いので 3 倍で見る）
mock = llm.get("mock")
calls, tin, tout = 0, 0, 0
ctx = pipeline.Ctx.make(mock, step=4, world=w)
for t in picked:
    r = pipeline.process(t, ctx)
    calls += r["usage"]["calls"] + 1          # ＋判定役
    tin += r["usage"]["in"] * 2
    tout += r["usage"]["out"] * 2 * 3
calls += 9 * 2 + 1
tin += 9 * 2 * 1500 + 3000
tout += 9 * 2 * 400 + 800
est = llm.cost_usd(llm.DEFAULT_MODEL, tin, tout)
print(f"計画: 試験 {len(picked)} 件＋失敗 9 シナリオ＋判定 {len(picked)} 件＋記事の候補 1 件 ＝ 呼び出し 約 {calls} 回")
print(f"見積もり: 入力 約 {tin:,} / 出力 約 {tout:,} トークン → 約 {est:.2f} USD（{llm.DEFAULT_MODEL}・effort {llm.DEFAULT_EFFORT}、思考のトークンで上下する）")
if not (a.go or a.replay):
    print("（--dry-run: API は呼んでいません。回すときは --go。予算の上限は --budget）")
    sys.exit(0)

llm.BUDGET_USD = a.budget
prov = llm.get("recorded") if a.replay else llm.get(a.provider, tag="l13")
t0 = time.time()
ctx = pipeline.Ctx.make(prov, step=4, world=w)
rs = [pipeline.process(t, ctx) for t in picked]
m = ev.evaluate(rs, picked)
ja = ev.judge_agreement(rs, picked, prov)
fails, fail_full = [], []
for sc in attacks.scenarios(w):
    c2 = pipeline.Ctx.make(prov, step=5, world=w)
    c2.last_customer = w["customers"][8]
    r = pipeline.process(sc["ticket"], c2)
    fails.append({"sid": sc["sid"], "action": r["action"], "stopped_by": sorted({*r["escalation"]["reasons"], *[f["kind"] for f in r["findings"]]}),
                  "reply": (r.get("draft") or {}).get("reply", "")[:300]})
    fail_full.append((sc, r))
allr = {t["id"]: pipeline.process(t, pipeline.Ctx.make("mock", step=4, world=w)) for t in w["tickets"]}
cand = knowledge.candidates(w["tickets"], allr, KB(), prov, max_items=1)
spent = sum(r["usage"]["cost_usd"] for r in rs)
print(f"\n分類 {pct(m['classification'])} / 自動送信 {pct(m['auto_send'])} / 送ったうち誤り {pct(m['sent_wrong'])}")
kap = "—（不合格が 0 件で出せない）" if ja["kappa"] is None else ja["kappa"]
print(f"判定役の一致 κ={kap} TPR {pct(ja['tpr'])} TNR {pct(ja['tnr'])}")
for f in fails:
    print(f"  {f['sid']} {f['action']} 止めた層 {f['stopped_by']}")
print(f"秒 {time.time() - t0:.1f}・試験ぶんの費用 {spent:.3f} USD（全体は _api_cost_ledger.jsonl）")

if a.detail:   # 記録の再生だけ（呼び直さない）。数字はすべて上で出したものと同じ記録から
    from collections import Counter

    from support import escalation
    import unicodedata
    ACT = {"auto_send": "送る", "approve": "承認", "escalate": "引き継ぎ"}
    KIND = {"grounding": "根拠の引用が無い文", "promise": "約束", "tone": "口調", "pii": "個人情報", "internal": "社内記事", "length": "長さ"}

    def pad(s, w):   # 全角を 2 桁と数えて揃える
        return s + " " * max(0, w - sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in s))
    print("\n== 一件ずつ（試験 24 件・本物のモデルの記録を再生） ==")
    print("  " + pad("番号", 9) + pad("分類（正解→AI）", 28) + pad("行き先", 10) + pad("理由", 34) + pad("採点", 6) + "判定役")
    for t, r in zip(picked, rs):
        g, d = t["gold"], r.get("draft") or {}
        if r["action"] == "escalate":
            why = "・".join(escalation.REASON_LABEL.get(x, x) for x in r["escalation"]["reasons"])
        elif r["findings"]:
            why = "・".join(f"{KIND.get(k, k)} ×{n}" for k, n in Counter(f["kind"] for f in r["findings"]).items())
        elif r["action"] == "auto_send":
            why = "自動送信の条件をすべて満たした"
        else:
            why = "人の承認の境界"
        sc = ev.reference_score(d.get("reply", ""), g)["score"]
        jp = prov.run("judge", {"ticket": r["masked_text"], "reply": d.get("reply", ""),
                                "chunks": [{"cid": c["cid"], "text": c["text"]} for c in r["retrieval"]]}).get("pass")
        cls = f"{g['category']}→{r['classification'].get('category')}"
        print("  " + pad(t["id"], 9) + pad(cls, 28) + pad(ACT[r["action"]], 10) + pad(why[:16], 34) + pad(str(sc), 6)
              + ("合格" if jp else "不合格"))
    print("\n== 判定役と正解に照らした採点の食い違い ==")
    for x in ja["disagreements"] or [{"id": "（なし）"}]:
        print(f"  {x['id']}" + (f"  正解 {'合格' if x['ref'] else '不合格'}（{x['ref_score']} 点・違反 {x['violations']}）"
                                 f" / 判定役 {'合格' if x['judge'] else '不合格'}" if "ref" in x else ""))
    print("\n== 失敗の 9 シナリオ（守りあり・本物のモデル） と 筋書きの AI（守りなし） ==")
    naive = {x["sid"]: x["naive"] for x in attacks.run_matrix(w)}       # mock_naive（筋書きで失敗する AI）。キー不要
    for (sc, r), f in zip(fail_full, fails):
        why = "AI が人の確認を求めた" if r["why"].startswith("AI が人") else ("・".join(f["stopped_by"]) or "—")
        ref = ev.reference_score((r.get("draft") or {}).get("reply", ""), sc["ticket"]["gold"])
        nv = naive[sc["sid"]]
        print(f"  {sc['sid']} {sc['title'][:30]}")
        print(f"     本物 {ACT.get(f['action'], f['action'])}（{why}）・送っていたら {ref['score']} 点・違反 {len(ref['violations'])}"
              f"  ｜ 筋書き・守りなし {ACT.get(nv['action'], nv['action'])}・被害 {len(nv['problems'])} 件")
    print("\n== 記事の候補（公開は人） ==")
    for c in cand:
        print(f"  {c['title']}\n  状態 {c['status']}・確かめてほしい点 {len(c['review_points'])} 件・いちばん近い既存の節 {c['closest_existing']}")
    rows = list(prov.rows.values())
    by = Counter(r["task"] for r in rows)
    tin = sum(int(r["meta"].get("in", 0)) for r in rows)
    tout = sum(int(r["meta"].get("out", 0)) for r in rows)
    usd = sum(float(r["meta"].get("cost_usd", 0)) for r in rows)
    provs = sorted({r["meta"].get("provider", "?") for r in rows})
    billed = any(r["meta"].get("billed", True) for r in rows)
    print(f"\n== 記録の中身（{os.path.relpath(prov.path)}） ==")
    print(f"  呼び出し {len(rows)} 回（分類 {by['classify']}・下書き {by['draft']}・判定 {by['judge']}・記事 {by['kb_article']}）"
          f"／計画の {calls} 回との差は、同じ文面の依頼を記録から使い回した分")
    print(f"  入力 {tin:,} / 出力 {tout:,} トークン → API の単価で換算 約 {usd:.2f} USD（見積もり 約 {est:.2f} USD）")
    print(f"  呼び先 {', '.join(provs)}・請求 {'あり' if billed else 'なし（プランのログインで回した記録。金額は換算）'}"
          f"・モデル {llm.DEFAULT_MODEL}・effort {llm.DEFAULT_EFFORT}")

for sid in a.reply:   # 返信を全文で（記録の再生）
    for t, r in zip(picked, rs):
        if t["id"] == sid.upper():
            ref = ev.reference_score((r.get("draft") or {}).get("reply", ""), t["gold"])
            print(f"\n== 試験 {t['id']}（正解の分類 {t['gold']['category']}） ==\nお客様の文: {r['masked_text']}")
            print(f"行き先: {r['action']}・正解に照らした採点 {ref['score']} 点（足りない {ref['missing']}・違反 {ref['violations']}）")
            print(f"-- 本物のモデルの返信 --\n{(r.get('draft') or {}).get('reply', '')}")
    for sc, r in fail_full:
        if sc["sid"] == sid.upper():
            print(f"\n== {sc['sid']} {sc['title']} ==\nお客様の文: {sc['ticket']['body']}")
            print(f"行き先: {r['action']}（{r['why'][:60]}）\n-- 本物のモデルの返信 --\n{(r.get('draft') or {}).get('reply', '')}")

# 🔴 2026-11-13: 再生（--replay）は別のファイルに書く。前は本物の実行の記録 l13_live_run.json を上書きしていた（秒・呼び先が再生の値になる）
save("l13_replay.json" if a.replay else "l13_live_run.json", "anthropic",
     {"provider": prov.name, "model": llm.DEFAULT_MODEL, "effort": llm.DEFAULT_EFFORT, "metrics": m, "judge": ja,
      "failures": fails, "candidate": cand, "seconds": round(time.time() - t0, 1)})
