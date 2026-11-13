"""窓口と通販サイトが共有する状態（記録・設定・AI の呼び先）。

設定（Step・守りの有無）は data/runtime/settings.json。両方のサービスが読む。
"""
from __future__ import annotations

import json
import os
import re
import threading
from datetime import datetime

from fastapi.templating import Jinja2Templates
from markupsafe import Markup, escape

from support import config, kb as kbmod, llm, pipeline, seed
from support.store import STATUS_LABEL, Store

TEMPLATES = Jinja2Templates(directory=os.path.join(config.ROOT, "templates"))
SETTINGS = os.path.join(config.RUNTIME_DIR, "settings.json")
_lock = threading.Lock()
QUEUE_LABEL = seed.QUEUES
CATEGORY_LABEL = {"shipping": "配送", "return": "返品・交換", "refund": "返金", "defect": "故障・不具合",
                  "subscription": "定期便", "warranty": "保証・修理", "account": "アカウント", "howto": "使い方",
                  "complaint": "苦情", "safety": "安全"}
ACTION_LABEL = {"auto_send": "自動送信", "approve": "人の承認へ", "escalate": "引き継ぎ", "human": "人が対応"}


def cite_links(text: str) -> Markup:
    """[KB-XXX#n] を記事へのリンクにする（本文は escape してから）。"""
    s = str(escape(text or ""))
    s = re.sub(r"\[(KB-[A-Z0-9\-]+)#(\d+)\]", r'<a class="cite" href="/kb/\1#s\2">[\1#\2]</a>', s)
    return Markup(s.replace("\n", "<br>"))


def shop_cites(text: str) -> Markup:
    """お客様向け: 引用は「ヘルプの記事」へのリンクに（記事 ID は見せない）。"""
    s = str(escape(text or ""))
    s = re.sub(r"\[(KB-[A-Z0-9\-]+)#(\d+)\]", r'<a class="cite" href="/help/\1#s\2">［ヘルプ］</a>', s)
    return Markup(s.replace("\n", "<br>"))


TEMPLATES.env.filters["cites"] = cite_links
TEMPLATES.env.filters["shopcites"] = shop_cites
TEMPLATES.env.globals.update(QUEUE_LABEL=QUEUE_LABEL, CATEGORY_LABEL=CATEGORY_LABEL, ACTION_LABEL=ACTION_LABEL,
                             STATUS_LABEL=STATUS_LABEL, COMPANY=config.COMPANY, SHOP_PORT=config.SHOP_PORT,
                             DESK_PORT=config.DESK_PORT)


def load_settings() -> dict:
    s = {"step": 5, "designed": True, "provider": os.environ.get("CSAI_PROVIDER", "mock"), "replayed": 0}
    if os.path.exists(SETTINGS):
        try:
            s.update(json.load(open(SETTINGS, encoding="utf-8")))
        except ValueError:
            pass
    return s


def save_settings(s: dict) -> None:
    config.ensure_dirs()
    with _lock, open(SETTINGS, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False)


class State:
    """1 プロセスに 1 つ。テストでは別の DB で作り直せる。"""

    def __init__(self, db_path: str | None = None):
        self.world = seed.world()
        self.kb = kbmod.default_kb()
        self.store = Store(db_path)
        self.chats: dict[str, list] = {}
        self._n = 0

    def ctx(self) -> pipeline.Ctx:
        s = load_settings()
        prov = s["provider"] if s["designed"] else "mock_naive"
        return pipeline.Ctx.make(prov, step=int(s["step"]), defenses=True if s["designed"] else None,
                                 world=self.world, kb=self.kb)

    def new_id(self, prefix: str) -> str:
        with _lock:
            self._n += 1
            return f"{prefix}-{datetime.now().strftime('%m%d%H%M%S')}-{self._n:03d}"

    def replay(self, n: int) -> list[str]:
        """8 週間の問い合わせの流れから、次の n 件を受信箱に流す。"""
        s = load_settings()
        start = int(s.get("replayed", 0))
        ctx = self.ctx()
        done = []
        for t in self.world["tickets"][start:start + n]:
            r = pipeline.process(t, ctx)
            self.store.ingest(t, r)
            done.append(t["id"])
        s["replayed"] = start + len(done)
        save_settings(s)
        return done

    def submit(self, customer_id: str, body: str, channel: str, order_id: str | None = None) -> tuple[dict, dict]:
        cust = next((c for c in self.world["customers"] if c["id"] == customer_id), self.world["customers"][0])
        order = next((o for o in self.world["orders"] if o["customer_id"] == cust["id"]), None)
        t = {"id": self.new_id("W"), "created_at": datetime.now().strftime("%Y-%m-%dT%H:%M"), "week": 9,
             "channel": channel, "customer_id": cust["id"], "order_id": order_id or (order or {}).get("id"),
             "product": (order or {}).get("product"), "body": body, "template": "web",
             "gold": None, "resolution": {"cause": "", "symptom": ""}, "pii": [], "injection": False, "contact_count": 1}
        r = pipeline.process(t, self.ctx(), channel=channel)
        self.store.ingest(t, r)
        return t, r


_state: State | None = None


def state() -> State:
    global _state
    if _state is None:
        _state = State()
    return _state


def reset_state(db_path: str | None = None) -> State:
    global _state
    _state = State(db_path)
    return _state
