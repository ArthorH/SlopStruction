"""manual2latex prototype: recreate + translate a PDF manual page by page in LaTeX.

    python graph.py ../Examples/LXUT33.pdf --to en --pages 2-3
    python graph.py ../Examples/LXUT33.pdf --to en --pages 2 --dry-run   # no model calls
"""
import argparse
import json
import operator
import shutil
from pathlib import Path
from typing import Annotated, TypedDict

import pymupdf
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

import render
from figures import extract_assets
from ingest import ingest_page

REPAIR_ATTEMPTS = 2  # second attempt uses the escalation model


class State(TypedDict):
    pdf: str
    lang: str
    out: str
    pages: list[int]
    dry: bool
    font: str
    results: Annotated[list[dict], operator.add]


def prepare(state: State):
    out = Path(state["out"])
    (out / "cache").mkdir(parents=True, exist_ok=True)
    font_file = out / "font.json"
    if font_file.exists():
        return {"font": json.loads(font_file.read_text())["font"]}
    if state["dry"]:
        font, reason, usage = render.FONTS[0], "dry-run default", None
    else:
        from analyze import choose_font
        doc = pymupdf.open(state["pdf"])
        facts = ingest_page(doc, state["pages"][0], out / "cache")
        font, reason, usage = choose_font(facts)
    font_file.write_text(json.dumps({"font": font, "reason": reason, "usage": usage}, indent=1))
    return {"font": font}


def fan_out(state: State):
    return [Send("page", {**state, "pno": p}) for p in state["pages"]]


def page(task: dict):
    out = Path(task["out"])
    pno = task["pno"]
    name = f"p{pno + 1:04d}"
    pages_dir = out / "pages"
    (pages_dir / "assets").mkdir(parents=True, exist_ok=True)
    record_file = pages_dir / f"{name}.json"
    if record_file.exists():  # resume: page already done
        return {"results": [json.loads(record_file.read_text())]}

    doc = pymupdf.open(task["pdf"])
    facts = ingest_page(doc, pno, out / "cache")
    assets = extract_assets(doc, pno, pages_dir / "assets")
    w, h, font, lang = facts["width"], facts["height"], task["font"], task["lang"]
    usage, status = [], "ok"

    if task["dry"]:
        body = render.skeleton_body(facts, assets)
    else:
        from analyze import recreate_page
        reply, u = recreate_page(facts, assets, font, lang)
        usage.append(u)
        (pages_dir / f"{name}.reply.md").write_text(reply)
        body = render.extract_body(reply)

    tex = pages_dir / f"{name}.tex"
    attempts = 0
    status = "ok"
    while True:
        problem = "" if not body and not task["dry"] else None
        if problem is None:
            tex.write_text(render.document(w, h, font, lang, body))
            ok, log_tail, npages = render.compile_tex(tex)
            if ok and npages == 1:
                break
            problem = ("lualatex log tail:\n" + log_tail) if not ok else \
                f"output has {npages} pages; it must be exactly 1"
        if not task["dry"] and attempts < REPAIR_ATTEMPTS:
            from analyze import repair
            if not body:
                problem = "Your reply produced no complete \\begin{tikzpicture}[page] " \
                          "... \\end{tikzpicture} block (truncated or full of notes). " \
                          "Write the entire page code now, nothing else."
            reply, u = repair(body or reply, problem, escalate=attempts > 0)
            usage.append(u)
            body = render.extract_body(reply)
            attempts += 1
        elif body:  # compile/type failure out of repair attempts: keep page via fallback
            status = "fallback"
            shutil.copy(tex, tex.with_suffix(".failed.tex"))
            png = pages_dir / "assets" / f"{name}_orig.png"
            doc[pno].get_pixmap(dpi=150).save(png)
            tex.write_text(render.document(w, h, font, lang,
                                           render.fallback_body(facts, f"assets/{png.name}")))
            render.compile_tex(tex)
            break
        else:  # no body at all after repairs
            status = "failed"
            break

    pdf = tex.with_suffix(".pdf")
    record = {"page": pno + 1, "status": status, "repairs": attempts,
              "assets": len(assets), "pdf": str(pdf) if pdf.exists() else None, "usage": usage}
    record_file.write_text(json.dumps(record, indent=1))
    return {"results": [record]}


def assemble(state: State):
    """Stitch all per-page PDFs into the final manual (runs at the very end)."""
    out = Path(state["out"])
    results = sorted(state["results"], key=lambda r: r["page"])
    ready = [r for r in results if r["pdf"]]
    final = out / f"{Path(state['pdf']).stem}.{state['lang']}.pdf"
    if ready:
        n = render.merge([r["pdf"] for r in ready], final,
                         labels=[r["page"] for r in ready],
                         title=Path(state["pdf"]).stem, lang=state["lang"])
    else:
        final, n = None, 0
        print("assemble: no page PDFs to stitch")
    missing = [r["page"] for r in results if not r["pdf"]]
    cost = sum((u.get("cost") or 0) for r in results for u in r["usage"])
    report = {"pdf": state["pdf"], "lang": state["lang"], "font": state["font"],
              "output": str(final) if final else None, "pages": n,
              "missing_pages": missing, "cost_usd": round(cost, 4),
              "status": {r["page"]: r["status"] for r in results}}
    (out / "report.json").write_text(json.dumps(report, indent=1))
    print(json.dumps(report, indent=1))
    return {}


def build():
    g = StateGraph(State)
    g.add_node("prepare", prepare)
    g.add_node("page", page)
    g.add_node("assemble", assemble)
    g.add_edge(START, "prepare")
    g.add_conditional_edges("prepare", fan_out, ["page"])
    g.add_edge("page", "assemble")
    g.add_edge("assemble", END)
    return g.compile()


def parse_pages(spec, count):
    if not spec:
        return list(range(count))
    pages = set()
    for part in spec.split(","):
        a, _, b = part.partition("-")
        pages.update(range(int(a) - 1, int(b or a)))
    return sorted(p for p in pages if 0 <= p < count)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf")
    ap.add_argument("--to", default="en", help="target language code (default en)")
    ap.add_argument("--pages", help="e.g. 1-3,7 (1-based)")
    ap.add_argument("--out", help="output dir (default out/<stem>.<lang>)")
    ap.add_argument("--dry-run", action="store_true", help="no model calls: untranslated code-only pages")
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()

    pdf = str(Path(a.pdf).resolve())
    count = len(pymupdf.open(pdf))
    out = Path(a.out or Path(__file__).parent / "out" / f"{Path(pdf).stem}.{a.to}{'.dry' if a.dry_run else ''}")
    state = {"pdf": pdf, "lang": a.to, "out": str(out.resolve()), "dry": a.dry_run,
             "pages": parse_pages(a.pages, count), "font": "", "results": []}
    build().invoke(state, config={"max_concurrency": a.workers})


if __name__ == "__main__":
    main()
