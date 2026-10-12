# manual2latex — Software Specification

Version 0.2 · 12 Oct 2026 · status: **target spec — a simpler working prototype exists**;
see [`Prototype.md`](Prototype.md) for what is implemented and verified now

This document defines exactly what `manual2latex` does, what goes in, what comes
out, and how every stage behaves. It is derived from
[`Instruction.md`](Instruction.md) (architecture) and
[`Enviroment_instruction.md`](Enviroment_instruction.md) (tooling), and is
grounded in the 11 real manuals in `Examples/`. How each of those manuals must be
handled is in [`Example_corpus.md`](Example_corpus.md).

Decisions confirmed by the project owner are marked **[Confirmed]**. Defaults
chosen in this spec where nothing was specified are marked **[Decision]**; the
remaining unknowns are in §15.

### Changes in 0.2

| Topic | 0.1 | 0.2 **[Confirmed]** |
|---|---|---|
| Purpose | faithful copy | recreate manuals **so they can be translated**; translation itself is done by the owner (§1, §11) |
| Pages | 1 source page → 1 output page | unchanged: **one output page per page** |
| Languages | all languages kept | **one selected language** per run (`--lang`); other languages are dropped (§6.2) |
| Models | Anthropic SDK, one model | **OpenRouter**, model **chosen per task** with escalation (§9) |
| Fonts | fixed substitution table | **a model chooses the look-alike font**, code verifies it (§6.4) |
| Visual elements | crop many, rebuild some | **rebuild every visual element**; only photographs are embedded (§7) |

---

## 1. Purpose

`manual2latex` takes a **born-digital PDF product manual** and recreates it as
**LaTeX source that compiles to a PDF that looks like the original**, built so
that the text can be translated and the document re-rendered in the new
language without redoing the layout.

Concretely:

- every piece of text, including labels on drawings, is real, editable text —
  never pixels or outlined paths;
- every visual element (warning boxes, step badges, color bars, language tabs,
  icons, tables, barcodes, line drawings) is **rebuilt** in LaTeX/TikZ;
- only **photographs** are embedded as images, with any text inside them
  removed and placed back on top as real text;
- all text is exported to a strings file (§11) that can be translated and fed
  back to re-render the manual.

The pipeline **does not translate**. It produces the source-language
recreation and the hand-off files for translation.

## 2. Inputs

| Input | Required | Description |
|---|---|---|
| `pdf_path` | yes | Path to one PDF. One document per run. |
| `--lang CODE` | for multilingual PDFs | ISO 639-1 code of the language to recreate (e.g. `pl`, `en`). Optional for single-language PDFs. See §6.2. |
| `--out DIR` | no | Output directory. Default `out/<pdf-stem>-<lang>/`. |
| `--thread-id ID` | no | Checkpoint thread. Default: first 16 hex chars of SHA-256(PDF bytes) + `-<lang>`. Same input → same thread → automatic resume. |
| `--pages A-B` | no | Restrict processing to a source page range (1-based, inclusive). For development. |
| `--target-langs a,b` | no | Languages the manual will be translated into. Used only to require glyph coverage when choosing fonts (§6.4). Default: none. |
| `--models FILE` | no | Model routing file. Default `models.toml` (§9). |
| `--style-from FILE` | no | Reuse a `style.json` (and font decisions) from another run, e.g. manuals sharing a template. |
| `--restyle` | no | Ignore cached style guide and font decisions; run `style_pass` and `font_match` again. |
| `--resume` | no | Continue a run paused for human review (§8.9). |
| `--dry-run` | no | Run `ingest` and `language_map` only; print page kinds, the language map, and projected model calls per task. |
| `OPENROUTER_API_KEY` | yes (env) | Read from the environment only, never from files or arguments. |

### 2.1 Page kinds (assigned by `ingest`)

| `kind` | Detected by | Handling |
|---|---|---|
| `text` | ≥ 20 extractable chars | normal path |
| `outlined` — text converted to vector paths | < 20 chars **and** > 200 vector paths | OCR path (§8.3.3) |
| `scan` | < 20 chars **and** one image covering > 80% of the page **and** the OCR probe finds ≥ 20 chars | OCR path |
| `photo` — full-page photo | same as scan, but the OCR probe finds < 20 chars | page = one photograph element |
| `graphics` — anything else with < 20 chars | e.g. covers, logo/barcode-only pages | OCR probe; text found → OCR path, else graphic elements only |

