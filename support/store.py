"""窓口の記録（SQLite）。チケット・承認・監査ログ・記事の候補。

🔴 承認の境界は人の側にもある: 返金額が閾値以上・規程外の約束を含む返信は「窓口責任者」しか送れない。
   画面の役割の切り替えは手元の模擬（ログインは作っていない）。本番では認証と権限で分ける。
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime

from support import checks, config, pii

_lock = threading.Lock()
SCHEMA = """
create table if not exists tickets(
  id text primary key, created_at text, channel text, customer_id text, order_id text, product text, body text,
  status text, queue text, priority text, category text, confidence real, action text, why text,
  result_json text, final_reply text, handled_by text, updated_at text);
create table if not exists audit(
  id integer primary key autoincrement, ticket_id text, at text, actor text, event text, detail text);
create table if not exists kb_candidates(
  id integer primary key autoincrement, symptom text, title text, body text, status text, created_at text, json text);
"""
STATUS_OF_ACTION = {"auto_send": "sent_auto", "approve": "waiting_approval", "escalate": "escalated", "human": "new"}
STATUS_LABEL = {"sent_auto": "自動で送信済み", "waiting_approval": "承認待ち", "escalated": "引き継ぎ中", "new": "未対応",
                "sent": "送信済み", "closed": "完了"}


def now() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


class Store:
    def __init__(self, path: str | None = None):
        config.ensure_dirs()
        self.path = path or os.path.join(config.RUNTIME_DIR, "helpdesk.sqlite")
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        with _lock:
            self.db.executescript(SCHEMA)
            self.db.commit()

    # ---- 書き込み ----
    def ingest(self, t: dict, r: dict) -> None:
        status = STATUS_OF_ACTION[r["action"]]
        final = (r.get("draft") or {}).get("reply") if r["action"] == "auto_send" else None
        with _lock:
            self.db.execute("insert or replace into tickets values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                t["id"], t["created_at"], r["channel"], t.get("customer_id"), t.get("order_id"), t.get("product"),
                t["body"], status, r["queue"], r["priority"], r["classification"].get("category"),
                r["classification"].get("confidence"), r["action"], r["why"], json.dumps(r, ensure_ascii=False),
                final, "AI" if final else None, now()))
            self.db.commit()
        self.log(t["id"], "AI", "受付", f"{r['action']} / {r['why'][:80]}")

    def log(self, tid: str, actor: str, event: str, detail: str = "") -> None:
        with _lock:
            self.db.execute("insert into audit(ticket_id, at, actor, event, detail) values (?,?,?,?,?)",
                            (tid, now(), actor, event, detail[:500]))
            self.db.commit()

    def send(self, tid: str, actor: str, role: str, reply: str) -> dict:
        """人が返信を送る。送る前に同じ検査を人の文にもかける。"""
        row = self.get(tid)
        if row is None:
            return {"ok": False, "error": "チケットがありません"}
        r = json.loads(row["result_json"])
        findings = checks.run(reply, channel=row["channel"])
        promise = [f for f in findings if f["kind"] == "promise"]
        needs_lead = ("refund_over_threshold" in r["escalation"]["reasons"]) or bool(promise)
        if needs_lead and role != "lead":
            self.log(tid, actor, "送信を止めた", "窓口責任者の承認が必要: " + ("; ".join(f["msg"] for f in promise) or "返金額が閾値以上"))
            return {"ok": False, "error": "この返信は窓口責任者だけが送れます（返金額が閾値以上、または規程外の約束を含む）",
                    "findings": findings}
        leaks = pii.detect(reply)
        if leaks:
            self.log(tid, actor, "送信を止めた", "個人情報らしい値: " + ", ".join(x[0] for x in leaks))
            return {"ok": False, "error": "返信に個人情報らしい値があります（" + ", ".join(x[0] for x in leaks) + "）", "findings": findings}
        with _lock:
            self.db.execute("update tickets set status='sent', final_reply=?, handled_by=?, updated_at=? where id=?",
                            (reply, f"{actor}（{'責任者' if role == 'lead' else '担当者'}）", now(), tid))
            self.db.commit()
        edited = reply != ((r.get("draft") or {}).get("reply") or "")
        self.log(tid, actor, "送信", ("直して送信" if edited else "そのまま承認") + (" / 注意: " + "; ".join(f["msg"] for f in findings) if findings else ""))
        return {"ok": True, "edited": edited, "findings": findings}

    def escalate(self, tid: str, actor: str, to_queue: str, note: str = "") -> None:
        with _lock:
            self.db.execute("update tickets set status='escalated', queue=?, updated_at=? where id=?", (to_queue, now(), tid))
            self.db.commit()
        self.log(tid, actor, "引き継ぎ", f"→ {to_queue} {note}")

    def close(self, tid: str, actor: str) -> None:
        with _lock:
            self.db.execute("update tickets set status='closed', updated_at=? where id=?", (now(), tid))
            self.db.commit()
        self.log(tid, actor, "完了")

    def add_candidate(self, c: dict) -> int:
        with _lock:
            cur = self.db.execute("insert into kb_candidates(symptom, title, body, status, created_at, json) values (?,?,?,?,?,?)",
                                  (c["symptom"], c["title"], c["body"], c["status"], now(), json.dumps(c, ensure_ascii=False)))
            self.db.commit()
            return cur.lastrowid

    def set_candidate_status(self, cid: int, status: str, actor: str) -> None:
        with _lock:
            self.db.execute("update kb_candidates set status=? where id=?", (status, cid))
            self.db.commit()
        self.log(f"KB候補{cid}", actor, "記事の候補", status)

    # ---- 読み出し ----
    def get(self, tid: str):
        return self.db.execute("select * from tickets where id=?", (tid,)).fetchone()

    def tickets(self, status: str | None = None, queue: str | None = None, limit: int = 200) -> list:
        q, args = "select * from tickets", []
        cond = []
        if status:
            cond.append("status=?")
            args.append(status)
        if queue:
            cond.append("queue=?")
            args.append(queue)
        if cond:
            q += " where " + " and ".join(cond)
        q += " order by case priority when 'urgent' then 0 when 'high' then 1 else 2 end, created_at desc limit ?"
        args.append(limit)
        return self.db.execute(q, args).fetchall()

    def audit_of(self, tid: str) -> list:
        return self.db.execute("select * from audit where ticket_id=? order by id", (tid,)).fetchall()

    def counts(self) -> dict:
        rows = self.db.execute("select status, count(*) n from tickets group by status").fetchall()
        return {r["status"]: r["n"] for r in rows}

    def candidates(self) -> list:
        return self.db.execute("select * from kb_candidates order by id desc").fetchall()

    def all_results(self) -> dict:
        return {r["id"]: json.loads(r["result_json"]) for r in self.db.execute("select id, result_json from tickets")}
