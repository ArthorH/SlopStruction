"""Model jobs: choose a font, recreate+translate a page, repair LaTeX."""
import json
import re

from models import ask, image_part
from render import FONTS

LANG_NAMES = {"en": "English", "pl": "Polish", "de": "German", "ru": "Russian",
              "fr": "French", "es": "Spanish", "it": "Italian", "uk": "Ukrainian"}

RECREATE_SYSTEM = r"""You recreate one page of a product manual in LaTeX, translated into {lang}.
The result must look like the original page: same layout, positions, colors, sizes.

Coordinates are in pt with the origin at the TOP-LEFT of the page; y grows downward.
Page size: {w} x {h} pt.

The preamble is fixed and already loads: fontspec (main font "{font}"), babel,
xcolor, graphicx, tikz, tcolorbox, fontawesome5, tabularx, multicol. It defines:
  \begin{{tikzpicture}}[page] ... \end{{tikzpicture}}   page-coordinate overlay
  \placeat{{x}}{{y}}{{width}}{{content}}      text block, top-left at (x,y), given width
  \placeimg{{x}}{{y}}{{w}}{{h}}{{file}}       image, top-left at (x,y)
Both macros are TikZ nodes: use them only inside the single tikzpicture.

Rules:
1. Output ONLY the page code in one ```latex block: ONE \begin{{tikzpicture}}[page] ... \end{{tikzpicture}}.
   No preamble, no notes, no plans, no commentary anywhere in the reply.
   Always complete the \end{{tikzpicture}}.
2. Translate ALL text into {lang}; every text line from the facts must appear, translated.
   Keep model numbers, units, numeric values, brand names.
   If the translation is longer, reduce the font size slightly so it still fits.
3. Raster images and complex drawings are provided as files (list below, with their exact
   bbox). Place each with \placeimg at its bbox. They contain no text: put any text
   that was on or around them back as translated text at the original position.
4. Rebuild every other visual element yourself: colored boxes, bars, rules, warning
   boxes, numbered step circles, tables, icons (fontawesome5, e.g. \faExclamationTriangle),
   arrows. Use \definecolor{{name}}{{HTML}}{{RRGGBB}} with the colors from the facts.
5. Set sizes with \fontsize{{size}}{{leading}}\selectfont. Escape LaTeX special characters.
6. Text facts come from the PDF text layer (exact text, position, size, color). If the
   facts have no text but the image shows text, read it from the image."""


def recreate_page(facts, assets, font, lang):
    system = RECREATE_SYSTEM.format(lang=LANG_NAMES.get(lang, lang), w=facts["width"],
                                    h=facts["height"], font=font)
    asset_list = "\n".join(f"- assets/{a['file']} ({a['kind']}) bbox={a['bbox']}" for a in assets) or "(none)"
    facts_view = {k: facts[k] for k in ("width", "height", "lines", "shapes")}
    content = [
        image_part(facts["image"]),
        {"type": "text", "text": f"The facts contain {len(facts['lines'])} text lines; all must appear, translated.\n"
                                 f"Image files:\n{asset_list}\n\nPage facts (JSON):\n"
                                 + json.dumps(facts_view, ensure_ascii=False)},
    ]
    return ask("recreate_page", system, content)


REPAIR_SYSTEM = r"""You fix LaTeX page bodies. You get the body (or an error description of what
went wrong) and details. Return ONE \begin{tikzpicture}[page] ... \end{tikzpicture} block in a
single ```latex block and nothing else. Macros \\placeat and \\placeimg exist."""


def repair(body_or_reply, problem, escalate=False):
    content = [{"type": "text", "text": f"PROBLEM:\n{problem}\n\nPREVIOUS OUTPUT:\n```\n{body_or_reply[:30000]}\n```"}]
    return ask("repair_latex", REPAIR_SYSTEM, content, escalate=escalate)


FONT_SYSTEM = """You choose the best-looking replacement for a manual's main text font.
Pick exactly one family from the allowed list, the one that looks most like the
text in the page image (shape, width, weight). Reply as JSON:
{"font": "<family from list>", "reason": "<short>"}"""


def choose_font(facts):
    fonts_used = sorted({ln["font"] for ln in facts["lines"]})
    content = [
        image_part(facts["image"]),
        {"type": "text", "text": f"Source fonts (from PDF): {fonts_used or 'unknown (outlined text)'}\n"
                                 f"Allowed families: {FONTS}"},
    ]
    text, usage = ask("choose_font", FONT_SYSTEM, content)
    m = re.search(r"\{.*\}", text, re.S)
    choice = json.loads(m.group(0)) if m else {}
    font = choice.get("font") if choice.get("font") in FONTS else FONTS[0]
    return font, choice.get("reason", ""), usage
