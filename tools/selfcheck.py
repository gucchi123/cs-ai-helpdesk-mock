"""きれいなコピーで全部を回して SELFCHECK.md を書く（キー不要・外部につながらない）。

python tools/selfcheck.py
1. キットを一時フォルダにコピー（.venv・data/runtime・記録・台帳は除く）
2. pytest
3. ラボ l01〜l12（mock）と l13 の見積もり（API は呼ばない）
4. run_all.py --check（2 つのサービスが起動して /health が 200）
"""
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP = {".venv", "__pycache__", "runtime", ".pytest_cache", "out", "out_mock", "recorded"}
LABS = ["l01_tour", "l02_first_ticket", "l03_classify_route", "l04_rag_citations", "l05_escalation", "l06_checks_pii",
        "l07_failures", "l08_eval", "l09_trends_graph", "l10_knowledge", "l11_cost_per_ticket", "l12_journey",
        "worked_examples", "l13_live_run"]


def main():
    py = sys.executable
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "CSAI_PROVIDER": "mock"}
    env.pop("ANTHROPIC_API_KEY", None)
    tmp = tempfile.mkdtemp(prefix="csai_selfcheck_")
    dst = os.path.join(tmp, "kit")
    shutil.copytree(ROOT, dst, ignore=lambda d, names: [n for n in names if n in SKIP or n.endswith(".jsonl") or n.endswith(".sqlite")])
    rows = []

    def run(label, cmd, timeout=600):
        t0 = time.time()
        p = subprocess.run(cmd, cwd=dst, env=env, capture_output=True, text=True, encoding="utf-8", timeout=timeout)
        ok = p.returncode == 0
        tail = (p.stdout or p.stderr).strip().splitlines()[-1:] or [""]
        rows.append((label, ok, round(time.time() - t0, 1), tail[0][:120]))
        print(("OK " if ok else "NG ") + label, tail[0][:120])
        return ok

    run("pytest", [py, "-m", "pytest", "-q"])
    for lab in LABS:
        run(f"labs/{lab}.py", [py, f"labs/{lab}.py"])
    run("run_all.py --check", [py, "run_all.py", "--check", "--reset"], timeout=120)
    allok = all(r[1] for r in rows)
    md = [f"# 自己検査（{datetime.now():%Y-%m-%d %H:%M}）", "",
          f"きれいなコピー（{tmp}）で実行。API キーなし・AI は mock。結果: {'すべて OK' if allok else '失敗あり'}", "",
          "| 項目 | 結果 | 秒 | 最後の行 |", "|---|---|---:|---|"]
    md += [f"| {a} | {'OK' if b else 'NG'} | {c} | {d.replace('|', '/')} |" for a, b, c, d in rows]
    open(os.path.join(ROOT, "SELFCHECK.md"), "w", encoding="utf-8").write("\n".join(md) + "\n")
    shutil.rmtree(tmp, ignore_errors=True)
    print("SELFCHECK.md を書きました")
    return 0 if allok else 1


if __name__ == "__main__":
    sys.exit(main())
