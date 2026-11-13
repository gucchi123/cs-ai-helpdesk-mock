"""商品とトップの画像（SVG・文字なし・ロゴなし）を作る。外部のサービスは使わない。

python tools/gen_images.py
🔴 画像に文字を入れない（家風）。tests/test_hygiene.py が <text> 要素の有無を確かめる。
"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "static", "img")
BG = '<rect width="400" height="300" rx="18" fill="{bg}"/><ellipse cx="200" cy="262" rx="120" ry="14" fill="#000" opacity=".08"/>'

SHAPES = {
    # 電気ケトル
    "K1": ("#e9f1ef", '<path d="M140 250 L150 110 Q200 90 250 110 L260 250 Z" fill="#f4f6f7" stroke="#9aa9b2" stroke-width="3"/>'
                      '<path d="M250 130 Q300 140 290 200 Q285 230 258 232" fill="none" stroke="#9aa9b2" stroke-width="10" stroke-linecap="round"/>'
                      '<path d="M150 112 L118 96 L152 128" fill="#f4f6f7" stroke="#9aa9b2" stroke-width="3"/>'
                      '<rect x="130" y="248" width="140" height="14" rx="6" fill="#4f6b77"/><circle cx="200" cy="200" r="7" fill="#2f7d6d"/>'),
    # 空気清浄機
    "A1": ("#eef2f6", '<rect x="135" y="60" width="130" height="195" rx="22" fill="#fbfcfc" stroke="#a7b3bb" stroke-width="3"/>'
                      + "".join(f'<line x1="155" y1="{y}" x2="245" y2="{y}" stroke="#c9d3d9" stroke-width="4" stroke-linecap="round"/>' for y in range(90, 170, 14))
                      + '<circle cx="200" cy="215" r="16" fill="none" stroke="#2f7d6d" stroke-width="4"/>'),
    # ロボット掃除機
    "R1": ("#f1efe9", '<ellipse cx="200" cy="200" rx="135" ry="52" fill="#3e4a52"/><ellipse cx="200" cy="188" rx="135" ry="52" fill="#56646d"/>'
                      '<ellipse cx="200" cy="180" rx="40" ry="14" fill="#2f7d6d" opacity=".8"/><rect x="170" y="140" width="60" height="10" rx="5" fill="#88969e"/>'),
    # コーヒーメーカー
    "C1": ("#f3ede6", '<rect x="130" y="70" width="140" height="40" rx="10" fill="#4a3f38"/><rect x="230" y="110" width="40" height="140" fill="#4a3f38"/>'
                      '<rect x="130" y="240" width="140" height="16" rx="6" fill="#4a3f38"/>'
                      '<path d="M150 150 L215 150 L208 236 Q182 246 157 236 Z" fill="#cfe3e8" opacity=".85" stroke="#7d9aa3" stroke-width="3"/>'
                      '<path d="M160 205 L205 205 L203 234 Q182 241 162 234 Z" fill="#6b4a33"/>'),
    # 加湿器
    "H1": ("#eaf2f7", '<path d="M150 250 Q140 150 200 110 Q260 150 250 250 Z" fill="#fbfdfe" stroke="#a3b7c3" stroke-width="3"/>'
                      '<path d="M200 105 Q190 70 205 45" fill="none" stroke="#b8d3e0" stroke-width="8" stroke-linecap="round" opacity=".8"/>'
                      '<path d="M215 100 Q230 70 220 50" fill="none" stroke="#b8d3e0" stroke-width="6" stroke-linecap="round" opacity=".6"/>'
                      '<circle cx="200" cy="215" r="10" fill="#2f7d6d"/>'),
    # トースター
    "T1": ("#f5efe8", '<rect x="110" y="120" width="180" height="130" rx="26" fill="#e7d9c7" stroke="#b49d84" stroke-width="3"/>'
                      '<rect x="140" y="112" width="45" height="12" rx="5" fill="#8a745e"/><rect x="215" y="112" width="45" height="12" rx="5" fill="#8a745e"/>'
                      '<rect x="150" y="90" width="28" height="30" rx="6" fill="#d9a35f"/><rect x="222" y="94" width="28" height="26" rx="6" fill="#d9a35f"/>'
                      '<circle cx="270" cy="200" r="9" fill="#8a745e"/>'),
}


def hero() -> str:
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 300"><rect width="400" height="300" rx="18" fill="#e5efec"/>'
            '<rect x="0" y="210" width="400" height="90" fill="#d6e4df"/><rect x="40" y="120" width="120" height="92" rx="8" fill="#f8faf9"/>'
            '<rect x="240" y="80" width="110" height="132" rx="14" fill="#fbfcfc" stroke="#a7b3bb" stroke-width="2"/>'
            '<circle cx="320" cy="40" r="18" fill="#f2d48a"/><path d="M70 120 Q100 70 130 120" fill="none" stroke="#9aa9b2" stroke-width="6"/></svg>')


def main():
    os.makedirs(OUT, exist_ok=True)
    for pid, (bg, body) in SHAPES.items():
        svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 300">{BG.format(bg=bg)}{body}</svg>'
        open(os.path.join(OUT, f"{pid}.svg"), "w", encoding="utf-8").write(svg)
    open(os.path.join(OUT, "hero.svg"), "w", encoding="utf-8").write(hero())
    print(f"{len(SHAPES) + 1} 枚を書き出しました: static/img/")


if __name__ == "__main__":
    main()
