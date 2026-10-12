Building a Manual-to-LaTeX Pipeline with LangGraph
12 Oct 2026 · @Artem
Why a graph at all
The task isn't a straight line, so a plain script handles it badly. Three things get in the way:
1. Parallelism: a 100-page manual means 100 independent analysis jobs.
2. Loops: compile the LaTeX, and if it fails, fix it and compile again. After it compiles, compare it visually to the original, fix differences, and recompile. You can't know in advance how many rounds that takes.
3. Pauses: sometimes the system should stop and ask "is this a diagram or a decoration?" and continue after you answer.
You could write all of this with for loops, thread pools, and manual saving to disk. LangGraph handles those three things for you, so you describe the shape of the workflow and it runs it.
The four core concepts
State is a single shared dictionary holding everything the pipeline knows at any moment: the PDF path, the extracted page data, the structured result for each page, the current LaTeX, whether the last compile succeeded, and how many repair attempts are used. Every step reads from it and writes to it. Think of a whiteboard that every worker can see.
Nodes are plain Python functions. Each takes the state, does one job, and returns only the parts of the state it wants to change. A node might call a model ("analyze this page") or run ordinary code ("compile this LaTeX"). Nodes don't know about each other, so each is easy to test alone.
Edges define what runs after what. Some are fixed ("after ingest, always do the style pass"). Others are conditional: a small function reads the state and picks the next node ("if the compile succeeded, go to visual check, otherwise go to repair"). Conditional edges are what create your loops.
Checkpointer saves the state after every node. If the program crashes on page 140, you resume from the last save instead of paying for 139 pages of model calls again. It also makes the human pause possible, because the graph can stop completely and continue hours later.
Two more features matter here:
• Reducers solve a specific problem. When 100 page-analysis nodes run in parallel and all write to page_irs, LangGraph needs a rule for combining them. A reducer says "append each result to the list" rather than "last writer wins".
• Send is how you fan out. Instead of an edge to one next node, you return a list of "run this node with this input" instructions, one per page, and LangGraph runs them in parallel.
Walking through the pipeline
1. Ingest. Ordinary code, no model. It opens the PDF, renders each page to an image, and pulls out the exact text, fonts, colors, and positions of everything embedded in the file. This is the factual layer: the model later interprets these facts instead of re-reading pixels.
2. Style pass. Runs once for the whole document, before the per-page work. It looks at a handful of representative pages and answers "what colors does this manual use?" and "what kinds of callout boxes exist: warning, note, tip?" The output becomes a LaTeX preamble with named styles. It runs first and once so every page maps to the same set of styles; if each page invented its own, the output would be inconsistent.
3. Fan-out analysis. Send creates one task per page. Each task gives a model the page image plus the extracted facts and asks for structured output: an ordered list of elements labeled heading, paragraph, figure, callout, step, icon, and so on. Structured output forces the model into a fixed schema, so downstream code can rely on it. Each element also carries a confidence score, which matters later. This is where the graphical vs. non-graphical decision happens, per region:
    ◦ Text-like: rebuild as real LaTeX text.
    ◦ Graphic content (photo, exploded diagram, schematic): crop out as an image.
    ◦ Graphic style (warning box, step badge, colored bar): rebuild as a LaTeX component such as tcolorbox, referencing a style from step 2.
4. Collect. Parallel tasks finish in any order, so this node sorts pages back into reading order and gathers every low-confidence element into a list.
5. Extract figures. Deterministic code. For each element marked as graphic content, crop its bounding box out of the PDF, preferably as vector so it stays sharp.
6. Render. Deterministic templates turn the structured data plus the style guide into a .tex file. The model does not write the LaTeX in the normal case. Templates are faster, cheaper, and always give the same output for the same input.
7. Compile loop. Run LaTeX. If it fails, a conditional edge sends the error log and the offending lines to a repair node, where a model proposes a fix, then back to compile. The loop is capped (say four attempts) by a counter in state, because without a cap an unfixable document would loop forever and keep spending money.
8. Visual check loop. Once it compiles, rasterize the output pages and have a vision model compare them to the originals and list concrete differences ("the warning box is missing its icon", "step 3's image is cropped too tightly"). Apply those fixes to the structured data, not the raw LaTeX, then re-render. A patch to the .tex would be erased by the next re-render; fixing upstream makes it permanent. This loop is capped too.
9. Human review. If anything remains low-confidence, the graph calls interrupt, which freezes it and saves everything. You inspect the flagged elements, give corrections, and resume exactly where it stopped.
Two kinds of work, deliberately separated
Models do judgment; code does mechanics. Deciding "is this region a decorative icon or a content diagram?" is judgment, so it goes to a model. Cropping, templating, and compiling are mechanics, so they go to code. When something goes wrong you can tell which kind of problem it is, and the mechanical parts are free and repeatable.
What usually goes wrong
• Cross-page continuity. With pure parallel fan-out, each page is analyzed in isolation, so a numbered list that continues onto the next page restarts. Fix it by passing the end of the previous page as context, or by adding a stitching step after collection.
• Huge state. Don't put image bytes in state, because every checkpoint saves a copy. Keep files on disk and store only their paths.
• Silent misclassification. A model may confidently label a text-heavy diagram as a paragraph. Build a small test set of manuals and measure figure recall and text accuracy before tuning anything.
• Cost. Per page you pay for at least one analysis call, plus any repair and visual-check calls. Caching results per page lets you iterate on later stages without redoing earlier ones.
How to build it
Start with three nodes: ingest, analyze one page, render. Get a single page from one manual to come out looking right. Then add fan-out, then the compile loop, then the visual loop, then the human pause. Each addition is a small change to the graph's shape, which is the main benefit of using LangGraph here.