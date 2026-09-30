"""The preview image shown when someone shares a whoshowsup.net link (Open Graph / social cards).

    .venv/Scripts/python.exe midterms_2026/share_card.py

1200 x 630 PNG with today's odds for the House and Senate and the likeliest governors split, naming
whichever side is favored. Written to site/src/share.png by export_site_data.main (every daily run);
the site build copies it to /share.png, and observablehq.config.js points each page's preview tags at it.
Fonts are Georgia and Segoe UI from Windows, close to the site's Source Serif and Inter.
"""
from pathlib import Path
import json

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site" / "src"
OUT = SITE / "share.png"
FONTS = Path("C:/Windows/Fonts")
W, H = 1200, 630
PAGE, INK, INK2, INK3, HAIR = "#f9f9f7", "#0b0b0b", "#52514e", "#898781", "#e4e2dc"
DEM, REP = "#2a78d6", "#d6403a"


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    for f in ([name] if isinstance(name, str) else name):
        try:
            return ImageFont.truetype(str(FONTS / f), size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def pct(p: float) -> str:
    return ">99%" if p >= 0.995 else "<1%" if p <= 0.005 else f"{round(100 * p)}%"


def chamber(d: ImageDraw.ImageDraw, x: int, y: int, w: int, label: str, p_dem: float) -> None:
    fav, p = ("Democrats", p_dem) if p_dem >= 0.5 else ("Republicans", 1 - p_dem)
    d.text((x, y), label.upper(), font=font("seguisb.ttf", 24), fill=INK3)
    d.text((x, y + 34), pct(p), font=font("segoeuib.ttf", 88), fill=DEM if p_dem >= 0.5 else REP)
    d.text((x, y + 142), f"chance {fav} win control", font=font("segoeui.ttf", 26), fill=INK2)
    # both parties' chances, as on the site
    by, bh, cut = y + 190, 16, x + round(w * p_dem)
    d.rounded_rectangle((x, by, x + w, by + bh), radius=8, fill=REP)
    if cut > x:
        d.rounded_rectangle((x, by, cut, by + bh), radius=8, fill=DEM)
        if cut < x + w - 8:
            d.rectangle((cut - 8, by, cut, by + bh), fill=DEM)
    d.rectangle((cut, by, cut + 3, by + bh), fill=PAGE)


def make(out: Path = OUT) -> Path:
    top = json.loads((SITE / "data" / "topline.json").read_text(encoding="utf-8"))
    img = Image.new("RGB", (W, H), PAGE)
    d = ImageDraw.Draw(img)
    logo = SITE / "apple-touch-icon.png"
    x0 = 64
    if logo.exists():  # the icon sits on a white square: make the near-white corners see-through
        a = np.asarray(Image.open(logo).convert("RGBA").resize((64, 64))).copy()
        a[a[..., :3].min(axis=2) > 235, 3] = 0
        mark = Image.fromarray(a)
        img.paste(mark, (x0, 52), mark)
    d.text((x0 + 84, 58), "Who Shows Up", font=font("segoeuib.ttf", 40), fill=INK)
    from datetime import date
    day = date.fromisoformat(top["forecast_date"])
    d.text((W - 64, 72), f"2026 midterm forecast · {day:%b} {day.day}", font=font("segoeui.ttf", 26), fill=INK3, anchor="ra")
    d.line((x0, 146, W - 64, 146), fill=HAIR, width=2)
    col = (W - 2 * x0 - 80) // 2
    chamber(d, x0, 186, col, "House", top["p_house_d"])
    chamber(d, x0 + col + 80, 186, col, "Senate", top["p_senate_d"])
    gd = round(top["gov_median"])
    gov = (f"Governors: the likeliest split of the 36 races is {max(gd, 36 - gd)} {'Democrats' if gd > 18 else 'Republicans'}, "
           f"{min(gd, 36 - gd)} {'Republicans' if gd > 18 else 'Democrats'}") if gd != 18 else "Governors: the likeliest result is an even 18-18 split"
    d.text((x0, 452), gov, font=font("segoeui.ttf", 28), fill=INK2)
    d.line((x0, 520, W - 64, 520), fill=HAIR, width=2)
    d.text((x0, 544), "whoshowsup.net", font=font("seguisb.ttf", 30), fill=INK)
    d.text((W - 64, 550), "A turnout-first forecast, updated daily", font=font("segoeui.ttf", 26), fill=INK3, anchor="ra")
    img.save(out, optimize=True)
    return out


if __name__ == "__main__":
    print(make())
