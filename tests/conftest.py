"""テストは API キー無しで回る（キーを外し、AI は mock）。窓口の記録と設定は一時フォルダに作る。"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ["CSAI_PROVIDER"] = "mock"


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    from support import llm
    monkeypatch.setattr(llm, "LEDGER", str(tmp_path / "ledger.jsonl"))
    monkeypatch.setattr(llm, "api_key", lambda: None)      # Windows のユーザー環境変数も読まない
    yield


@pytest.fixture
def world():
    from support import seed
    return seed.world()


@pytest.fixture
def eval_set(world):
    from support import seed
    return seed.eval_set(world)


@pytest.fixture
def web(tmp_path, monkeypatch):
    from support.web import common
    monkeypatch.setattr(common, "SETTINGS", str(tmp_path / "settings.json"))
    common.reset_state(str(tmp_path / "helpdesk.sqlite"))
    from fastapi.testclient import TestClient
    from support.web import desk, shop
    return {"desk": TestClient(desk.app), "shop": TestClient(shop.app), "state": common.state(), "common": common}
