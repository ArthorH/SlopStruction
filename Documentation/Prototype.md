# manual2latex — Working Prototype

12 Oct 2026 · status: **implemented and run** · supersedes nothing in
[`Specification.md`](Specification.md) — that document describes the target
system; this one describes what exists now and how to run it.

## What it does today

Recreates and translates a PDF manual **page by page** with a LangGraph
pipeline: every page is rendered, extracted, sent to a vision model that
rewrites it as a LaTeX page body in the target language, compiled with
`lualatex`, and finally **stitched** into one PDF with bookmarks and metadata.

Verified end to end on `Examples/LXUT33.pdf` (UNI-T multimeter, no text layer)
and `instrukcja-obslugi-AMICA-ED975396BA.pdf` p. 9:

| Run | Pages | Result | Cost (OpenRouter) |
|---|---|---|---|
| LXUT33 pp. 1–8 → English | 8 | 7 recreated, 1 fallback (p. 2) | $0.145 |
| LXUT33 pp. 1–8 → Russian | 8 | 8/8 recreated | $0.1334 |
| AMICA p. 9 → English | 1 | recreated, no repairs | $0.0095 |

~$0.01–0.02 per page with the default model mix → the 326-page Canon manual
would cost roughly $3–7.

## Architecture

```
prepare ─► [Send × N pages] page ─► assemble
(font pick,      (facts → assets → recreate →     (stitch all page PDFs
 cached)          compile → repair ≤2 → fallback)  → final PDF + report.json)
```

| File | Role |
|---|---|
| `graph.py` | LangGraph wiring, CLI, per-page resume (page records on disk) |
| `ingest.py` | page render (110 dpi) + facts JSON: text lines (bbox, font, size, color), filled-rect/line shapes |
| `figures.py` | assets the model places as-is: raster images (photos, logos — original) and complex vector drawings, all taken from a text-stripped page copy so translated text can be re-typeset on top |
| `analyze.py` | model jobs: `recreate_page` (vision → translated LaTeX), `repair_latex`, `choose_font` |
| `render.py` | fixed lualatex preamble, `\placeat`/`\placeimg` pt-placement macros, 2-pass compile, skeleton/fallback bodies, **stitch** |
| `models.py` + `models.toml` | OpenRouter client, per-task model routing, cost capture |
| `verify.py`, `style.py`, `ir.py` | not implemented yet (see roadmap below) |

Key behaviors:

- **One output page per source page**, original page size, single
  `tikzpicture[page]` overlay with coordinates in pt from the top-left.
- **Extraction guard:** only a complete `\begin{tikzpicture}...\end{tikzpicture}`
  block is compiled. Notes/truncated replies go to repair (haiku, then sonnet);
  after 2 failed repairs the page falls back to the original page image so the
  stitch never breaks.
- **Fonts:** a model picks one of 10 curated free families (TeX Gyre Heros,
  Adventor, Termes, DejaVu (Sans/Condensed), Carlito, Montserrat, Open Sans,
  Latin Modern Sans, TeX Gyre Cursor); the choice is cached per output folder.
- **Stitch:** `assemble` merges per-page PDFs in page order, adds a bookmark per
  source page ("page 3") and metadata (`title` = PDF stem, `subject` = language).
  Pages that failed hard (no PDF) are skipped and listed as `missing_pages`.
- **Resume:** every finished page writes `pages/pNNNN.json`; rerunning skips
  those pages, so re-runs only pay for new/removed pages.

## Models (models.toml)

| Task | Default model | Escalation | $/Mtok in/out |
|---|---|---|---|
| `recreate_page` (bulk, vision + translation + LaTeX) | `google/gemini-3.8-flash` | `anthropic/claude-sonnet-5.5` | 0.75 / 3.75 |
| `repair_latex` | `anthropic/claude-haiku-5.5` | `anthropic/claude-sonnet-5.5` | 0.10 / 0.50 |
| `choose_font` (once per doc) | `google/gemini-3.5-flash-lite` | — | 0.30 / 2.50 |

`recreate_page` runs with `reasoning: "low"` and `max_tokens: 45000` — the
default Gemini reasoning budget was truncating bodies and leaking chain-of-thought
into pages; capping it cut cost ~7× and fixed both. Every call records tokens and
OpenRouter-reported cost into `report.json`.

No OpenAI models are used anywhere.

## Running it

```bash
cd manual2latex && source .venv/bin/activate

python graph.py ../Examples/LXUT33.pdf --to ru --pages 1-8 --workers 4
python graph.py ../Examples/LXUT33.pdf --to en --pages 2-3     # subset
python graph.py ../Examples/LXUT33.pdf --to en --pages 2 --dry-run  # no model calls
```

- Output: `out/<stem>.<lang>/<stem>.<lang>.pdf` (stitched), `pages/` per-page
  `.tex/.pdf/.reply.md/.json`, `assets/`, `report.json`.
- API key: `OPENROUTER_API_KEY` env var or `manual2latex/.env` (gitignored).
- Environment: TeX Live 2026 user install at `~/texlive/2026` with the font and
  babel packages listed in `Enviroment_instruction.md` step 5.

## Known limitations (honest list)

- **No text-layer pages** (UNI-T) work, but positions/sizes are eyeballed by the
  model from the page image — no OCR bbox stage yet.
- **No language filtering**: multilingual files would recreate every language;
  for LXUT33 we pass `--pages 1-8` (Polish half) manually.
- Small pictograms under the asset threshold get redrawn approximately.
- Model nondeterminism: the same page can succeed or need repairs run-to-run
  (UNI-T p. 2 succeeded alone, fell back in the 8-page batch).
- No visual-diff (SSIM) check, no IR schema/validation, no strings export for
  re-translation — those remain per `Specification.md`.

## Roadmap (in spec order, against what exists)

1. ~~recreate + compile one page~~ ✅ · ~~multi-page fan-out~~ ✅ · ~~stitch~~ ✅
2. Language map (drop other-language pages/blocks) — §6.2
3. IR + validation before render; per-page retry on validation failure — §8.3
4. Strings export / re-render path for translation iteration — §11
5. Visual check loop (SSIM + vision diffs) — §8.8
6. Escalation on low-confidence heuristics, human review gate — §8.4, §8.9
