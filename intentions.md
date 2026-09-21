# Intentions: Handwritten Notes → LaTeX Converter

## Purpose of This Document

Captures the intent behind this project before the code grew around it. It is meant to be
read in full by anyone — human or model — picking the project up. Scope decisions are
deliberate: Section 8 lists what was cut from v1 and why, and cutting something is a
decision, not an oversight. Reopen those only with a reason.

## 1. Project Overview

A local, offline tool that converts photos of handwritten notes into structured LaTeX.
The content is theoretical CS / mathematics — equations, proofs, derivations — mixed with
explanatory prose.

The point is not transcription. It is **structure preservation**: if the page uses aligned
`=` signs down a derivation, the output uses an `align` environment, not eight loose lines.
Follow the conventions the page already establishes rather than imposing a generic default.

## 2. Why Offline

**Stated explicitly because it is the constraint that drives every other decision.**

Two reasons, in order:

1. **No recurring cost.** An API-backed pipeline bills per page, separately from any Claude
   subscription, and the spend concentrates during development when you re-run the same
   pages dozens of times tuning prompts. A local model costs disk and nothing else.
2. **Personal notes stay on the machine.** Secondary, but real.

**The cost of this constraint, stated honestly:** a local ~8B vision model will transcribe
handwritten math noticeably worse than a frontier model would. Accepted knowingly. The
mitigation is not a better local model — it is Section 7's division of labour.

If the per-page cost ever stops mattering, revisit this first. It is the single highest-
leverage assumption in the document.

## 3. Core Input/Output Behavior

- **Input:** one or more photos, one page of notes per photo.
- **Output per run:** a `.tex` source file and a compiled `.pdf`. The PDF exists so the
  conversion can be eyeballed at a glance instead of read as source.
- **Batching:** per run, either one merged `.tex`/`.pdf` for all photos, or a separate pair
  per photo.
- **Compilability:** generated `.tex` files are complete standalone documents with a correct
  preamble — not fragments needing manual assembly. A file that does not compile is a bug.

## 4. Uncertainty Must Be Visible

The system must never silently guess. Where the model is unsure of a transcription, it
emits an inline `%% UNSURE: <note>` LaTeX comment at that point in the source.

**Why a comment and not a confidence score:** locally served models do not expose usable
per-token confidence, and a model's *self-reported* confidence is poorly calibrated. An
inline marker the model is instructed to emit is the honest mechanism that actually works.
Do not replace this with a confidence-score API that does not exist.

Diagrams follow the same rule — see Section 5.

## 5. Diagrams (v1: embed, do not vectorize)

Notes contain hand-drawn automata, graphs, and trees. **v1 does not attempt to convert these
to TikZ.** It crops the region and embeds it as an image with a visible flag.

**Why this was cut:** a classify → describe → generate-TikZ → compile-verify → retry pipeline
is roughly 40% of the build, and by its own design falls back to an embedded image whenever
it fails. It also silently assumes reliable diagram *localization* — bounding boxes from an
8B VLM on a photographed page — which is a separate capability that does not currently hold
up. Building the fallback first is the correct order: it is the path most diagrams take.

Vectorization is a v2 feature, worth attempting only after the core OCR is known to work.
When it is revisited, the two-step approach (structured description first, TikZ second,
never image → code directly) is the right shape and reportedly outperforms direct generation.

## 6. Model & Runtime

- **Task:** whole-page mixed handwritten math and prose, at the structural level.
- **Size:** the largest model that runs comfortably. **Not capped at 8B.** Disk and hardware
  are not constrained, so there is no reason to choose a smaller model than will run; an 8B
  cap would sacrifice the one thing this project is judged on.
- **Source:** open weights, run locally. No API calls anywhere in the pipeline.
- **Serving:** Ollama, so one model artifact runs on Metal (Mac) and CUDA (Windows) behind
  one interface, with no platform-specific inference code.
- **Selection is deliberately open.** Candidates are research-stage and their names, sizes,
  and licenses change — verify against the current Ollama library rather than trusting any
  list written here. Decide it with the eval in Section 9, not from benchmarks.

## 7. Division of Labour

The pipeline does the bulk conversion. Interactive fixing of a converted `.tex` is done in
whatever editor or assistant the user already has.

**Why there is no chat-editing feature:** it would be a second implementation of something
already available, and a local model rewriting a whole `.tex` file to satisfy "make line 3 a
partial derivative" reliably regresses lines it was not asked to touch. Batch conversion is
where a local pipeline adds value; conversational repair is not.

## 8. Explicit Non-Goals (v1)

- No API calls, anywhere.
- No diagram vectorization — embed and flag (Section 5).
- No chat-editing loop (Section 7).
- No handwriting calibration phase. A plain-text notation glossary in the prompt ("my z has
  a bar", "∂ looks like a 6") captures most of the benefit of few-shot handwriting samples
  for a fraction of the work and context.
- No networked accounts or cross-machine sync. Local, per-machine only.
- No perspective/skew correction in v1 — orientation, contrast, and downscaling only.

## 9. The Eval Comes First

**Before tuning anything, build the eval.** Without it, model comparison is three people
squinting at PDFs and agreeing with whoever spoke last.

1. Pick 5–10 real pages: some math-heavy, some prose-heavy, at least one with a diagram.
2. Hand-transcribe each to correct LaTeX **once**. This is the ground truth and the most
   valuable artifact in the repo.
3. Score candidates by normalized edit distance against it, plus a compile-success rate.

This is also how the Section 6 model question gets settled, and how you find out early
whether the offline constraint in Section 2 is survivable at all. If every local candidate
scores badly on real pages, that is a finding, and it should change the plan rather than be
worked around.

## 10. Build Order

1. Eval harness + hand-transcribed ground truth (Section 9).
2. Preprocess → single photo → `.tex` → compiled `.pdf`, with `%% UNSURE` markers.
3. Batch handling, merge-vs-separate.
4. Diagram crop-and-embed with visible flagging.
5. Model bake-off using step 1. Settle Section 6.
6. Notation glossary in the prompt.
7. *Only then* consider anything from Section 8.

## 11. Interface

Command-line, writing into an output folder.

A GUI was considered and is not being built. It was justified by the PDF-preview-plus-chat
loop, and Section 7 removed the chat half; a file manager and a PDF viewer cover the rest.
