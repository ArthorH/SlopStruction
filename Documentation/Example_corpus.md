# manual2latex — Example Corpus and Expected Behavior

Version 0.2 · companion to [`Specification.md`](Specification.md) v0.2. For each
PDF in `Examples/`: what is measurably in the file, what makes it hard, and
**exactly what the pipeline must do with it**. Section numbers (§) refer to
`Specification.md`.

Numbers were measured with PyMuPDF 1.28.2 on 12 Oct 2026. Page numbers are
**1-based source PDF page indexes**, not printed folios. Output page numbers
differ after language filtering (§3.1); `page_map.json` maps them.

Language page ranges below come from a quick Polish-marker heuristic
(frequency of "ł", "się", " nie ") and are **indicative**. The real
`language_map` (§6.2) uses `lingua-language-detector` per block; the
ground-truth labels (end of this file) are what tests check against.

## Corpus summary

| File | Pages | Page size (pt) | Text chars | Raster imgs | Vector paths | Languages | Hardest feature |
|---|---|---|---|---|---|---|---|
| `EOS_2000D_Instruction_Manual_PL.pdf` | 326 | 298×420 | 403,815 | 382 | 43,623 | PL | icon fonts, 1,321 internal links |
| `instrukcja-obslugi-RYOBI-RY18LT23A-0.pdf` | 120 | 462×637 | 524,289 | 532 | 31,766 | ~25 | language selection, pictogram pages |
| `instrukcja-obsluga-RYOBI-R18GN18-0.pdf` | 104 | 462×637 | 474,006 | 470 | 22,080 | ~25 | same template |
| `Instrukcja-obslugi-RYOBI-RLM36X41H50PG.pdf` | 192 | 462×637 | 679,273 | 783 | 104,671 | ~25 | same template, most paths |
| `instrukcja-obslugi-RYOBI-RY36BI1800A-250.pdf` | 220 | 462×637 | 681,140 | 430 | 76,378 | ~25 | same template, most pages |
| `instrukcja-obslugi-AMICA-ED975396BA.pdf` | 44 | 420×595 (A5) | 65,195 | 7 | 8,172 | PL | baseline: simple |
| `SL400EU_Przepisy.pdf` (Ninja) | 46 | 420×595 (A5) | 56,954 | 209 | 7,984 | PL | photo backgrounds, recipe layout, QR |
| `airblade-katalog-suszarek-2021-PL.pdf` | 32 | 482×652 | 17,489 | 50 | 484 | PL | full-page photos, brochure |
| `airblade_v_installation_guide.pdf` | 83 | 842×595 (A4 landscape) | 413,699 | **0** | 3,538 | 40+ incl. RTL | language selection on mixed pages |
| `LXUT33.pdf` (UNI-T) | 16 | 595×842 (A4) | **0** | 5 | 40,023 | PL + EN halves | **all text outlined** |
| `XBOX SERIES X + S MANUAL EN - AU NZ.pdf` | 12 | 425×312 | 39,827 | **0** | 401 | EN | 6 pt text, vector barcode |

Every file: unencrypted, rotation 0, uniform page size, one logical page per
PDF page.

### Source text fonts → `font_match` (§6.4)

The model chooses each replacement; these are the families it will be asked
about. Decisions are cached across documents, so each family is matched once.

| Source family (styles seen) | Used in | Needs |
|---|---|---|
| Arial / ArialMT (Regular, Bold, Italic, BoldItalic) | EOS, all RYOBI, UNI-T* | Latin incl. Polish; matched once, reused by 5 files |
| Arial Narrow (Regular, Bold) | RYOBI RLM36X41H50PG, RY18LT23A | condensed width |
| Verdana (Regular, Bold, Italic) | AMICA | wide humanist sans |
| Calibri (Regular, Bold) | AMICA (few spans) | |
| Gotham (Book, Bold, Light, Black) | Ninja | 4 weights |
| DysonFutura (Book, Light, Medium, Heavy) | Dyson catalog | geometric sans, 4 weights |
| FuturaBT (Book, Medium, Heavy) | Dyson guide | geometric sans |
| HelveticaNeue | Dyson guide | |
| CordiaNew / MadrasahArabic | Dyson guide | only if `--lang th` / `--lang ar` |
| SegoePro (Regular, Bold, SemiLight) | Xbox | 6 pt legibility |

