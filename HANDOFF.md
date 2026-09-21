# Handoff

Read this before running anything. It says what works, what has never been run, and
what the first day of work should be.

## What this is

A command-line tool that converts photos of handwritten maths/CS notes into LaTeX,
running entirely on your machine. No API keys, no accounts, no per-page cost.

`README.md` is the usage guide. `intentions.md` is the design and — more useful —
the record of what was deliberately cut and why. Read `intentions.md` before
proposing a feature; several obvious ideas were considered and rejected for reasons
that still hold.

## Honest status

**The plumbing is built and tested. The actual transcription quality is completely
unknown.** No one has yet run a real photograph of real handwriting through this.

| Component | State |
|---|---|
| CLI, arg handling, error paths | Tested |
| Image preprocessing | Tested |
| Diagram cropping and embedding | Tested, including malformed model output |
| `%% UNSURE` flagging and review page | Tested |
| LaTeX document assembly | Tested |
| Ollama request/response handling | Tested against a mock |
| Eval scoring | Tested |
| **A real Ollama generation** | **Never run** |
| **A real `pdflatex` compile** | **Never run** |
| **Quality on real handwriting** | **Never measured** |

32 tests, no network or model needed:

```bash
./.venv/bin/python -m unittest discover -s tests
```

The two untested seams are untested because the machine this was built on had
neither Ollama nor a TeX engine installed. They are the first things you will
exercise, and the most likely place to hit a problem. Expect to debug there.

## Setup

Full per-platform instructions are in `README.md` — macOS, Windows and Linux are all
covered. Roughly 7 GB, all of it removable via the `## Uninstall` section there.

The short version:

```bash
git clone https://github.com/zprynne/word2latex.git && cd word2latex
uv venv && uv pip install -e .     # or python3 -m venv .venv && .venv/bin/pip install -e .
# install Ollama, then:
ollama pull qwen2.5vl:7b
# install a TeX distribution (BasicTeX / MiKTeX / TeX Live)
./.venv/bin/w2l check              # tells you what is missing, per platform
```

`w2l check` is the fastest way to find out what your machine is still missing; it
prints the right install command for whichever OS you are on.

**On the model name:** `qwen2.5vl:7b` is a placeholder default, not a researched
recommendation. Check the current Ollama library and pick candidates yourself.
`intentions.md` §6 explicitly leaves model selection open and explicitly removes the
8B size cap that was in the original plan. Bigger is fine if it runs.

**Platform note:** the code is pure Python and platform-agnostic — Ollama is reached
over HTTP, LaTeX through `subprocess`. It has only been exercised on macOS, so
Windows and Linux are untested in practice even though nothing in the code is
Mac-specific.

## Do this first

**Build the eval before touching the prompt.** This is the one instruction in this
document that matters. Without ground truth, every model and prompt comparison
degenerates into looking at two PDFs and preferring whichever you saw last.

1. Photograph 5–10 real pages. Include some math-heavy, some prose-heavy, and at
   least one with a hand-drawn diagram. Put them in `samples/pages/`.
2. Hand-transcribe each into `samples/truth/<same-stem>.tex` — body content only,
   no preamble. This is tedious and it is the single most valuable artifact you will
   produce. Do it once, carefully.
3. Run it:

```bash
./.venv/bin/w2l eval --pages samples/pages --truth samples/truth \
  --models qwen2.5vl:7b,llama3.2-vision:11b
```

You now have a number. Every subsequent decision — model choice, prompt change,
preprocessing tweak — is measured against it.

`samples/` is gitignored. Your notes stay local; only the code is shared.

## How to think about the output

Two things are flagged rather than silently guessed. Both are deliberate and both
should stay:

- `%% UNSURE:` comments mark passages the model could not read. They appear inline
  in the `.tex` at the point of the problem, and are collected onto a "Review these"
  page at the end of the PDF. `grep -n '%% UNSURE' out/*.tex`.
- Red-boxed figures are hand-drawn diagrams cropped from the photo and embedded as
  images. v1 does not convert diagrams to TikZ — see `intentions.md` §5 for why that
  was cut and what the right shape is if it is ever revisited.

If the model starts silently guessing instead of flagging, that is a prompt
regression, not an improvement. The flagging is the feature.

## Where to make changes

`src/word2latex/prompt.py` is where nearly all quality lives. It is the first place
to work and the easiest place to cause an unnoticed regression, which is exactly why
the eval comes first.

```
src/word2latex/
  cli.py          subcommands: convert, eval, check
  preprocess.py   EXIF orientation, grayscale, autocontrast, downscale to 1568px
  prompt.py       the conversion prompt  <- start here
  backend.py      Ollama HTTP client, stdlib only
  latex.py        document assembly, diagram cropping, flagging
  compile.py      pdflatex/latexmk runner
  evaluate.py     token edit-distance scoring
tests/            32 tests, no network needed
```

## Known limitations

These are known and accepted for v1, not oversights:

- No perspective or skew correction. Photograph pages flat and evenly lit; it
  materially affects results. Adding deskew means adding OpenCV (~90 MB), which was
  judged not worth it until the basics are measured.
- Diagram bounding boxes come from the model and are unreliable. The code pads them,
  sanity-checks them, and falls back to embedding the whole page when the estimate is
  bad — so a wrong box degrades to "too much image", never to a broken document.
- Page order on a merged run is filename order. Name files accordingly.
- Generated LaTeX is untrusted input to TeX, so compilation runs with shell-escape
  disabled and a 120-second timeout. Do not remove either.
- A model that returns prose instead of LaTeX will produce a `.tex` that fails to
  compile. The error surfaces; it is not silently swallowed.

## Things that were considered and cut

Listed so they are not re-proposed without new information. Full reasoning in
`intentions.md` §5, §7, §8.

- **Diagram vectorization to TikZ** — roughly 40% of the build, falls back to an
  embedded image whenever it fails, and depends on bounding-box localisation that
  does not currently hold up. v2 at the earliest, and only after OCR is proven.
- **Chat-based editing of the `.tex`** — duplicates any editor or coding assistant,
  and a local model rewriting a whole file to satisfy one instruction regresses lines
  it was not asked to touch.
- **Handwriting calibration from a reference page** — replaced by `--glossary`, a
  plain-text file of the writer's quirks injected into the prompt. Most of the
  benefit, almost none of the work.
- **A GUI** — justified by a PDF-preview-plus-chat loop that no longer exists once
  chat editing is cut.
