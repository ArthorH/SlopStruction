"""Deterministic page facts: render, text lines, simple shapes."""
import json
from pathlib import Path

import pymupdf

MAX_SHAPES = 150


def hexcolor(c):
    if c is None:
        return None
    if isinstance(c, int):
        return f"#{c:06x}"
    return "#" + "".join(f"{round(v * 255):02x}" for v in c[:3])


def text_lines(page):
    lines = []
    for block in page.get_text("dict")["blocks"]:
        if block["type"] != 0:
            continue
        for line in block["lines"]:
            spans = [s for s in line["spans"] if s["text"].strip()]
            if not spans:
                continue
            first = spans[0]
            lines.append({
                "bbox": [round(v, 1) for v in line["bbox"]],
                "text": "".join(s["text"] for s in spans),
                "font": first["font"],
                "size": round(first["size"], 1),
                "color": hexcolor(first["color"]),
                "bold": bool(first["flags"] & 16) or "bold" in first["font"].lower(),
                "dir": [round(v, 2) for v in line["dir"]],
            })
    return lines


def simple_shapes(page):
    """Filled rectangles and lines: the boxes, bars and rules a model should rebuild."""
    shapes = []
    for d in page.get_drawings():
        r = d["rect"]
        if r.width < 2 and r.height < 2:
            continue
        shapes.append({
            "bbox": [round(v, 1) for v in r],
            "fill": hexcolor(d.get("fill")),
            "stroke": hexcolor(d.get("color")),
            "width": round(d.get("width") or 0, 2),
            "items": len(d["items"]),
        })
    shapes.sort(key=lambda s: (s["bbox"][2] - s["bbox"][0]) * (s["bbox"][3] - s["bbox"][1]), reverse=True)
    return shapes[:MAX_SHAPES]


def ingest_page(doc, pno, cache_dir: Path, dpi=110):
    """Writes page PNG + facts JSON; returns the facts dict."""
    facts_path = cache_dir / f"p{pno + 1:04d}.json"
    if facts_path.exists():
        return json.loads(facts_path.read_text())
    page = doc[pno]
    png = cache_dir / f"p{pno + 1:04d}.png"
    page.get_pixmap(dpi=dpi).save(png)
    facts = {
        "page": pno + 1,
        "width": round(page.rect.width, 2),
        "height": round(page.rect.height, 2),
        "image": str(png),
        "lines": text_lines(page),
        "shapes": simple_shapes(page),
    }
    facts_path.write_text(json.dumps(facts, ensure_ascii=False, indent=1))
    return facts
