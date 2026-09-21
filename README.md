# word2latex

Converts photos of handwritten notes into structured LaTeX. Runs entirely on your
machine — no API calls, no accounts, no per-page cost.

Built for theoretical CS and maths notes: equations, proofs, derivations mixed with
prose. It aims to preserve the *structure* of the page, not just the text — aligned
derivations become `align*`, boxed results become theorem environments.

See [`intentions.md`](intentions.md) for the design and, importantly, for what was
deliberately left out.

## Status

v1, early. The pipeline, diagram embedding, flagging and eval harness are implemented
and tested. **Transcription quality on real handwriting is unmeasured** — that is what
`w2l eval` exists to settle, and it is the first thing to do.

## Install

Requires [uv](https://docs.astral.sh/uv/) (already installed) and about 7 GB of disk,
almost all of it the model. Everything is removable — see [Uninstall](#uninstall).

```bash
# 1. The Python package (~50 MB; Pillow is the only dependency)
uv venv && uv pip install -e .

# 2. Ollama, to serve the model locally (~500 MB)
brew install --cask ollama
ollama serve &

# 3. A vision model (~6 GB). Check the Ollama library for current options —
#    do not trust a model name hardcoded in a README.
ollama pull qwen2.5vl:7b

# 4. LaTeX, to produce PDFs (~500 MB; skip if you only want .tex)
brew install --cask basictex
sudo tlmgr update --self
sudo tlmgr install latexmk enumitem ulem marginnote framed
```

Confirm everything is wired up:

```bash
./.venv/bin/w2l check
```

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

Nothing here installs into system Python or leaves background services beyond Ollama.
To reclaim everything:

```bash
# The model weights — the big one (~6 GB)
rm -rf ~/.ollama

# Ollama itself (~500 MB)
brew uninstall --cask ollama

# LaTeX (~500 MB)
sudo rm -rf /usr/local/texlive /Library/TeX
brew uninstall --cask basictex

# The project, venv and all outputs
rm -rf ~/Documents/Projects/word2latex

# uv's download cache, if you want it back
uv cache clean
```

To free space without uninstalling, `ollama rm <model>` drops one model's weights and
keeps everything else.

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
