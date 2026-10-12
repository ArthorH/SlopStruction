"""LaTeX side: preamble, placement macros, compile, fallback, merge."""
import re
import subprocess
from pathlib import Path

import pymupdf

TEXBIN = Path.home() / "texlive/2026/bin/x86_64-linux"
FONTS = ["TeX Gyre Heros", "TeX Gyre Adventor", "TeX Gyre Termes", "DejaVu Sans",
         "DejaVu Sans Condensed", "Carlito", "Montserrat", "Open Sans", "Latin Modern Sans"]
BABEL = {"en": "english", "pl": "polish", "de": "ngerman", "ru": "russian"}

PREAMBLE = r"""\documentclass{article}
\usepackage[paperwidth=%(w)spt,paperheight=%(h)spt,margin=0pt]{geometry}
\usepackage{fontspec}
\setmainfont{%(font)s}
%(babel)s
\usepackage{xcolor,graphicx,tikz,tcolorbox,fontawesome5,tabularx,multicol}
\pagestyle{empty}
\setlength{\parindent}{0pt}
%% Page coordinates: pt, origin top-left, y grows downward.
\tikzset{page/.style={remember picture,overlay,x=1pt,y=-1pt,shift={(current page.north west)}}}
%% Use inside \begin{tikzpicture}[page] ... \end{tikzpicture}
\newcommand{\placeat}[4]{\node[anchor=north west,inner sep=0pt,text width=#3pt,align=left] at (#1,#2) {#4};}
\newcommand{\placeimg}[5]{\node[anchor=north west,inner sep=0pt] at (#1,#2) {\includegraphics[width=#3pt,height=#4pt]{#5}};}
"""


def preamble(w, h, font, lang):
    babel = f"\\usepackage[{BABEL[lang]}]{{babel}}" if lang in BABEL else ""
    return PREAMBLE % {"w": w, "h": h, "font": font, "babel": babel}


def document(w, h, font, lang, body):
    return preamble(w, h, font, lang) + "\\begin{document}\n" + body.strip() + "\n\\end{document}\n"


def extract_body(text):
    """Model reply -> exactly one complete \\begin{tikzpicture}...\\end{tikzpicture}.
    Notes, plans, and reasoning around the code are dropped. Returns "" when the
    block is missing or truncated, so the caller retries instead of compiling it."""
    blocks = re.findall(r"```(?:latex|tex)?\s*(.*?)```", text, re.S)
    with_tikz = [b for b in blocks if "\\begin{tikzpicture}" in b]
    cand = max(with_tikz or blocks, key=len, default="") if blocks else text
    m = re.search(r"\\begin\{tikzpicture\}.*?\\end\{tikzpicture\}", cand, re.S)
    if m:
        return m.group(0)
    return cand.strip() if "\\begin{tikzpicture}" in cand else ""


def compile_tex(tex_path: Path, timeout=180):
    """Two direct lualatex passes (remember-picture overlays need the second).
    Returns (ok, log_tail, page_count)."""
    cmd = [str(TEXBIN / "lualatex"), "-interaction=nonstopmode",
           "-halt-on-error", tex_path.name]
    try:
        for _ in range(2):
            subprocess.run(cmd, cwd=tex_path.parent, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, "timeout", 0
    pdf = tex_path.with_suffix(".pdf")
    log = tex_path.with_suffix(".log")
    tail = "\n".join(log.read_text(errors="replace").splitlines()[-80:]) if log.exists() else ""
    if not pdf.exists() or "! " in tail:
        return False, tail, 0
    return True, tail, len(pymupdf.open(pdf))


def esc(s):
    rep = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#",
           "_": r"\_", "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}
    s = "".join(rep.get(c, c) for c in s)
    return "".join(c for c in s if not 0xE000 <= ord(c) <= 0xF8FF)  # drop icon-font glyphs


def skeleton_body(facts, assets):
    """Code-only recreation, untranslated. Used by --dry-run to test the mechanics."""
    out = ["\\begin{tikzpicture}[page]"]
    for i, s in enumerate(reversed(facts["shapes"])):
        if s["fill"] and s["items"] <= 4:
            x0, y0, x1, y1 = s["bbox"]
            out.append(f"\\definecolor{{s{i}}}{{HTML}}{{{s['fill'][1:]}}}"
                       f"\\fill[s{i}] ({x0},{y0}) rectangle ({x1},{y1});")
    for a in assets:
        x0, y0, x1, y1 = a["bbox"]
        out.append(f"\\placeimg{{{x0}}}{{{y0}}}{{{x1 - x0:.1f}}}{{{y1 - y0:.1f}}}{{assets/{a['file']}}}")
    for i, ln in enumerate(facts["lines"]):
        if ln["dir"] != [1.0, 0.0]:
            continue
        x0, y0, x1, y1 = ln["bbox"]
        size = ln["size"]
        text = esc(ln["text"])
        if ln["bold"]:
            text = f"\\textbf{{{text}}}"
        out.append(f"\\definecolor{{t{i}}}{{HTML}}{{{ln['color'][1:]}}}"
                   f"\\placeat{{{x0}}}{{{y0}}}{{{max(x1 - x0, 5) * 1.3:.1f}}}"
                   f"{{\\color{{t{i}}}\\fontsize{{{size}}}{{{size * 1.15:.1f}}}\\selectfont {text}}}")
    out.append("\\end{tikzpicture}")
    return "\n".join(out)


def fallback_body(facts, png_name):
    w, h = facts["width"], facts["height"]
    return f"\\begin{{tikzpicture}}[page]\\placeimg{{0}}{{0}}{{{w}}}{{{h}}}{{{png_name}}}\\end{{tikzpicture}}"


def merge(pdfs, out_pdf, labels=None, title=None, lang=None):
    """Stitch per-page PDFs into one document with a bookmark per source page."""
    doc = pymupdf.open()
    toc = []
    for i, p in enumerate(pdfs):
        src = pymupdf.open(p)
        doc.insert_pdf(src, from_page=0, to_page=0)
        label = f"page {labels[i]}" if labels else Path(p).stem
        toc.append([1, label, len(doc)])
    doc.set_toc(toc)
    meta = doc.metadata or {}
    meta.update({"title": title or out_pdf.stem, "creator": "manual2latex",
                 "producer": "manual2latex"})
    if lang:
        meta["subject"] = f"recreated manual, language: {lang}"
    doc.set_metadata(meta)
    doc.save(out_pdf)
    return len(doc)
