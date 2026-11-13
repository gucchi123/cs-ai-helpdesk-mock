"""ラボの共通部品: 引数・書き出し先・表示。

- --provider mock（既定・キー不要）/ mock_naive / recorded / anthropic
- 書き出し先: mock 系は labs/out_mock/、recorded・anthropic は labs/out/（本物の記録と混ぜない）
"""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from support import config  # noqa: E402


def args(desc: str, limit: int | None = None, **extra) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=desc)
    ap.add_argument("--provider", default=os.environ.get("CSAI_PROVIDER", "mock"))
    ap.add_argument("--limit", type=int, default=limit, help="件数を絞る（実演を 30〜120 秒に収める）")
    for k, v in extra.items():
        ap.add_argument(f"--{k}", default=v)
    return ap.parse_args()


def out_path(name: str, provider: str) -> str:
    config.ensure_dirs()
    d = config.LABS_OUT_MOCK if provider.startswith("mock") else config.LABS_OUT
    return os.path.join(d, name)


def save(name: str, provider: str, data) -> str:
    p = out_path(name, provider)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1, default=str)
    print(f"\n書き出し: {os.path.relpath(p, ROOT)}")
    return p


def pct(r: dict) -> str:
    if r.get("rate") is None:
        return "—"
    lo, hi = r["ci95"]
    return f"{r['rate'] * 100:.1f}%（{r['k']}/{r['n']}、95%区間 {lo * 100:.1f}〜{hi * 100:.1f}%）"


def banner(title: str, provider: str) -> None:
    print(f"== {title} ==  AI: {provider}" + ("（筋書きで動く mock。性能の証拠ではありません）" if provider.startswith("mock") else ""))
