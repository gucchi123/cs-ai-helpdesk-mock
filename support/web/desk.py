"""窓口（ヘルプデスク）: 受信箱・チケット・承認の列・傾向・記事の候補・設定。ポート 8801。"""
from __future__ import annotations

import json

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from support import analytics, config, flags as flagmod, knowledge
from support.web.common import TEMPLATES, load_settings, save_settings, state

app = FastAPI(title="つゆはな家電 お問い合わせ窓口（架空）")
app.mount("/static", StaticFiles(directory=f"{config.ROOT}/static"), name="static")


def _role(req: Request) -> str:
    return req.cookies.get("desk_role", "agent")


def _page(req: Request, name: str, **kw):
    s = load_settings()
    return TEMPLATES.TemplateResponse(req, name, {"role": _role(req), "settings": s, "step_title": flagmod.STEP_TITLES[int(s["step"])], **kw})


@app.get("/", response_class=HTMLResponse)
def dashboard(req: Request):
    st = state()
    rows = st.store.tickets(limit=5000)
    n = len(rows)
    by = lambda key: sum(1 for r in rows if r["action"] == key)
    results = st.store.all_results()
    ai_usd = sum(r["usage"]["cost_usd"] for r in results.values())
    kpi = {"n": n, "auto": by("auto_send"), "approve": by("approve"), "escalate": by("escalate"), "human": by("human"),
           "waiting": sum(1 for r in rows if r["status"] == "waiting_approval"),
           "escalated": sum(1 for r in rows if r["status"] == "escalated"),
           "ai_usd": round(ai_usd, 4), "usd_per_ticket": round(ai_usd / n, 5) if n else 0,
           "estimated": any(r["usage"].get("estimated") for r in results.values())}
    return _page(req, "desk/dashboard.html", kpi=kpi, counts=st.store.counts(), total_stream=len(st.world["tickets"]))


@app.post("/replay")
def replay(n: int = Form(20)):
    state().replay(max(1, min(int(n), 400)))
    return RedirectResponse("/", status_code=303)


@app.get("/inbox", response_class=HTMLResponse)
def inbox(req: Request, status: str | None = None, queue: str | None = None):
    return _page(req, "desk/inbox.html", rows=state().store.tickets(status=status or None, queue=queue or None),
                 status=status, queue=queue)


@app.get("/approvals", response_class=HTMLResponse)
def approvals(req: Request):
    st = state().store
    return _page(req, "desk/approvals.html", waiting=st.tickets(status="waiting_approval"), escalated=st.tickets(status="escalated"))


@app.get("/tickets/{tid}", response_class=HTMLResponse)
def ticket(req: Request, tid: str, msg: str | None = None):
    st = state()
    row = st.store.get(tid)
    if row is None:
        return HTMLResponse("見つかりません", status_code=404)
    r = json.loads(row["result_json"])
    cust = next((c for c in st.world["customers"] if c["id"] == row["customer_id"]), None)
    return _page(req, "desk/ticket.html", t=row, r=r, audit=st.store.audit_of(tid), msg=msg,
                 customer_name=(cust or {}).get("name", "（不明）"))


@app.post("/tickets/{tid}/send")
def send(req: Request, tid: str, reply: str = Form(...), actor: str = Form("担当者A")):
    res = state().store.send(tid, actor, _role(req), reply)
    msg = "送信しました" if res["ok"] else res["error"]
    return RedirectResponse(f"/tickets/{tid}?msg={msg}", status_code=303)


@app.post("/tickets/{tid}/escalate")
def escalate(tid: str, to_queue: str = Form(...), note: str = Form(""), actor: str = Form("担当者A")):
    state().store.escalate(tid, actor, to_queue, note)
    return RedirectResponse(f"/tickets/{tid}?msg=引き継ぎました", status_code=303)


@app.post("/tickets/{tid}/close")
def close(tid: str, actor: str = Form("担当者A")):
    state().store.close(tid, actor)
    return RedirectResponse(f"/tickets/{tid}?msg=完了にしました", status_code=303)


@app.get("/insights", response_class=HTMLResponse)
def insights(req: Request):
    st = state()
    results = st.store.all_results()
    ids = set(results)
    tickets = [t for t in st.world["tickets"] if t["id"] in ids]
    rep = analytics.report(tickets, results) if tickets else None
    return _page(req, "desk/insights.html", rep=rep, mermaid=analytics.mermaid(rep["graph"]) if rep else "")


@app.get("/knowledge", response_class=HTMLResponse)
def knowledge_page(req: Request):
    rows = state().store.candidates()
    return _page(req, "desk/knowledge.html", rows=[{**dict(r), "data": json.loads(r["json"])} for r in rows])


@app.post("/knowledge/generate")
def knowledge_generate():
    st = state()
    results = st.store.all_results()
    tickets = [t for t in st.world["tickets"] if t["id"] in results]
    for c in knowledge.candidates(tickets, results, st.kb, st.ctx().provider):
        st.store.add_candidate(c)
    return RedirectResponse("/knowledge", status_code=303)


@app.post("/knowledge/{cid}/status")
def knowledge_status(req: Request, cid: int, status: str = Form(...), actor: str = Form("担当者A")):
    if status == "公開を承認" and _role(req) != "lead":
        return RedirectResponse("/knowledge?msg=公開の承認は窓口責任者だけ", status_code=303)
    state().store.set_candidate_status(cid, status, actor)
    return RedirectResponse("/knowledge", status_code=303)


@app.get("/kb", response_class=HTMLResponse)
def kb_list(req: Request):
    return _page(req, "desk/kb.html", articles=state().kb.articles)


@app.get("/kb/{aid}", response_class=HTMLResponse)
def kb_article(req: Request, aid: str):
    a = state().kb.by_article.get(aid)
    if a is None:
        return HTMLResponse("見つかりません", status_code=404)
    return _page(req, "desk/kb_article.html", a=a)


@app.get("/settings", response_class=HTMLResponse)
def settings_page(req: Request):
    return _page(req, "desk/settings.html", steps=flagmod.STEP_TITLES)


@app.post("/settings")
def settings_save(step: int = Form(...), designed: str = Form("on")):
    s = load_settings()
    s["step"] = max(0, min(6, int(step)))
    s["designed"] = designed == "on"
    save_settings(s)
    return RedirectResponse("/settings", status_code=303)


@app.get("/role")
def set_role(r: str = "agent"):
    resp = RedirectResponse("/", status_code=303)
    resp.set_cookie("desk_role", "lead" if r == "lead" else "agent")
    return resp


@app.get("/api/tickets/{tid}")
def api_ticket(tid: str):
    row = state().store.get(tid)
    if row is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse(json.loads(row["result_json"]))


@app.get("/health")
def health():
    return {"ok": True, "service": "desk"}