\* UNI-T has no font information (outlined text); the model judges from the
rendered glyphs alone.

**Not text fonts** (→ icons, §7.1): Webdings, Wingdings, Wingdings3, Dmk4,
Y007C (all in EOS).

### Feature coverage

| Feature (§) | Exercised by |
|---|---|
| Language selection, whole pages (§6.2) | all 4 RYOBI, UNI-T |
| Language selection, `mixed` pages (§6.2) | Dyson guide, RYOBI p. 2 |
| Page renumbering + re-pointed references (§3.1, §8.5) | RYOBI, Dyson guide (language index), EOS (links) |
| OCR path (§8.3.3) | UNI-T (14 of 16 pages outlined, 2 graphics pages) |
| Full-page photo, *not* a scan (§2.1) | Dyson catalog pp. 5, 21, 23 |
| Icon fonts → icons (§7.1) | EOS |
| Vector → TikZ (§7.2) | RYOBI pictograms, Xbox triangles and barcode, AMICA marks |
| Complex drawings, text removed (§7.3) | Dyson guide pp. 3–4, UNI-T schematics, EOS screen diagrams |
| Photos with text (§7.4) | Ninja (labels on food photos), EOS (cover), Dyson catalog |
| QR regeneration (§7.1) | Ninja p. 46 |
| Tables (§8.3.1) | AMICA p. 23, Ninja p. 24 (split), UNI-T p. 6 (no text layer), Xbox p. 9 |
| Callouts / steps | Xbox, RYOBI, Dyson guide, EOS / RYOBI, Ninja, Dyson guide |
| Junk PDF outline (§8.5) | Dyson guide |
| Tight translation fit (§11.3) | Xbox (6 pt, 3 columns), EOS (7–8 pt), labels on all drawings |

---

## 1. `instrukcja-obslugi-AMICA-ED975396BA.pdf` — baseline

**What it is.** Built-in oven manual, Polish only, 44 A5 pages. Verdana 10 pt
body, one text color (`#231f20`). 7 raster images; drawings are vector.

**Notable pages.**
- p. 1: cover — logo, title, a list of 8 model codes, a boxed warning with a
  book icon.
- p. 3: table of contents with dotted leaders and underlined entries.
- p. 9: "ROZPAKOWANIE" / "USUWANIE ZUŻYTYCH URZĄDZEŃ" — two headings, body
  text, recycling pictogram, WEEE crossed-bin mark.
- p. 23: oven programs table, **11 rows × 6 columns**, icons in the last column.
- p. 30: door-removal procedure, drawings labeled A, B, C.

**Expected behavior.**
- `--lang` optional (single language). All 44 pages kept; output page *N* =
  source page *N*.
- `font_match`: Verdana and Calibri.
- p. 3 TOC → entries with `\dotfill` and `\pageref` to the output pages (same
  numbers here, since nothing is dropped).
- p. 9 pictograms → TikZ (vector, few paths). Book icon on p. 1 → fontawesome5
  `\faBook` if the model judges it equivalent, else TikZ.
- p. 23 → one `table`, 11 × 6; last-column icons → TikZ graphics in cells.
- p. 30 → drawings rebuilt (TikZ or vector-pdf by path count); "A", "B", "C"
  → `label`s anchored to their drawings.

**Pass criteria.** Compiles first time; text accuracy ≥ 0.99; SSIM ≥ 0.85 on
all pages; embedded images only where the source has photographs (at most the
7 source rasters). **First milestone page: p. 9** (§14).

---

## 2. `SL400EU_Przepisy.pdf` — Ninja Double Stack XL quick guide + recipes

