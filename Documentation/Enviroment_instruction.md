Here is the setup in order, with a check after each step so you know it worked before moving on.

Step 1: Python 3.11 or newer

Check what you have:

bash
python --version

If it’s older than 3.11, install a current Python from python.org (on Windows, tick “Add to PATH” in the installer). On Linux/macOS, use your package manager or pyenv.

Step 2: Project folder and virtual environment

A virtual environment keeps this project’s packages separate from everything else on your machine.

bash
mkdir manual2latex && cd manual2latex
python -m venv .venv

Activate it. You do this every time you open a new terminal:

bash
# Linux / macOS
source .venv/bin/activate

# Windows PowerShell
.venv\Scripts\Activate.ps1

Your prompt should now start with (.venv).

Step 3: Install the Python packages
bash
pip install --upgrade pip
pip install langgraph langgraph-checkpoint-sqlite langchain-anthropic anthropic \
            pymupdf pydantic jinja2 pillow numpy scikit-image openai

What each one is for:

Package	Role
langgraph	the graph engine (nodes, edges, Send, interrupt)
langgraph-checkpoint-sqlite	saves state to a file so runs can resume
langchain-anthropic, anthropic	calling Claude (LangGraph wrapper and the raw SDK)
pymupdf	reading PDFs, rendering pages, cropping figures
pydantic	the validated IR schema
jinja2	the LaTeX templates
pillow, numpy, scikit-image	image handling and SSIM page comparison

Freeze the versions right away, because LangGraph’s API changes between releases:

bash
pip freeze > requirements.txt

Verify:

bash
python -c "import fitz, langgraph, anthropic, pydantic, jinja2, skimage; print('ok')"
Step 4: API key

The pipeline talks to models through OpenRouter. Put the key in
`manual2latex/.env` (gitignored) or export it, never in code or git.

bash
# preferred: the file the pipeline reads automatically
echo 'OPENROUTER_API_KEY="sk-or-..."' > manual2latex/.env

# or: Linux / macOS (add to ~/.bashrc or ~/.zshrc to make it permanent)
export OPENROUTER_API_KEY="sk-or-..."

Verify with a tiny call (uses the configured recreate model):

bash
cd manual2latex && python -c "
from models import ask; print(ask('repair_latex', 'reply ok', [{'type':'text','text':'say ok'}], max_tokens=20))"

Step 5: A LaTeX distribution

This is the biggest install, and the pipeline needs a real TeX engine to compile. Pick one:

Windows: MiKTeX (installs missing packages on demand) or TeX Live.
macOS: MacTeX (about 5 GB) or the smaller BasicTeX.
Linux: sudo apt install texlive-full (large but painless), or texlive-latex-extra texlive-fonts-extra texlive-science latexmk for a leaner set.

The pipeline compiles with **lualatex** and `fontspec` (model-chosen OpenType fonts),
so on top of a minimal install you also need:

bash
tlmgr install fontspec luatexbase tex-gyre dejavu carlito montserrat opensans \
              babel-polish babel-english babel-german hyphen-polish hyphen-german \
              cyrillic babel-russian hyphen-russian

Make sure latexmk is available too. MiKTeX and TeX Live include it, though latexmk needs Perl on Windows. Then verify:

bash
pdflatex --version
latexmk --version

The generated documents will use these packages: tcolorbox, tikz, fontawesome5, titlesec, tabularx, longtable, multicol, graphicx, xcolor. A full TeX Live has them all. With BasicTeX or a lean install, add them with tlmgr install tcolorbox pgf fontawesome5 titlesec multirow. MiKTeX fetches them automatically on first use.

Test that the important ones compile. Save as test.tex:

latex
\documentclass{article}
\usepackage{tcolorbox}
\usepackage{tikz}
\usepackage{fontawesome5}
\begin{document}
\begin{tcolorbox}[title=Warning]\faExclamationTriangle\ It works.\end{tcolorbox}
\end{document}
bash
latexmk -pdf -interaction=nonstopmode test.tex

A test.pdf with a titled box means LaTeX is ready. If you see “File not found” for a .sty, that package is the one to install.

Later, if you prefer a lighter option, tectonic is a single-binary engine that downloads packages on demand. It’s optional here.

Step 6: Folder layout
bash
mkdir cache out templates
touch ingest.py ir.py analyze.py style.py figures.py render.py verify.py graph.py

Put one test manual in the folder, ideally a short born-digital PDF of 3-5 pages, as manual.pdf.

Step 7: Smoke test the ingest layer

Before writing any graph code, confirm PyMuPDF reads your PDF:

bash
python -c "
import fitz
d = fitz.open('manual.pdf')
print(len(d), 'pages')
p = d[0]
print(len(p.get_text('dict')['blocks']), 'text blocks')
print(len(p.get_image_info()), 'images')
print(len(p.get_drawings()), 'vector shapes')
p.get_pixmap(dpi=150).save('cache/page_0.png')
"

Open cache/page_0.png. If the page looks right and the counts are non-zero, you’re set. Zero text blocks and one big image per page means it’s a scan, which needs the OCR path from earlier instead.

Step 8: Optional installs for later

Skip these until the basic pipeline works:

Docling (pip install docling) for a layout-detection first pass. It pulls in large ML dependencies.
Prefect if you outgrow plain Python orchestration.
LangGraph Studio / LangSmith for visual debugging of the graph. It needs a free LangSmith account, and you set LANGSMITH_API_KEY the same way as above.
Common setup problems
pip installs into the wrong Python: the venv isn’t active. Look for (.venv) in your prompt.
ModuleNotFoundError: fitz: the package is called pymupdf, but you import it as fitz. If you installed the wrong one (pip install fitz), run pip uninstall fitz and then pip install pymupdf.
LangGraph import errors: check the installed version with pip show langgraph against the current docs, since checkpointers and interrupt moved between releases.
LaTeX compiles by hand but fails from Python: the Python process doesn’t see the same PATH. Call latexmk by full path, or restart the terminal after installing TeX.

Once step 7 prints sensible numbers for your test PDF, tell me what it printed and we’ll write ingest.py and ir.py properly. I can also add these steps to the doc if you want them there.