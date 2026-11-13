"""導入の道筋 Step 0〜6 の模擬実験。仮定を変えて回し直せる。

python labs/l12_journey.py
python labs/l12_journey.py --set operators=3 --set ai_flaky_rate=0.2   # 仮定を変える
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _common import banner, out_path  # noqa: E402
from support import config, sim  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--steps", nargs="*", type=int, default=list(range(7)))
ap.add_argument("--set", action="append", default=[], help="ASSUME の値を変える（例: operators=3）")
a = ap.parse_args()
for kv in a.set:
    k, v = kv.split("=", 1)
    old = config.ASSUME[k]
    config.ASSUME[k] = type(old)(v) if not isinstance(old, tuple) else old
banner("導入の道筋（仮定のもとでの模擬実験）", "mock_flaky")
rows = [sim.run_step(s) for s in a.steps]
print(sim.to_markdown(rows))
name = "l12_journey.json" if not a.set else "l12_journey_" + "_".join(x.replace("=", "-") for x in a.set) + ".json"
p = out_path(name, "mock")
json.dump({"assume": config.ASSUME, "rows": rows}, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"書き出し: {os.path.relpath(p, config.ROOT)}")