**What it is.** 46 A5 pages, Polish only, Gotham fonts, brand green
`#47644b`, salmon `#f58262`. Many pages on a **photographic marble
background**; 209 raster images (food photos).

**Notable pages.**
- p. 1: cover — product logo, food photos around the edge.
- p. 3: "Spis treści" — white card on marble, dietary icons ("Oznaczenia").
- p. 10: product photo with "STREFA 1" / "STREFA 2" label boxes.
- p. 16: photo grid with captions, numbered circles 1–3, rotated side labels.
- p. 24: cooking tables; `find_tables()` returns five 1×3 fragments + one 6×3
  table — one logical table.
- p. 31: recipe — title card, 3 zones (STREFA 1 / Składniki / STREFA 2), steps
  1–7.
- p. 46: back cover, **QR code**, social icons.

**Expected behavior.**
- All 46 pages kept. `font_match`: Gotham (4 weights).
- Marble texture → one embedded photo, reused as background on every page that
  uses it (§7.4 step 4).
- p. 10 "STREFA" boxes are PDF text over a photo → `label`s anchored to the
  photo (translatable); the box shapes → TikZ.
- p. 16 circles → `step` badges (TikZ, colors from facts); rotated labels →
  rotated text.
- p. 24 → fragments merged by ingest into one `table`; section rows
  ("FRYTKI", "MROŻONKI") → spanning header rows.
- p. 46 QR → decoded and regenerated with `qrcode`; decoded text must equal
  the original. Social icons → fontawesome5 (`\faFacebook`, `\faInstagram`…).

**Pass criteria.** Steps continuous within each recipe; QR decodes identically;
no text inside any embedded photo.

---

## 3. `airblade-katalog-suszarek-2021-PL.pdf` — Dyson Airblade catalog

**What it is.** 32-page marketing brochure, Polish only, DysonFutura fonts.
Light grey text (`#868786`, `#b1b2b2`) on white, white on black. Accents red
`#e41e0a`, blue `#009ee3`. Designed as facing-page spreads (folios like
"01 02"), but each PDF page is a single page.

**Notable pages.**
- pp. 5, 21, 23: **full-page photos with < 20 chars**; the naive scan
  heuristic flags them.
- p. 11: dark page, cut-away product rendering with leader-line labels.
- p. 17: three products with prices.
- p. 22: black page, benefits list, row of 6 round blue icons.

**Expected behavior.**
- All 32 pages kept. `font_match`: DysonFutura (Book, Light, Medium, Heavy).
- pp. 5, 21, 23 → OCR probe returns < 20 chars → `kind = photo` → one embedded
  photograph each. **Not** sent to `ocr_transcribe`.
- p. 11 → rendering embedded as photo; labels are PDF text → anchored `label`s;
  leader lines → TikZ on top of the photo.
- p. 22 icons → TikZ (vector circles + glyphs) or fontawesome5 where
  equivalent (`\faStopwatch`, `\faTree`…); the model decides equivalence, code
  falls back to TikZ.
- Folio pairs "01 02" are running text → renumbered.

**Pass criteria.** Zero pages sent to `ocr_transcribe`; grey text colors exact
(from facts).

---

## 4. `airblade_v_installation_guide.pdf` — Dyson Airblade V installation guide

**What it is.** 83 landscape A4 pages, **40+ language sections**: Latin
scripts, Cyrillic, Greek, Thai, CJK, Arabic (RTL), Korean, Vietnamese. FuturaBT,
8 pt body, **5 narrow columns** per page. Warning red `#ef4235`, OK green
`#56af31`. **No raster images** — all illustrations are vector.

**Notable pages.**
- p. 1: cover, line-art product outline.
- p. 2: language index — language code → printed page number (e.g. PL → 48).
- pp. 3–4: near-wordless installation drawings (19 and 53 chars: step numbers
  "1", "2", "3.1", dimensions), 1,290 and 1,746 vector paths.
- p. 5 onward: language sections; **sections start mid-page** (p. 17: Russian
  ends, Slovak begins). First Arabic section p. 34.
