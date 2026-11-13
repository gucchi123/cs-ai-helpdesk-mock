"""一式を起動する: 通販サイト（:8800）と窓口（:8801）を別々のプロセスで。

python run_all.py            # 起動（Ctrl+C で止める）
python run_all.py --check    # 起動して /health を確かめて止める
python run_all.py --reset    # 窓口の記録（data/runtime/helpdesk.sqlite）と設定を消してから起動

AI の呼び先は環境変数 CSAI_PROVIDER（mock / recorded / anthropic）。既定は mock（キー不要）。
🔴 API キーは環境変数に置く。画面・ログ・記録には出さない。
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
from support import config  # noqa: E402

SERVICES = [("shop", "support.web.shop:app", config.SHOP_PORT), ("desk", "support.web.desk:app", config.DESK_PORT)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--reset", action="store_true")
    a = ap.parse_args()
    config.ensure_dirs()
    if a.reset:
        for f in ("helpdesk.sqlite", "settings.json"):
            p = os.path.join(config.RUNTIME_DIR, f)
            if os.path.exists(p):
                os.remove(p)
        print("窓口の記録と設定を消しました")
    procs = []
    for name, target, port in SERVICES:
        procs.append(subprocess.Popen([sys.executable, "-m", "uvicorn", target, "--host", "127.0.0.1", "--port", str(port),
                                       "--log-level", "warning"], cwd=ROOT))
        print(f"  {name:<5} http://127.0.0.1:{port}/")
    ok = True
    for name, _, port in SERVICES:
        for _ in range(60):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1) as r:
                    if r.status == 200:
                        break
            except OSError:
                time.sleep(0.25)
        else:
            ok = False
            print(f"  {name} が起動しませんでした")
    print("起動しました。通販サイト http://127.0.0.1:8800/ ・窓口 http://127.0.0.1:8801/" if ok else "起動に失敗しました")
    try:
        if a.check:
            return 0 if ok else 1
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        for p in procs:
            p.terminate()
        for p in procs:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()


if __name__ == "__main__":
    sys.exit(main() or 0)
