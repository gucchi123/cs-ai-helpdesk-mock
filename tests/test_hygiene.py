"""実在の名前・鍵・カード番号らしい値・画像の文字が、キットに入っていないこと。"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCAN_DIRS = ["support", "templates", "kb", "static", "labs", "tools"]
EXT = (".py", ".html", ".md", ".css", ".svg", ".json", ".jsonl")

# 実在の会社・サービス・事故の当事者の名前（講座では社名を出さない取り決め）。モデルの呼び先の Anthropic/Claude は除く
BANNED = ["Air Canada", "エア・カナダ", "DPD", "Cursor", "Klarna", "Chevrolet", "Zendesk", "Freshdesk", "Intercom",
          "Salesforce", "Amazon", "ヤマト", "佐川", "Dify", "Copilot", "ChatGPT", "OpenAI", "Gemini",
          "LINE", "MyCity", "Watsonville"]


def _files():
    for d in SCAN_DIRS:
        for base, _, files in os.walk(os.path.join(ROOT, d)):
            if "__pycache__" in base or os.sep + "out" + os.sep in base + os.sep or base.endswith(os.sep + "recorded"):
                continue
            for f in files:
                if f.endswith(EXT):
                    yield os.path.join(base, f)


def test_no_real_company_names():
    hits = []
    for p in _files():
        s = open(p, encoding="utf-8", errors="ignore").read()
        for w in BANNED:
            if re.search(rf"(?<![A-Za-z]){re.escape(w)}(?![A-Za-z])", s):
                hits.append((os.path.relpath(p, ROOT), w))
    assert hits == [], hits


def test_no_api_keys():
    for p in _files():
        s = open(p, encoding="utf-8", errors="ignore").read()
        assert not re.search(r"sk-ant-[A-Za-z0-9]{8,}", s), p


def test_no_card_like_numbers():
    rx = re.compile(r"(?<!\d)(?:\d{4}[ -]){3}\d{4}(?!\d)|(?<!\d)\d{16}(?!\d)")
    for p in _files():
        if p.endswith(".svg"):
            continue
        assert not rx.search(open(p, encoding="utf-8", errors="ignore").read()), p


def test_images_have_no_text():
    img = os.path.join(ROOT, "static", "img")
    files = [f for f in os.listdir(img) if f.endswith(".svg")]
    assert len(files) >= 7
    for f in files:
        s = open(os.path.join(img, f), encoding="utf-8").read()
        assert "<text" not in s and "<tspan" not in s, f


def test_company_is_fictional_name_everywhere():
    from support import config
    assert config.COMPANY == "つゆはな家電"