- Polish text detected on pp. 15 and 52 (heuristic).
- pp. 32, 81: near-blank (2 chars, 0 paths).
- p. 83: black back cover, customer-care phone table, NSF mark.
- PDF outline: `"PDF 1"` → p. 1, `"PDf 2"` → p. 5 — junk.

**Expected behavior with `--lang pl`.**
- `language_map`: pp. 1, 3, 4, 83 `neutral` → kept; pages with Polish →
  `selected` or `mixed` → kept; everything else `other`; pp. 32, 81 `blank`.
  Output ≈ 7–8 pages (exact list from ground truth).
- On `mixed` pages: other-language columns removed; Polish content flows from
  the top of the 5-column grid.
- p. 2 language index → `neutral`-structured page: rebuilt as a table that lists
  **only** languages in the output (just PL), with `\pageref` to the output
  page. **[Decision]** If that leaves a single entry, the page is still kept
  (one per page) so the cover → index → drawings order is preserved.
- pp. 3–4: > 400 paths → vector-pdf crops with text removed; "1", "2", "3.1"
  → `step` elements; dimension numbers → `label`s.
- p. 83 phone table → keep all rows (contacts are per country, not per
  language); NSF mark → TikZ.
- Outline ignored (0 of 2 entries match headings).
- `font_match`: FuturaBT and HelveticaNeue only (CordiaNew/MadrasahArabic are
  not used in Polish text).

**Expected behavior with `--lang ar`** (to exercise RTL): `babel`
`bidi=basic`, mirrored column order, MadrasahArabic matched.

**Pass criteria.** 0 non-Polish text blocks in output; every Polish block from
the ground truth present; 0 raster images.

---

## 5. `LXUT33.pdf` — UNI-T UT33A+/B+/C+/D+ multimeter

**What it is.** 16 A4 pages: Polish (pp. 1–8), then English (pp. 9–16) with the
same layout. **0 extractable characters** — all lettering is outlined.

| Page | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 | 15 | 16 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| paths | 74 | 2401 | 3715 | 2252 | 3690 | 1647 | 6179 | 500 | 59 | 2053 | 3431 | 2214 | 3720 | 1555 | 6010 | 523 |
| images | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

**Notable pages.**
- pp. 1, 9: covers (PL / EN) — product photo, title bar, model list.
- p. 2: warnings, certifications, specifications, icon legend ("Ikony").
- pp. 3–4: device schematic with numbered parts; measurement wiring diagrams
  with "Czerwony"/"Czarny" (red/black) lead labels.
- p. 6: accuracy tables (Zakres / Model / Rozdzielczość / Precyzja).

**Expected behavior with `--lang pl`.**
- `ingest`: pp. 2–8, 10–16 → `outlined`; pp. 1, 9 → `graphics` (74/59 paths,
  no full-page image) → OCR probe finds text → OCR path.
- `language_map` runs on OCR text: pp. 1–8 `selected`, pp. 9–16 `other` →
  **8 output pages**. With `--lang en`: pp. 9–16 kept, output pages 1–8.
- `ocr_transcribe` on every kept page (confidence ≤ 0.8). Escalation if OCR
  boxes cover < 50% of glyph-path area.
- Glyph outlines covered by OCR boxes → removed, re-rendered as real text.
  "Czerwony"/"Czarny" → `label`s anchored to the diagrams, so they translate.
- Remaining schematic paths: TikZ if ≤ 400 items per drawing, else vector-pdf
  (text already removed).
- p. 6 tables: structure from the vision model + ruling lines in the drawings;
  `find_tables()` returns nothing here.
- Symbols (Ω, µA, ⏚, diode, continuity) → Unicode in the chosen font if it has
  the glyph (checked by `fontTools`), else TikZ.
- `font_match`: the model judges a geometric sans from the rendered glyphs
  (no font name available).

**Pass criteria.** OCR accuracy ≥ 0.97 on pp. 2 and 6; `main.pdf` text is fully
extractable (copy-paste works); `--lang pl` and `--lang en` runs produce
structurally identical IR.

---

