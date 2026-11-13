import json

from support import pipeline
from support.store import Store


def _ingest(store, world, body, step=4):
    t = dict(world["tickets"][0])
    t.update({"id": "X-9", "body": body, "channel": "mail"})
    r = pipeline.process(t, pipeline.Ctx.make("mock", step=step, world=world))
    store.ingest(t, r)
    return t, r


def test_store_ingest_and_audit(tmp_path, world):
    s = Store(str(tmp_path / "h.sqlite"))
    t, r = _ingest(s, world, "送料無料になる条件を教えてください。")
    row = s.get("X-9")
    assert row["action"] == r["action"] and json.loads(row["result_json"])["ticket_id"] == "X-9"
    assert s.audit_of("X-9")[0]["event"] == "受付"


def test_agent_cannot_send_promise(tmp_path, world):
    s = Store(str(tmp_path / "h.sqlite"))
    _ingest(s, world, "開封済みですが返金してもらえますか？")
    res = s.send("X-9", "担当者A", "agent", "全額返金いたします。")
    assert not res["ok"] and "窓口責任者" in res["error"]
    assert any(a["event"] == "送信を止めた" for a in s.audit_of("X-9"))


def test_lead_can_send_promise(tmp_path, world):
    s = Store(str(tmp_path / "h.sqlite"))
    _ingest(s, world, "開封済みですが返金してもらえますか？")
    res = s.send("X-9", "責任者B", "lead", "今回は特別に返金いたします。")
    assert res["ok"] and s.get("X-9")["status"] == "sent"


def test_pii_blocks_send(tmp_path, world):
    s = Store(str(tmp_path / "h.sqlite"))
    _ingest(s, world, "届きません")
    res = s.send("X-9", "担当者A", "agent", "090-0000-1234 にお電話します")
    assert not res["ok"] and "個人情報" in res["error"]


def test_edit_recorded_in_audit(tmp_path, world):
    s = Store(str(tmp_path / "h.sqlite"))
    _ingest(s, world, "届きません")
    s.send("X-9", "担当者A", "agent", "確認してご連絡します。")
    assert any("直して送信" in a["detail"] for a in s.audit_of("X-9"))


def test_desk_pages(web):
    d = web["desk"]
    for path in ["/", "/inbox", "/approvals", "/insights", "/knowledge", "/kb", "/kb/KB-RET-01", "/settings", "/health"]:
        assert d.get(path).status_code == 200, path


def test_desk_replay_and_ticket_page(web):
    d = web["desk"]
    assert d.post("/replay", data={"n": 30}, follow_redirects=False).status_code == 303
    rows = web["state"].store.tickets()
    assert len(rows) == 30
    page = d.get(f"/tickets/{rows[0]['id']}")
    assert page.status_code == 200 and "監査ログ" in page.text
    assert d.get(f"/api/tickets/{rows[0]['id']}").json()["ticket_id"] == rows[0]["id"]


def test_desk_send_flow_and_role(web):
    d = web["desk"]
    d.post("/replay", data={"n": 60})
    waiting = web["state"].store.tickets(status="waiting_approval")
    assert waiting
    tid = waiting[0]["id"]
    d.post(f"/tickets/{tid}/send", data={"reply": "確認してご連絡します。", "actor": "担当者A"})
    assert web["state"].store.get(tid)["status"] == "sent"


def test_desk_insights_after_replay(web):
    d = web["desk"]
    d.post("/replay", data={"n": 400})
    page = d.get("/insights")
    assert page.status_code == 200 and "出荷の遅れ" in page.text


def test_desk_knowledge_generate_and_lead_only_publish(web):
    d = web["desk"]
    d.post("/replay", data={"n": 400})
    d.post("/replay", data={"n": 400})
    d.post("/knowledge/generate")
    cands = web["state"].store.candidates()
    assert cands
    d.post(f"/knowledge/{cands[0]['id']}/status", data={"status": "公開を承認"})
    assert web["state"].store.candidates()[0]["status"] == "要確認"      # 担当者は公開を承認できない
    d.get("/role?r=lead")
    d.post(f"/knowledge/{cands[0]['id']}/status", data={"status": "公開を承認"})
    assert web["state"].store.candidates()[0]["status"] == "公開を承認"


def test_settings_change_step(web):
    d = web["desk"]
    d.post("/settings", data={"step": 2, "designed": "on"})
    assert web["common"].load_settings()["step"] == 2


def test_shop_pages(web):
    s = web["shop"]
    for path in ["/", "/products/K1", "/help", "/help/KB-SHP-01", "/contact", "/static/img/K1.svg"]:
        assert s.get(path).status_code == 200, path


def test_shop_hides_internal_articles(web):
    assert web["shop"].get("/help/KB-REF-02").status_code == 404
    assert "KB-REF-02" not in web["shop"].get("/help").text


def test_chat_auto_answer(web):
    s = web["shop"]
    s.post("/chat", data={"message": "送料無料になる条件を教えてください。", "customer_id": "C0001", "back": "/"})
    page = s.get("/")
    assert "5,500円" in page.text


def test_chat_hands_off_complaint(web):
    s = web["shop"]
    s.post("/chat", data={"message": "対応がひどすぎます。責任者を出してください。", "customer_id": "C0002", "back": "/"})
    page = s.get("/")
    assert "担当者におつなぎします" in page.text
    assert web["state"].store.tickets(status="escalated")


def test_chat_off_before_step5(web):
    web["desk"].post("/settings", data={"step": 3, "designed": "on"})
    s = web["shop"]
    s.post("/chat", data={"message": "送料は？", "customer_id": "C0001", "back": "/"})
    assert "準備中" in s.get("/").text


def test_contact_form_creates_ticket(web):
    s = web["shop"]
    page = s.post("/contact", data={"body": "スミカゼのランプが点滅しています。", "customer_id": "C0003"})
    assert page.status_code == 200 and "受付番号" in page.text
    assert web["state"].store.tickets()
