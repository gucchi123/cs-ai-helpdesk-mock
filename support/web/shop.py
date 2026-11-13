"""お客様向けの通販サイト（チャットつき）。ポート 8800。

- 商品・ヘルプ（公開記事だけ）・お問い合わせフォーム・右下のチャット
- チャットは AI が答える。自動送信の条件を満たさないものは「担当者におつなぎします」で窓口の列へ
- ログインは作っていない（デモ用に「お客様」を選ぶ）。🔴 本番では本人確認の後でしか注文の情報を出さない
"""
from __future__ import annotations

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from support import config, seed
from support.web.common import TEMPLATES, load_settings, state

app = FastAPI(title="つゆはな家電 オンラインストア（架空）")
app.mount("/static", StaticFiles(directory=f"{config.ROOT}/static"), name="static")


def _sid(req: Request) -> str:
    return req.cookies.get("shop_chat") or ""


def _page(req: Request, name: str, **kw):
    st = state()
    sid = _sid(req)
    resp = TEMPLATES.TemplateResponse(req, name, {
        "products": seed.PRODUCTS, "chat": st.chats.get(sid, []), "demo_customers": st.world["customers"][:6],
        "customer_id": req.cookies.get("shop_customer", st.world["customers"][0]["id"]),
        "chat_on": int(load_settings()["step"]) >= 5, **kw})
    if not sid:
        resp.set_cookie("shop_chat", st.new_id("S"))
    return resp


@app.get("/", response_class=HTMLResponse)
def home(req: Request):
    return _page(req, "shop/home.html")


@app.get("/products/{pid}", response_class=HTMLResponse)
def product(req: Request, pid: str):
    p = seed.PRODUCTS.get(pid)
    if p is None:
        return HTMLResponse("見つかりません", status_code=404)
    return _page(req, "shop/product.html", pid=pid, p=p)


@app.get("/help", response_class=HTMLResponse)
def help_list(req: Request):
    return _page(req, "shop/help.html", articles=[a for a in state().kb.articles if a.public])


@app.get("/help/{aid}", response_class=HTMLResponse)
def help_article(req: Request, aid: str):
    a = state().kb.by_article.get(aid)
    if a is None or not a.public:
        return HTMLResponse("見つかりません", status_code=404)
    return _page(req, "shop/help_article.html", a=a)


@app.get("/contact", response_class=HTMLResponse)
def contact(req: Request):
    return _page(req, "shop/contact.html")


@app.post("/contact", response_class=HTMLResponse)
def contact_post(req: Request, body: str = Form(...), customer_id: str = Form(...)):
    t, r = state().submit(customer_id, body, "form")
    return _page(req, "shop/contact_done.html", tid=t["id"], r=r)


@app.post("/chat")
def chat(req: Request, message: str = Form(...), customer_id: str = Form(...), back: str = Form("/")):
    st = state()
    sid = _sid(req) or st.new_id("S")
    log = st.chats.setdefault(sid, [])
    log.append({"who": "you", "text": message})
    if int(load_settings()["step"]) < 5:
        log.append({"who": "sys", "text": "チャットは準備中です。お問い合わせフォームをご利用ください。"})
    else:
        t, r = st.submit(customer_id, message, "chat")
        if r["action"] == "auto_send":
            log.append({"who": "ai", "text": r["draft"]["reply"], "tid": t["id"]})
        else:
            log.append({"who": "sys", "tid": t["id"],
                        "text": f"担当者におつなぎします。受付番号は {t['id']} です。平日 9〜18 時に順番にご返信します。"})
    resp = RedirectResponse(back if back.startswith("/") else "/", status_code=303)
    resp.set_cookie("shop_chat", sid)
    resp.set_cookie("shop_customer", customer_id)
    return resp


@app.get("/health")
def health():
    return {"ok": True, "service": "shop"}