## 6. `EOS_2000D_Instruction_Manual_PL.pdf` — Canon EOS 2000D

**What it is.** 326 small pages (298 × 420 pt), Polish only, Arial 7–8 pt, 2
columns, light-blue accents (`#80d9ff`, `#4dc9ff`). **129-entry valid PDF
outline**, **1,321 internal links**.

**Icon fonts:**

| Font | Glyph spans | Example |
|---|---|---|
| Webdings | 1,406 | `U+F03D` |
| Dmk4 (Canon) | ~900 | ASCII letters mapped to icons |
| Y007C (Canon) | ~280 | ASCII digits/letters mapped to icons |
| Wingdings3 | 130 | `U+F075` |
| Wingdings | 116 | `U+F0E8` |

**Notable pages.**
- p. 1: cover photo, model logo, red "Instrukcja obsługi" bar.
- p. 3: kit contents, product photos with captions.
- p. 109: tips with inline button icons and small exposure diagrams.
- p. 164: LCD screen diagram with ~30 leader-line labels.
- p. 326: back cover, addresses.

**Expected behavior.**
- All 326 pages kept. `font_match`: Arial (shared decision with RYOBI).
- Every icon-font span → icon graphic (fontawesome5 via `iconmap.json`, else
  glyph outline → TikZ). A Dmk4 "k" never appears as the letter "k". Inline
  icons appear in `strings.pl.json` as `{icon:ID}` placeholders.
- p. 164: screen diagram → vector-pdf or TikZ with text removed; all ~30 labels
  → anchored `label`s with tight `max_width_pt` in the strings file.
- Outline valid → 129 `hyperref` bookmarks at the same levels.
- 1,321 links → `\hyperlink` to output pages (same numbers, nothing dropped).
  "(str. N)" references → `\pageref`.

**Pass criteria.** 0 literal icon-font characters in output text; ≥ 99% of
links preserved with correct target; 129 bookmarks.

---

## 7. The four RYOBI manuals — one shared template

| File | Pages | Polish text (heuristic) | Low-text pages (cover, pictograms, back) |
|---|---|---|---|
| `instrukcja-obslugi-RYOBI-RY18LT23A-0.pdf` (grass trimmer) | 120 | 40–42, 109 | 1, 80–91, 120 |
| `instrukcja-obsluga-RYOBI-R18GN18-0.pdf` | 104 | 34–36, 81 | 1, 67–71, 104 |
| `Instrukcja-obslugi-RYOBI-RLM36X41H50PG.pdf` (lawn mower) | 192 | 76–81, 181 | 1, 55, 67, 152–165, 192 |
| `instrukcja-obslugi-RYOBI-RY36BI1800A-250.pdf` (pressure washer) | 220 | 88–94 | 1, 179–189, 215, 218, 220 |

**What they are.** Same template: 462 × 637 pt, ArialMT 5–9 pt, near-black
`#231f20`, section headers as white text on grey bars (`#808285`, `#636466`).
**~25 language versions in one PDF** (EN, FR, DE, ES, IT, NL, PT, DA, SV, FI,
NO, RU, PL, CS, HU, RO, LV, LT, ET, HR, SL, SK, BG, UK, TR), each 3–7 pages.
A vertical **language tab strip** along the page edge highlights the current
language.

**Notable pages (RY18LT23A).**
- p. 1: cover, product photo, book pictogram.
- p. 2: "Important!" notice: one row per language (signal word | sentence).
- pp. 40–42: Polish section, 2 columns, numbered safety rules.
- pp. 80–91: near-wordless pictogram pages: numbered frames, ✓/✗, icons.
- p. 109: Polish text in a later multilingual part (e.g. declarations).
- p. 120: back cover, addresses, document code.

**Expected behavior with `--lang pl` (RY18LT23A).**
- Kept: p. 1, p. 2 (`mixed` → only the PL row + header), pp. 40–42, pp. 80–91
  (`neutral`), p. 109, p. 120 → **≈ 18 output pages**; every other page
  `other` → dropped. Exact list confirmed by ground truth.
