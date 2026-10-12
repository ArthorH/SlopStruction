"""Page assets the model may place as-is.

Raster images (photos, logos) stay original. Complex vector drawings are cropped
as vector PDF. Both are taken from a copy of the page with all text removed, so
the translated text can be placed on top without the original showing through.
"""
from pathlib import Path

import pymupdf

MIN_SIDE = 12          # pt; smaller images are ignored
DRAWING_MIN_PATHS = 40  # vector clusters with fewer paths are left for TikZ
DRAWING_MIN_AREA = 0.01  # share of page area


def textless_copy(doc, pno):
    tmp = pymupdf.open()
    tmp.insert_pdf(doc, from_page=pno, to_page=pno)
    page = tmp[0]
    for block in page.get_text("dict")["blocks"]:
        if block["type"] == 0:
            page.add_redact_annot(block["bbox"], fill=False)
    page.apply_redactions(
        images=pymupdf.PDF_REDACT_IMAGE_NONE,
        graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
        text=pymupdf.PDF_REDACT_TEXT_REMOVE,
    )
    return tmp


def _clip(rect, page_rect):
    r = pymupdf.Rect(rect) & page_rect
    return r if not r.is_empty else None


def extract_assets(doc, pno, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    src = doc[pno]
    tmp = textless_copy(doc, pno)
    page = tmp[0]
    assets = []

    for i, info in enumerate(src.get_image_info()):
        r = _clip(info["bbox"], src.rect)
        if r is None or r.width < MIN_SIDE or r.height < MIN_SIDE:
            continue
        name = f"p{pno + 1:04d}_img{i + 1:02d}.png"
        page.get_pixmap(clip=r, dpi=200).save(out_dir / name)
        assets.append({"file": name, "kind": "raster", "bbox": [round(v, 1) for v in r]})

    page_area = src.rect.width * src.rect.height
    drawings = src.get_drawings()
    for i, r in enumerate(src.cluster_drawings(drawings=drawings)):
        r = _clip(r, src.rect)
        if r is None or r.width * r.height < DRAWING_MIN_AREA * page_area:
            continue
        paths = sum(1 for d in drawings if pymupdf.Rect(d["rect"]).intersects(r))
        if paths < DRAWING_MIN_PATHS:
            continue
        name = f"p{pno + 1:04d}_vec{i + 1:02d}.pdf"
        crop = pymupdf.open()
        crop.new_page(width=r.width, height=r.height).show_pdf_page(
            pymupdf.Rect(0, 0, r.width, r.height), tmp, 0, clip=r)
        crop.save(out_dir / name)
        assets.append({"file": name, "kind": "vector", "paths": paths,
                       "bbox": [round(v, 1) for v in r]})
    return assets
