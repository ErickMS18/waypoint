"""Generate a 1200x627 project cover (LinkedIn / GitHub social preview).

Reusable for any project: edit the CONFIG block or pass a JSON file with the same keys.

    python scripts/make_cover.py                       # Waypoint cover -> assets/cover.png
    python scripts/make_cover.py my_cover.json out.png # any other project

Fonts: uses Inter if installed, otherwise falls back to DejaVu/Arial.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

CONFIG = {
    "title": "Waypoint",
    "subtitle": "AI career radar + personal planner · LLM-powered",
    "stats": [["360", "real job postings"], ["180", "companies"], ["5", "target roles"]],
    "tech": "Python · LLMs · Pydantic · Streamlit · Evaluation (P/R/F1)",
    "url": "github.com/ErickMS18/waypoint",
    "chart_title": "Most requested skills (5 data & AI roles)",
    # [label, required share, nice-to-have share]
    "bars": [["Python", 0.683, 0.036], ["SQL", 0.431, 0.008], ["Machine Learning", 0.367, 0.042],
             ["LLMs", 0.269, 0.103], ["AI agents", 0.258, 0.069]],
}

W, H = 1200, 627
BG, INK, INK_2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
BLUE, ORANGE = "#2a78d6", "#eb6834"


def font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    names = {
        "bold": ["Inter-Bold.otf", "Inter-Bold.ttf", "DejaVuSans-Bold.ttf", "arialbd.ttf"],
        "semi": ["Inter-SemiBold.otf", "Inter-SemiBold.ttf", "DejaVuSans-Bold.ttf", "arialbd.ttf"],
        "regular": ["Inter-Regular.otf", "Inter-Regular.ttf", "DejaVuSans.ttf", "arial.ttf"],
        "mono": ["DejaVuSansMono.ttf", "consola.ttf", "cour.ttf"],
    }[weight]
    dirs = [Path("/usr/share/fonts/opentype/inter"), Path("/usr/share/fonts/truetype/dejavu"),
            Path("C:/Windows/Fonts"), Path.home() / "AppData/Local/Microsoft/Windows/Fonts"]
    for n in names:
        for d in dirs:
            if (d / n).exists():
                return ImageFont.truetype(str(d / n), size)
    return ImageFont.load_default(size)


def make_cover(cfg: dict, out: Path) -> Path:
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    x0 = 72
    d.text((x0, 70), cfg["title"], font=font("bold", 96), fill=INK)
    d.text((x0, 180), cfg["subtitle"], font=font("regular", 30), fill=INK_2)
    sx = x0
    for value, label in cfg["stats"]:
        d.text((sx, 268), value, font=font("bold", 54), fill=BLUE)
        d.text((sx, 334), label, font=font("regular", 21), fill=INK_2)
        sx += 215
    d.text((x0, 428), cfg["tech"], font=font("regular", 21), fill=INK)
    d.text((x0, 506), cfg["url"], font=font("mono", 22), fill=INK_2)

    bars = cfg.get("bars") or []
    if bars:
        cx, cy, label_w, max_w, row = 808, 258, 95, 230, 50
        d.text((cx, cy - 38), cfg.get("chart_title", ""), font=font("regular", 15), fill=INK_2)
        f = font("regular", 17)
        top = max(r + n for _, r, n in bars)
        d.line([(cx + label_w, cy - 6), (cx + label_w, cy + row * len(bars) - 8)], fill=GRID, width=2)
        for i, (name, req, nice) in enumerate(bars):
            y = cy + i * row
            tw = d.textlength(name, font=f)
            d.text((cx + label_w - 12 - tw, y + 7), name, font=f, fill=INK_2)
            wr, wn = max_w * req / top, max_w * nice / top
            bx = cx + label_w + 2
            d.rounded_rectangle([bx, y, bx + wr, y + 34], radius=4, fill=BLUE)
            if wn >= 3:
                d.rounded_rectangle([bx + wr + 2, y, bx + wr + 2 + wn, y + 34], radius=4, fill=ORANGE)
        ly = cy + row * len(bars) + 6
        d.rounded_rectangle([cx + label_w + 2, ly + 4, cx + label_w + 14, ly + 16], radius=2, fill=BLUE)
        d.text((cx + label_w + 20, ly), "required", font=font("regular", 14), fill=INK_2)
        d.rounded_rectangle([cx + label_w + 100, ly + 4, cx + label_w + 112, ly + 16], radius=2, fill=ORANGE)
        d.text((cx + label_w + 118, ly), "nice-to-have", font=font("regular", 14), fill=INK_2)
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out, optimize=True)
    return out


if __name__ == "__main__":
    cfg = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")) if len(sys.argv) > 1 else CONFIG
    target = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).resolve().parents[1] / "assets" / "cover.png"
    print(make_cover(cfg, target))