- Output numbering 1…18; any "see page N" in the Polish text → `\pageref`
  to the output page; references to dropped pages listed in review.
- Grey header bars → `heading` style (fill + white text).
- Language strip → TikZ `decoration`; **all 25 codes kept** as in the source,
  highlighted tab = render language (PL now, the translation language after
  `--render-lang`).
- Pictogram pages: each frame → `graphic` (TikZ ≤ 400 paths, else vector-pdf);
  frame numbers → `step`; ✓/✗ → fontawesome5 (`\faCheck`, `\faTimes`) or TikZ.
- Numbered safety lists continuing across columns/pages → counters carried
  (§8.5).
- `font_match`: Arial (shared decision), Arial Narrow.
- **Template reuse:** run RY18LT23A first, then the other three with
  `--style-from out/instrukcja-obslugi-RYOBI-RY18LT23A-0-pl/style.json` → no
  `style_pass` or `font_match` calls for them.

**Pass criteria.** 0 non-Polish text in output (except the language strip
codes and neutral codes); no list restarts in the Polish section; pictogram
pages contain no embedded images.

---

## 8. `XBOX SERIES X + S MANUAL EN - AU NZ.pdf` — Product & Regulatory Guide

**What it is.** 12 landscape pages (425 × 312 pt), English only, SegoePro, **6 pt**
body (39,697 of 39,827 chars), single color `#231f20`, 3 columns. No raster
images.

**Notable pages.**
- p. 1: cover — Xbox logo, title.
- pp. 2–6: safety text, many `⚠ WARNING:` / `CAUTION:` blocks with vector
  triangles.
- pp. 7–8: limited warranty, numbered legal sections, all-caps paragraphs.
- p. 9: "Microsoft Contract Information" table (Country | Entity | Address |
  Phone).
- p. 12: back cover: Microsoft logo + **vector barcode**; no text layer, 86
  paths → `graphics` kind.

**Expected behavior.**
- All 12 pages kept. `font_match`: SegoePro (Regular, Bold, SemiLight); the
  model is told text is set at 6 pt, so legibility and width matter.
- `WARNING:` blocks → `callout(variant=warning)`; triangle → `\faExclamationTriangle`.
- All-caps text kept as typed characters (no `\MakeUppercase`), so translators
  see the real text.
- p. 9 → 4-column `table`.
- p. 12: OCR probe finds barcode digits only. Logo → TikZ from paths; barcode →
  TikZ from bar paths (exact); human-readable digits → `label` (not
  translatable content, but kept as text).
- 3-column 6 pt layout leaves no slack: this file is the **fit-strategy test**
  for translations (§11.3).

**Pass criteria.** Barcode TikZ render matches the source at 300 dpi
(bar positions within 0.1 pt); every `WARNING:` is a callout; 12 output pages.

---

## Ground-truth set (for §13 metrics)

Hand-label these first. For each page: element bboxes, kinds, reading order,
language of each text block, and expected graphic method.

| File | Pages | Why |
|---|---|---|
| AMICA | 1, 3, 9, 23, 30 | baseline, TOC, marks, table, labeled drawings |
| Ninja SL400EU | 3, 10, 16, 24, 31, 46 | backgrounds, photo labels, steps, split table, recipe, QR |
| Dyson catalog | 5, 11, 22 | photo-not-scan, labels over photo, icon row |
| Dyson install guide | 2, 3, 15, 17, 52, 83 | index, vector steps, PL pages, mid-page language switch, back cover |
| LXUT33 | 1, 2, 3, 6, 9 | OCR cover, legend, schematic, table, EN cover (must be dropped for `pl`) |
| EOS 2000D | 1, 3, 109, 164 | cover, captions, inline icons, labeled screen diagram |
| RYOBI RY18LT23A | 2, 40, 41, 85, 109 | mixed table, PL section, pictograms, late PL page — **plus the complete kept/dropped page list for `--lang pl`** |
| Xbox | 2, 9, 12 | warnings, table, barcode-only page |
