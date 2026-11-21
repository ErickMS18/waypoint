"""Generate a 1200x627 project cover (LinkedIn / GitHub social preview) in Waypoint's visual identity.

Bottle-green ground, a mustard panel for the one thing that matters, Instrument Serif for the voice and
Hanken Grotesk for the rest (both bundled with the app, so the cover looks the same on any machine).
Reusable for any project: edit the CONFIG block or pass a JSON file with the same keys.

    python scripts/make_cover.py                       # Waypoint cover -> assets/cover.png
    python scripts/make_cover.py my_cover.json out.png # any other project
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

CONFIG = {
    "title": "Waypoint",
    "subtitle": "AI career radar + personal planner",
    "stats": [["360", "real job postings"], ["180", "companies"], ["5", "target roles"]],
    "tech": "Python  /  LLMs  /  Pydantic  /  FastAPI  /  Evaluation (P/R/F1)",
    "url": "github.com/ErickMS18/waypoint",
    "chart_title": "Most requested skills",
    "chart_note": "technical, share of 360 postings in 5 roles",
    # [label, share of postings]
    "bars": [["Python", 0.72], ["SQL", 0.44], ["Machine Learning", 0.41], ["LLMs", 0.37], ["AI agents", 0.33]],
}

W, H = 1200, 627
BG, INK, MUTED, LINE = "#0E2A21", "#F4EFE0", "#B8C6BA", "#25493D"
ACCENT, ON_ACCENT, PINK = "#F2B630", "#1C1405", "#F49AC1"
FONTS = Path(__file__).resolve().parents[1] / "src" / "waypoint" / "web" / "static" / "fonts"


def serif(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / "instrument-serif-latin-400-normal.woff2"), size)


def sans(size: int, weight: int = 400) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(str(FONTS / "hanken-grotesk-latin-wght-normal.woff2"), size)
    try:
        f.set_variation_by_axes([weight])
    except (OSError, AttributeError):
        pass
    return f


def make_cover(cfg: dict, out: Path) -> Path:
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    x0 = 72

    # brand mark + title
    d.polygon([(x0, 128), (x0 + 22, 90), (x0 + 44, 128)], fill=ACCENT)
    d.text((x0 + 62, 46), cfg["title"], font=serif(118), fill=INK)
    d.text((x0, 182), cfg["subtitle"], font=sans(30, 450), fill=MUTED)

    # stats: serif numbers, the first one in mustard, the rest in ink
    sx = x0
    for i, (value, label) in enumerate(cfg["stats"]):
        d.text((sx, 252), value, font=serif(84), fill=ACCENT if i == 0 else INK)
        d.text((sx + 2, 352), label, font=sans(19), fill=MUTED)
        sx += 190
    d.line([(x0, 418), (x0 + 560, 418)], fill=LINE, width=2)
    d.text((x0, 440), cfg["tech"], font=sans(20, 500), fill=INK)
    d.text((x0, 520), cfg["url"], font=sans(20, 400), fill=PINK)

    # mustard panel with the skills chart
    bars = cfg.get("bars") or []
    if bars:
        px, py, pw, ph = 720, 72, 408, 483
        d.rounded_rectangle([px, py, px + pw, py + ph], radius=28, fill=ACCENT)
        ix = px + 40
        d.polygon([(ix, py + 62), (ix + 12, py + 41), (ix + 24, py + 62)], fill=ON_ACCENT)
        d.text((ix + 36, py + 36), cfg.get("chart_title", ""), font=sans(20, 650), fill=ON_ACCENT)
        d.text((ix, py + 74), cfg.get("chart_note", ""), font=sans(16), fill=ON_ACCENT)
        top = 1.0  # bars on a 0–100% scale, so lengths are honest
        y = py + 128
        max_w = pw - 80 - 64
        for name, v in bars:
            d.text((ix, y), name, font=sans(19, 550), fill=ON_ACCENT)
            by = y + 32
            d.rounded_rectangle([ix, by, ix + max_w, by + 12], radius=6, fill="#D99F1F")
            d.rounded_rectangle([ix, by, ix + max(12, max_w * v / top), by + 12], radius=6, fill=ON_ACCENT)
            d.text((ix + max_w + 14, by - 8), f"{round(v * 100)}%", font=serif(26), fill=ON_ACCENT)
            y += 66
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out, optimize=True)
    return out


if __name__ == "__main__":
    cfg = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")) if len(sys.argv) > 1 else CONFIG
    target = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).resolve().parents[1] / "assets" / "cover.png"
    print(make_cover(cfg, target))
