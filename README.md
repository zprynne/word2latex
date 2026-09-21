# word2latex

Converts photos of handwritten notes into structured LaTeX. Runs entirely on your
machine — no API calls, no accounts, no per-page cost.

Built for theoretical CS and maths notes: equations, proofs, derivations mixed with
prose. It aims to preserve the *structure* of the page, not just the text — aligned
derivations become `align*`, boxed results become theorem environments.

New here? Start with [`HANDOFF.md`](HANDOFF.md).

See [`intentions.md`](intentions.md) for the design and, importantly, for what was
deliberately left out.

## Status

v1, early. The pipeline, diagram embedding, flagging and eval harness are implemented
and tested. **Transcription quality on real handwriting is unmeasured** — that is what
`w2l eval` exists to settle, and it is the first thing to do.

## Install

Roughly 7 GB, nearly all of it the model. Everything is removable — see
[Uninstall](#uninstall).

### 1. Get the code

```bash
git clone https://github.com/zprynne/word2latex.git
cd word2latex
```

### 2. Python environment

Needs Python 3.10+. Using [uv](https://docs.astral.sh/uv/) (recommended):

```bash
uv venv && uv pip install -e .          # ~50 MB; Pillow is the only dependency
```

Or with stock Python:

```bash
python3 -m venv .venv
.venv/bin/pip install -e .              # Windows: .venv\Scripts\pip install -e .
```

### 3. Ollama, to serve the model locally

| Platform | Command |
|---|---|
| macOS | `brew install --cask ollama` |
| Windows | `winget install Ollama.Ollama` |
| Linux | `curl -fsSL https://ollama.com/install.sh \| sh` |

Then start it (`ollama serve`, or launch the app on macOS/Windows).

### 4. A vision model (~6 GB)

```bash
ollama pull qwen2.5vl:7b
```

**Check the current Ollama library before settling on this one.** The default in
`backend.py` is a placeholder, not a researched recommendation — `intentions.md` §6
leaves model choice deliberately open and removes the 8B size cap from the original
plan. Any model Ollama serves with vision support will work; pass `--model`.

### 5. LaTeX, for PDF output (~500 MB)

Skip this if you only want `.tex` files; the tool degrades gracefully.

| Platform | Command |
|---|---|
| macOS | `brew install --cask basictex` then `sudo tlmgr update --self && sudo tlmgr install latexmk enumitem ulem marginnote framed` |
| Windows | `winget install MiKTeX.MiKTeX` (installs missing packages on demand) |
| Linux | `sudo apt install texlive-latex-recommended texlive-latex-extra latexmk` |

### 6. Confirm

```bash
./.venv/bin/w2l check          # Windows: .venv\Scripts\w2l check
```

Should report `ok` on all four lines. It tells you exactly what is missing and how to
install it for your platform.

## Use

```bash
# One photo
./.venv/bin/w2l convert page01.jpg

# A whole folder, merged into one document
./.venv/bin/w2l convert ./photos --merge --name lecture07 --title "Lecture 7"

# A folder, one .tex + .pdf per photo
./.venv/bin/w2l convert ./photos

# Skip the PDF
./.venv/bin/w2l convert page01.jpg --no-compile
```

Output lands in `out/`. Pages are ordered by filename when merging.

### Reading the output

Two things are flagged rather than silently guessed:

- **`%% UNSURE:`** comments mark passages the model could not read confidently. They
  appear inline in the `.tex` at the point of the problem, and are collected into a
  "Review these" page at the end of the PDF.
- **Red-boxed figures** are hand-drawn diagrams, cropped from your photo and embedded
  as images. v1 does not convert diagrams to TikZ; see `intentions.md` §5.

```bash
grep -n '%% UNSURE' out/*.tex   # everything worth checking
```

### Handwriting glossary

A plain text file describing your own quirks, injected into the prompt:

```
my lowercase z always has a bar through it
partial derivative symbols look like a 6
I write set union wider than intersection
```

```bash
./.venv/bin/w2l convert ./photos --glossary my-handwriting.txt
```

## Measuring quality

**Do this before tuning anything.** Without ground truth, comparing models is guesswork.

1. Put 5–10 real photos in `samples/pages/` — some math-heavy, some prose-heavy, at
   least one with a diagram.
2. Hand-transcribe each into `samples/truth/<same-stem>.tex`. Body content only, no
   preamble. Tedious once, valuable forever.
3. Score candidates:

```bash
./.venv/bin/w2l eval \
  --pages samples/pages --truth samples/truth \
  --models qwen2.5vl:7b,llama3.2-vision:11b
```

Reports mean similarity (normalised token edit distance, comments excluded) and
compile rate per model, and writes `out/eval/report.txt`.

If every candidate scores badly, that is a real finding about the offline constraint,
not a prompt-tuning problem. See `intentions.md` §2.

## Uninstall

Nothing installs into system Python or leaves background services beyond Ollama.

```bash
rm -rf ~/.ollama                              # model weights — the big one (~6 GB)
rm -rf ~/Documents/Projects/word2latex        # project, venv, outputs
```

Then remove Ollama and LaTeX through however you installed them — `brew uninstall
--cask ollama basictex` on macOS, Add/Remove Programs on Windows, your package
manager on Linux. On macOS, BasicTeX also leaves `/usr/local/texlive` and
`/Library/TeX`, which need `sudo rm -rf`.

To free space without uninstalling, `ollama rm <model>` drops one model's weights.

## Licensing

This repository has no LICENSE file, which under default copyright means all rights
reserved — the code is readable but not formally licensed for reuse, including by
people it is shared with directly. That is deliberate for now, not an oversight. If
you want to use or build on it, ask.

## Layout

```
src/word2latex/
  cli.py          subcommands: convert, eval, check
  preprocess.py   EXIF orientation, grayscale, autocontrast, downscale
  prompt.py       the conversion prompt — highest-leverage file here
  backend.py      Ollama HTTP client (stdlib only)
  latex.py        document assembly, diagram cropping, flagging
  compile.py      pdflatex/latexmk runner, shell-escape off, timeout bounded
  evaluate.py     edit-distance scoring against hand-transcribed truth
```