The OCR probe is one cheap vision call per candidate page ("transcribe any
text; return nothing if none"). Its result is cached. Encrypted PDFs abort with
exit code 1 and no partial output.

All 11 example PDFs are unencrypted, rotation 0, one logical page per PDF page.
One (`LXUT33.pdf`) has no text layer at all.

## 3. Outputs

```
out/<pdf-stem>-<lang>/
├── main.tex              # entry point; \input's preamble and every page
├── preamble.tex          # generated from the style guide (§6.3)
├── fonts.tex             # fontspec setup from font decisions (§6.4)
├── pages/
│   ├── p0001.tex         # one file per OUTPUT page
│   └── ...
├── graphics/
│   ├── g_<hash>.tex      # rebuilt TikZ graphics (icons, badges, barcodes, drawings)
│   ├── g_<hash>.pdf      # complex vector drawings, text removed (§7.3)
│   └── photo_<hash>.jpg  # photographs, text removed (§7.4)
├── strings.<lang>.json   # every translatable string (§11)
├── page_map.json         # output page → source page, kept/dropped pages and why
├── main.pdf              # compiled result
├── report.json           # run summary (§12)
└── review.json           # elements awaiting/after human review (§8.9)
```

### 3.1 Page model **[Confirmed: one per page]**

- Every **kept** source page becomes exactly **one** output page, in source
  order. Each `pages/pNNNN.tex` ends with `\clearpage`, and its page size is the
  source page size (`geometry`, `paperwidth`/`paperheight` in pt).
- A page is **dropped** if, after language filtering (§6.2), it has no content
  left (only other-language text, or blank). Dropped pages are listed in
  `page_map.json` with the reason.
- Content never moves to another page. If it does not fit, the fit strategy in
  §11.3 applies, then a review item is raised.
- **Printed page numbers are renumbered** to the output sequence. Tables of
  contents, language indexes, and "see page N" references are re-pointed with
  `\label`/`\pageref` to the output page that now contains the target.

## 4. Architecture overview

A LangGraph `StateGraph` with an SQLite checkpointer.

```
ingest ─► language_map ─► style_pass ─► font_match ─► [Send × kept pages] analyze_page
                                                                       │
                       ┌───────────────────────────────────────────────┘
                       ▼
                   collect ─► stitch ─► build_graphics ─► render ─► compile
                                                            ▲         │ │
                                              repair_latex ◄┼── fail ─┘ │ ok
                                                            │           ▼
                                            apply_ir_fixes ◄┴── diffs ─ visual_check
                                                                        │ no diffs
                                                                        ▼
                                                    review_gate ─► export_strings ─► END
                                                    (interrupt)
                      compile loop ≤ 4 attempts · visual loop ≤ 3 rounds
```

Principle (from `Instruction.md`): **models do judgment, code does mechanics.**

| Node | Kind | Module | Model task (§9) |
|---|---|---|---|
| `ingest` | mechanics | `ingest.py` | `ocr_probe` (only for < 20-char pages) |
| `language_map` | mechanics | `ingest.py` | none |
| `style_pass` | judgment | `style.py` | `style_pass`, once per document |
| `font_match` | judgment + verification | `fonts.py` | `font_match`, once per source font family |
| `analyze_page` | judgment | `analyze.py` | `analyze_page` / `ocr_transcribe`, per kept page |
| `collect` | mechanics | `graph.py` | none |
| `stitch` | mechanics | `graph.py` | none |
| `build_graphics` | mechanics | `figures.py` | `image_edit` (optional, §7.4) |
| `render` | mechanics | `render.py` + `templates/` | none |
| `compile` | mechanics | `render.py` | none |
| `repair_latex` | judgment | `render.py` | `repair_latex`, on failure only |
| `visual_check` | judgment | `verify.py` | `visual_check`, per page that differs |
| `apply_ir_fixes` | mechanics | `verify.py` | none |
| `review_gate` | human | `graph.py` | none (`interrupt`) |
| `export_strings` | mechanics | `render.py` | none |

New modules relative to `Enviroment_instruction.md` step 6: `fonts.py`,
`models.py` (OpenRouter client and routing, §9).

## 5. State

State is a `TypedDict`. **No image or font bytes in state** — only paths. Every
checkpoint stores a copy of the whole state.

```python
class PipelineState(TypedDict):
    pdf_path: str
    pdf_sha: str
    lang: str                          # selected language
    out_dir: str
    page_count: int
    page_facts: list[str]              # cache/<sha>/facts/pNNNN.json
    page_images: list[str]             # cache/<sha>/pages/pNNNN.png
    language_map: LanguageMap          # per page: kept/dropped + selected regions
    style: StyleGuide | None
    fonts: list[FontDecision]
    page_irs: Annotated[list[PageIR], operator.add]   # reducer: append
    low_confidence: list[ElementRef]
    tex_path: str | None
    compile_ok: bool
    compile_log_tail: str
    compile_attempts: int              # cap 4
    visual_diffs: list[VisualDiff]
    visual_rounds: int                 # cap 3
    review_decisions: list[ReviewDecision]
    model_usage: Annotated[list[UsageRecord], operator.add]   # per call (§9.4)
```

## 6. Document-level stages

### 6.1 `ingest` — deterministic facts

For each source page `N`, using PyMuPDF (`import pymupdf`; the `fitz` alias is
deprecated in the installed 1.28.2):

1. Render `cache/<sha>/pages/pNNNN.png` at **150 dpi**, and on demand at
   **300 dpi** for font samples and photo crops.
2. Write `cache/<sha>/facts/pNNNN.json`:
   - page `width`, `height` (pt), `rotation`, `kind` (§2.1);
   - every text **span**: text, bbox, font, size, color (hex), flags;
   - every **image**: bbox, xref, pixel size (`get_image_info(xrefs=True)`);
   - **vector drawings** (`get_drawings()`): full path items are kept in a
     separate file `drawings/pNNNN.json` (needed for TikZ rebuilding, §7.2); the
     facts file holds clusters (bbox, fill/stroke colors, path count);
   - **links**: internal (target page) and external (URI);
   - candidate **tables** from `find_tables()`. Vertically adjacent fragments
     with identical column x-positions (±2 pt) are merged first
     (`find_tables()` splits at full-width section rows, e.g. Ninja p. 24).
3. Document facts: page count, PDF outline, metadata, font histogram, color
   histogram (character-weighted), scripts present, symbol-font usage.

Idempotent: reused when the cached file matches `pdf_sha`.

### 6.2 `language_map` — select one language **[Confirmed]**

Runs before any expensive model call, so pages in unwanted languages are never
analyzed.

1. Each text block (or OCR block for `outlined`/`scan` pages) gets a language
   from **`lingua-language-detector`** (deterministic, offline). Blocks under 3
   words inherit the language of their neighbors in reading order; blocks that
   are only numbers, model codes, units, or symbols are `neutral`.
2. Each page is classified:

   | Page class | Rule | Action |
   |---|---|---|
   | `selected` | ≥ 90% of language-tagged chars are `--lang` | keep |
   | `mixed` | contains `--lang` text and other-language text | keep; other-language blocks removed |
   | `neutral` | no language-tagged text (cover, pictogram pages, back cover) | keep |
   | `other` | language-tagged text, none in `--lang` | drop |
   | `blank` | no elements at all | drop |

3. If `--lang` is not given and more than one language covers > 5% of the
   characters, the run stops with exit code 1 and prints the languages found
   with their page ranges. If `--lang` is given but not found, same.
4. On `mixed` pages, removed-language regions are masked (filled white) in the
   page image given to models, and their spans are removed from the facts the
   model sees. Remaining content keeps its column grid and **flows from the top
   of the page** — no empty holes where the other languages were.
5. Multilingual tables (e.g. RYOBI p. 2: one row per language) keep only the
   rows in `--lang`, plus header rows.
6. Language index pages (e.g. Dyson guide p. 2) and language tab strips are
   handled as visual elements (§7.1), not dropped by this step.

### 6.3 `style_pass` — one style guide per document

Runs once, before per-page analysis, so every page maps to the same styles.

**Input:** document facts + images of up to **8 representative kept pages**
chosen by code (first, most distinct fill colors, most text, one per distinct
large-filled-rectangle color, last).

**Output:** `StyleGuide`:

```python
class StyleGuide(BaseModel):
    heading_levels: list[HeadingStyle]   # size, weight, color, bar fill, spacing
    palette: dict[str, str]              # name -> hex, e.g. {"brand": "#ef4235"}
    callouts: list[CalloutStyle]         # variant, frame/back color, icon, title style
    step_badge: BadgeStyle | None        # shape, fill, stroke, number style
    language_tab: TabStyle | None        # strip position, size, highlight color
    columns: int                         # dominant column count
    text_fonts: list[str]                # source font families to match (§6.4)
```

- **Colors come from extracted facts**; the model only names them.
- Rendered to `preamble.tex` from `templates/preamble.tex.j2`: `xcolor`
  definitions, one `tcolorbox` style per callout, `titlesec` formats, TikZ
  styles for badges and tabs.
- **Engine: always `lualatex`** **[Decision]**. Model-chosen fonts are
  OpenType/TrueType files loaded with `fontspec`, which `pdflatex` cannot do;
  `lualatex` also covers every script in the corpus for any later translation.

### 6.4 `font_match` — the model chooses the look-alike **[Confirmed]**

Proprietary fonts in the corpus (Arial, Verdana, Calibri, SegoePro, Gotham,
DysonFutura, FuturaBT, HelveticaNeue, CordiaNew, MadrasahArabic) cannot be
shipped. For each source **text** font family a model picks the replacement.
Symbol fonts (Webdings, Wingdings, Wingdings3, Dmk4, Y007C) are not text fonts
and go to icon rebuilding instead (§7.1).

**Procedure, per source family:**

1. **Sample (code).** Crop 3–6 real lines set in that family from the 300-dpi
   renders, covering each weight/style used (Book, Bold, Italic, Medium, Heavy…).
   Measure from the facts: average advance width per em, x-height-to-size
   ratio (from lowercase span bboxes), and weight distribution.
2. **Choose (model, task `font_match`).** The model gets the samples, the
   measurements, the family name, and the required character set: every
   character used in `--lang` text plus the alphabets of `--target-langs`. It
   returns:
   ```python
   class FontChoice(BaseModel):
       family: str                     # any freely licensed font family
       source: Literal["texlive", "google-fonts", "url"]
       url: str | None                 # required when source == "url"
       weights: dict[str, str]         # source style -> candidate style
       reason: str                     # what visual traits it matches
       alternatives: list[str]         # 2 ranked fallbacks
   ```
   The model may pick any font family. It is told that metric-compatible fonts
   (similar advance widths) are preferred, because pages are fixed-size and
   translations get longer.
3. **Verify (code).**
   - Install into project `fonts/<family>/` (Google Fonts download by family
     name, `tlmgr install`, or URL). The license must be OFL, Apache-2.0, GPL
     with font exception, or similar; otherwise → next alternative.
   - Check glyph coverage with `fontTools` against the required character set.
     Missing glyphs → next alternative.
   - Typeset the same sample text with `lualatex` at the measured size and
     compute the width ratio candidate / source.
4. **Confirm (model).** The model sees source sample and candidate render side
   by side and returns `accept` or `reject` + reason. Reject → next
   alternative, at most **3 candidates**; if all are rejected, the best by width
   ratio is used and a review item is raised.
5. **Record.** `FontDecision` (source family, chosen family, weights map,
   width ratio, rounds) goes to `cache/fonts/decisions.json`, **shared across
   documents**: once Arial is matched, all RYOBI and Canon manuals reuse that
   choice without another call. An owner override file
   `fonts/override.toml` always wins over the model.

`fonts.tex` is generated from the decisions (`\setmainfont`,
`\newfontfamily` per source family, `Path = fonts/<family>/`).

## 7. Visual element policy — rebuild everything **[Confirmed]**

Every visual element is recreated in LaTeX/TikZ. **The only exception is
photographs** (camera photos, product shots, food photos, photographic
textures), which cannot be recreated and are embedded.

### 7.1 Rebuilt natively

| Element | Rebuilt as |
|---|---|
| Callout / warning / note boxes | `tcolorbox` style from §6.3 |
| Step badges (numbered circles/squares) | TikZ style `step badge` |
| Heading bars, color bars, rules, background fills | TikZ / `tcolorbox` / page-style overlays |
| Language tab strip | TikZ overlay; the highlighted tab follows the language of the render (source or translation) |
| Language index pages | table of language codes → page references; after filtering it lists only languages present in the output |
| Tables | `tabularx` / `longtable`, cell fills and rules from facts |
| Icons from icon fonts (Webdings, Wingdings, Dmk4, Y007C…) | `fontawesome5` glyph if a match exists in `templates/iconmap.json`; otherwise the glyph outline converted to TikZ (§7.2) |
| Vector icons, arrows, ✓/✗, warning triangles, pictograms | `fontawesome5` match, otherwise TikZ from paths (§7.2) |
| Barcodes | TikZ from the bar paths (vector) — exact; raster barcodes decoded and regenerated |
| QR codes | decoded (OpenCV `QRCodeDetector`) and regenerated with the `qrcode` package; decoded text must match before acceptance |
| Logos, certification marks (CE, WEEE, NSF) | TikZ from paths if vector; raster logos embedded as images (treated like photographs) |
| Simple line drawings (≤ 400 path items, no shading/raster) | TikZ from paths (§7.2) |
| Complex line drawings (> 400 path items or shadings) | vector PDF crop **with all text removed** (§7.3) |

### 7.2 Vector → TikZ (code)

Path items from `drawings/pNNNN.json` (`l`, `c`, `re`, `qu`) become TikZ
`\draw` / `\fill` commands with the same coordinates (pt, origin at the element
bbox), stroke width, dash pattern, line cap/join, fill and stroke color, and
even-odd rule. Colors equal to a palette entry use the palette name, so a whole
manual can be recolored in one place. Output: `graphics/g_<hash>.tex`,
deduplicated by hash. Paths that are glyph outlines of text recognized by OCR
are **not** converted — that text is rendered as real text instead.

### 7.3 Complex vector drawings

1. Clip the region into a one-page PDF (`show_pdf_page`, `clip=bbox`).
2. Remove all text from it: add redaction annotations over every text span and
   every OCR'd glyph-outline area in the region, then
   `apply_redactions(images=PDF_REDACT_IMAGE_NONE,
   graphics=PDF_REDACT_LINE_ART_REMOVE_IF_COVERED,
   text=PDF_REDACT_TEXT_REMOVE)` (verified available in PyMuPDF 1.28.2). The
   redaction annotations are created with `fill=False` so nothing is painted
   over the art (`fill=None`, the default, paints white).
3. The removed text comes back as **anchored text labels**: absolutely
   positioned (TikZ overlay relative to the drawing), same size, color, font,
   rotation, and alignment as the source. Leader lines stay in the drawing.

### 7.4 Photographs

1. Extract the embedded image at native resolution (never upscale).
2. If text is drawn over the photo as PDF text → it is already separate; render
   it as anchored labels.
3. If text is **baked into the pixels** (found by the OCR probe inside the photo
   bbox), remove it:
   - the area behind the text is flat (pixel std-dev < 12 in a 6-px ring
     around the text boxes) → OpenCV `cv2.inpaint` (Telea);
   - otherwise → model task `image_edit` ("remove the text, change nothing
     else"), then code checks that SSIM outside the text boxes is ≥ 0.98, or
     the edit is rejected and a review item raised.
   The removed text is re-added as anchored labels.
4. Full-bleed photographic backgrounds (e.g. Ninja marble texture) are embedded
   once and reused on every page that has them.

## 8. Per-page stages

### 8.1 Fan-out

`font_match` returns `[Send("analyze_page", {"page": N}) for N in kept_pages]`.
Concurrency is capped at **8** simultaneous calls (OpenRouter rate limits
apply per key).

### 8.2 `analyze_page` input

The 150-dpi page image (other-language regions masked, §6.2), the filtered
facts JSON, the `StyleGuide`, and the **last 3 elements of the previous kept
page** for continuity. The model returns a `PageIR` via structured output. It
never emits LaTeX.

### 8.3 IR

#### 8.3.1 Element types

Every element has: `id` (`pNNNN_eKK`, source page number), `kind`, `bbox` (pt,
source coordinates), `order`, `confidence` (0.0–1.0), `lang`, `source_spans`,
and `string_ids` for every piece of text it contains (§11).

| `kind` | Extra fields | Rendered as |
|---|---|---|
| `heading` | `level` 1–4 | `\section`… with `heading_levels` style |
| `paragraph` | `runs` (text + bold/italic/color/link) | text |
| `list_item` | `marker`, `number`, `continues` | `itemize` / `enumerate` |
| `step` | `number`, `body`, `graphic_ids` | step badge + body |
| `callout` | `variant`, `title`, `body` | `tcolorbox` style |
| `table` | `rows`, `cols`, `cells`, `header_rows`, `cell_graphics` | `tabularx` / `longtable` |
| `graphic` | `method`: `tikz` \| `vector-pdf` \| `photo` \| `qr` \| `fontawesome`; `labels` | §7 |
| `label` | `anchor_id` (graphic it belongs to), `rotation`, `align` | TikZ overlay text |
| `decoration` | `role`: background, bar, rule, language-tab | TikZ overlay |
| `running` | `role`: header, footer, page-number | page style |

`graphic.method` is chosen by code from §7 rules; the model only says what the
region **is** (photo, drawing, icon, barcode, logo…).

#### 8.3.2 Region decision rules (model, in order; first match wins)

1. Barcodes, QR codes, logos, certification marks → `graphic`.
2. Photos, exploded views, schematics, wiring/installation drawings, product
   renderings → `graphic`. Every piece of text on or around it → `label`
   anchored to it (whether it is PDF text, outlined, or baked into pixels).
3. Boxes with a title/icon and a distinct frame or fill → `callout`. Variant
   from the signal word (UWAGA / OSTRZEŻENIE / WARNING / CAUTION / ВНИМАНИЕ…) or
   icon, not from color alone.
4. Numbered circles/squares followed by an instruction → `step`.
5. Glyphs from symbol fonts or Private Use Area code points → `graphic`
   (icon). **Never** emitted as literal characters.
6. Grid-aligned text with rules or cell fills → `table`.
7. Full-bleed backgrounds, bars, edge tabs, divider rules → `decoration`.
8. Other text → `heading` / `paragraph` / `list_item` / `running`.

**Text comes from the facts file, never from the model's reading of pixels**,
except on `outlined`/`scan` pages and baked-in photo text (§8.3.3).

#### 8.3.3 OCR path

For `outlined`/`scan` pages and baked-in text: model task `ocr_transcribe`
returns text **with bounding boxes** and font size/color estimates; these
replace facts spans. Confidence is capped at **0.8**. Glyph-outline paths
covered by OCR boxes are excluded from TikZ conversion (§7.2) and removed from
vector crops (§7.3).

### 8.4 `collect`

1. Sort `page_irs` by page.
2. Validate each `PageIR`. On failure: one retry with the same model, then one
   with the escalation model (§9.2); still failing → page rendered as a raster
   fallback (still one output page), listed in review.
3. `low_confidence` = elements with `confidence < 0.70`.

### 8.5 `stitch` — document-level fixes

- **Numbered lists/steps** continuing across kept pages or columns: carry the
  counter (`enumerate` with `resume`/`start=`).
- **Split paragraphs** across pages: continuation without indent.
- **Running headers/footers** identical on ≥ 50% of kept pages → page style.
  Page numbers become `\thepage` (renumbered, §3.1).
- **PDF outline**: used for `hyperref` bookmarks only if ≥ 50% of its entries
  match a `heading` on the target page; otherwise bookmarks are built from
  headings. Entries pointing at dropped pages are removed.
- **Links and page references**: link rects attach to the text run they
  overlap (> 50% area) → `\hyperlink`. Textual references ("str. 35",
  "page 12") whose target page is known become `\pageref`. Targets on dropped
  pages are left as text and listed in review.

### 8.6 `build_graphics`

Applies §7 to every `graphic`, `decoration`, and icon: TikZ conversion, vector
crops with text removed, photo extraction and text removal, QR regeneration.
Everything is hashed and deduplicated.

### 8.7 `render` and `compile` loop

**Render** is pure templating: `PageIR` + `StyleGuide` + `FontDecision`s +
strings file → `pages/pNNNN.tex` via Jinja2 templates (one per element kind).
Text is LaTeX-escaped. Body text flows inside `multicol` with the detected
column count; `decoration`, anchored `graphic`s and their `label`s are placed
absolutely with TikZ `remember picture, overlay`.

**Compile:** `latexmk -lualatex -interaction=nonstopmode -halt-on-error`,
timeout 300 s, TeX binaries called by absolute path
(`~/texlive/2026/bin/x86_64-linux`; Python's PATH may differ from the shell).

- Success → `visual_check`.
- Failure → `repair_latex` (task `repair_latex`): last 200 log lines + ±20
  lines around the error. Returns a fix to the template output **for that
  element**; `compile_attempts += 1`.
- 4 failed attempts → offending page replaced with a raster fallback, logged,
  pipeline continues.
- Missing `.sty` or font file → environment error naming the package/font, no
  repair attempt.

### 8.8 `visual_check` loop

1. Rasterize `main.pdf` at 150 dpi and pair each output page with its source
   page via `page_map.json`.
2. `selected`/`neutral` pages: grayscale **SSIM** against the source. ≥ 0.85
   passes without a model call.
3. `mixed` pages (content reflowed by design) and pages below threshold: task
   `visual_check` gets both images and returns concrete `VisualDiff`s tied to
   element ids ("p0012_e04: warning box is missing its icon").
4. `apply_ir_fixes` changes the **IR, never the `.tex`**, then re-renders.
5. Cap 3 rounds; remaining diffs go to review.

Font substitution lowers SSIM somewhat; the 0.85 threshold is a starting point
to tune on the corpus.

### 8.9 `review_gate`

If there are low-confidence elements, unresolved diffs, rejected fonts,
overflows, or unresolved page references, the node calls `interrupt()`. State is
checkpointed; the process exits with code 3 and prints the path to
`review.json`. The owner sets each item to `accept`, `change_kind`,
`edit_text`, or `override_font`, then runs `--resume`. The graph re-renders and
re-compiles (normal caps apply).

## 9. Models via OpenRouter **[Confirmed]**

### 9.1 Client

All model calls go through OpenRouter's OpenAI-compatible API,
`https://openrouter.ai/api/v1`, using `langchain-openai`'s `ChatOpenAI` with
`base_url` set to that URL and `api_key` from `OPENROUTER_API_KEY`. Structured
output uses JSON-schema mode generated from the Pydantic models. `models.py` is
the only module that knows about providers; nodes ask for a **task**, not a
model.

### 9.2 Routing: model chosen per task

`models.toml` maps each task to a model, by need. Defaults (prices per million
input/output tokens, from the OpenRouter model list on 12 Oct 2026):

| Task | What it needs | Default model | $ in/out | Escalation model |
|---|---|---|---|---|
| `ocr_probe` | vision, cheap, yes/no + short text | `anthropic/claude-haiku-5.5` | 0.10 / 0.50 | — |
| `ocr_transcribe` | vision, accurate text + bboxes | `google/gemini-3.8-flash` | 0.75 / 3.75 | `anthropic/claude-sonnet-5.5` |
| `style_pass` | vision, design judgment; once per document | `anthropic/claude-opus-5.5` | 4 / 20 | — |
| `font_match` | vision, typographic judgment; once per font family, cached across documents | `anthropic/claude-opus-5.5` | 4 / 20 | — |
| `analyze_page` | vision + structured output; bulk (every kept page) | `google/gemini-3.8-flash` | 0.75 / 3.75 | `anthropic/claude-sonnet-5.5` |
| `repair_latex` | text, LaTeX knowledge | `anthropic/claude-haiku-5.5` | 0.10 / 0.50 | `anthropic/claude-sonnet-5.5` |
| `visual_check` | vision, two-image comparison | `anthropic/claude-sonnet-5.5` | 2 / 10 | — |
| `image_edit` | image in → image out (text removal from photos) | `google/gemini-nano-banana-2.1` | 1.5 / 7.5 | — |

```toml
# models.toml
base_url = "https://openrouter.ai/api/v1"

[tasks.analyze_page]
model    = "google/gemini-3.8-flash"
escalate = "anthropic/claude-sonnet-5.5"
needs    = ["image", "structured_outputs"]
# ... one table per task
```

**Escalation triggers** (to the task's `escalate` model, once):

- `PageIR` fails schema validation after one retry;
- more than **25%** of a page's elements have `confidence < 0.70`;
- `ocr_transcribe` returns boxes covering < 50% of the glyph-path area on an
  `outlined` page;
- `repair_latex` fails 2 attempts in a row.

### 9.3 Startup check

Before the graph starts, `models.py` fetches `GET /api/v1/models` and checks
that every configured model exists and supports what its task `needs`
(`image` input, `structured_outputs`, image output for `image_edit`). Any
mismatch → exit 1 with the task and model named. A missing
`OPENROUTER_API_KEY` → exit 1.

### 9.4 Cost tracking

Each call records task, model, tokens, and the cost OpenRouter reports for it
(usage accounting enabled in the request) into `model_usage`. `report.json`
sums cost per task and per page. `--dry-run` prints projected calls per task.

## 10. Caching and resumability

| What | Where | Invalidated when |
|---|---|---|
| Graph checkpoints | `cache/checkpoints.sqlite` | never automatically |
| Renders, facts, drawings | `cache/<sha>/` | PDF bytes change |
| OCR probe / transcription | `cache/<sha>/ocr/` | PDF or `ocr_*` model changes |
| Language map | `cache/<sha>/language_map.json` | PDF changes |
| Style guide | `cache/<sha>/style.json` | PDF changes or `--restyle` |
| Font decisions | `cache/fonts/decisions.json` (all documents) | `--restyle` or override file |
| Page IR | `cache/<sha>/ir/<lang>/pNNNN.json` | PDF, style, prompt version, or `analyze_page` model change |

The prompt version is a constant in `analyze.py`. A crash resumes from the last
checkpoint.

## 11. Translation hand-off

The pipeline stops at the source-language recreation. Translation is done by
the owner; these files make it possible without touching layout.

### 11.1 `strings.<lang>.json`

Every piece of rendered text — paragraphs, headings, table cells, callout
titles, labels on drawings and photos, running headers — is one entry:

```json
"p0012_e04_s01": {
  "text": "Nie używaj urządzenia, gdy {icon:g_3fa1} świeci na <b>czerwono</b>.",
  "kind": "callout-body",
  "page": 12,
  "max_width_pt": 182.4,
  "max_lines": 3
}
```

- Inline formatting uses `<b>`, `<i>`, `<color:NAME>`, `<link:TARGET>` tags;
  inline icons use `{icon:ID}`; page references use `{pageref:LABEL}`. These
  placeholders must be kept by translators; `render` validates them.
- `max_width_pt` / `max_lines` tell the translator the space available (labels
  and table cells are tight; flowing body text is not).

### 11.2 Re-rendering a translation

```bash
python graph.py manual.pdf --lang pl --render-strings strings.de.json --render-lang de
```

Runs **render → compile → fit check** only, with no analysis calls: same IR,
same graphics, new text. `--render-lang` sets `babel` language (hyphenation),
the highlighted language tab, and the output folder suffix. Font coverage for
`de` is guaranteed only if `de` was in `--target-langs` when fonts were chosen;
otherwise missing glyphs are reported before compiling.

### 11.3 Fit strategy (translations are usually longer)

Applied per text container, in order, until it fits:

1. normal hyphenation for the render language, `\emergencystretch`;
2. reduce paragraph and list spacing down to 50%;
3. reduce font size in 2.5% steps down to **85%** of the source size;
4. raise an `overflow` review item (content is never moved to another page).

Anchored labels have a fixed box (source bbox width): shrink to 80%, then
flag.

## 12. `report.json`

Pages: source count, kept, dropped (with reasons), kind and language class per
page. Elements by kind; graphics by method (TikZ / vector-pdf / photo / qr /
fontawesome); photos with text removed and how. Font decisions. Compile
attempts, visual rounds, final SSIM per page. Fallback pages. Review items.
Model calls, tokens, and cost per task. Wall time.

| Exit code | Meaning |
|---|---|
| 0 | finished, nothing to review |
| 1 | fatal: encrypted PDF, missing key, model check failed, language not found/ambiguous, TeX not found |
| 2 | finished with fallback pages |
| 3 | paused for human review |

## 13. Quality measurement

Ground truth: hand-labeled pages listed in `Example_corpus.md`.

| Metric | Definition | Initial target |
|---|---|---|
| Language filtering | kept pages/blocks in `--lang` vs. labeled | 100% of labeled `--lang` blocks kept, 0 other-language blocks kept |
| Text accuracy | 1 − CER of output text vs. facts text (text pages) | ≥ 0.99 |
| OCR accuracy | same vs. hand transcription (outlined/scan pages, baked-in text) | ≥ 0.97 |
| Text extractability | share of visible source text that is real text in `main.pdf` | 100% |
| Rebuild rate | non-photo graphics rebuilt (TikZ/fontawesome/qr) vs. vector-pdf crops | report; vector-pdf only for > 400-path drawings |
| Visual similarity | median SSIM, `selected`/`neutral` pages | ≥ 0.85 |
| Silent misclassification | photo/drawing labeled as text with confidence ≥ 0.70 | 0 |

## 14. Build order

1. `ingest` → `analyze_page` (one page) → `render`. Suggested first page:
   `instrukcja-obslugi-AMICA-ED975396BA.pdf` p. 9 (single language, single
   color, two pictograms to rebuild as TikZ).
2. `models.py` with routing + startup check.
3. `language_map` (needed before any multilingual file).
4. `style_pass`, `font_match`, fan-out.
5. `build_graphics`: TikZ conversion first, then vector-pdf text removal, then
   photo text removal.
6. `compile` loop, `visual_check` loop, `review_gate`.
7. `export_strings` and the `--render-strings` path.
8. OCR path (`LXUT33.pdf`).

## 15. Open questions

| # | Question | Current default |
|---|---|---|
| Q1 | Marketing/price content (Dyson catalog, Ninja recipes) in scope? | in scope, same rules |
| Q2 | Preserve internal links and PDF bookmarks (Canon: 1,321 links, 129 bookmarks)? | yes, via `hyperref`, re-pointed to output pages |
| Q3 | Default `--target-langs` for font coverage? | none; set per run |
| Q4 | Raster logos: embed (current) or ask the owner for vector originals? | embed |
| Q5 | Budget cap per run (stop when OpenRouter cost exceeds X)? | none |

## 16. Environment additions this spec requires

Relative to the environment installed per `Enviroment_instruction.md`:

```bash
# Python (in .venv)
pip install langchain-openai lingua-language-detector fonttools opencv-python-headless
pip freeze > requirements.txt

# API key: OpenRouter instead of Anthropic
export OPENROUTER_API_KEY="sk-or-..."      # add to ~/.bashrc

# TeX Live: lualatex engine and font loading
tlmgr install fontspec qrcode collection-langpolish babel-polish
```

`langchain-anthropic` and `anthropic` (installed earlier) are no longer used.
Fonts chosen by `font_match` are downloaded into `fonts/` at run time; the TeX
Live font packages available for that are `montserrat`, `carlito`, `dejavu`,
`tex-gyre`, `noto`, `opensans` (checked with `tlmgr info`); others (e.g.
Liberation, Selawik, Jost) come from Google Fonts or their project pages.
