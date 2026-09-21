"""Eval harness.

intentions.md Section 9: model comparison without ground truth is people squinting
at PDFs. This scores candidates against hand-written reference LaTeX so a model
choice, or a prompt change, is a measurement rather than an impression.

Score is normalised edit distance on token sequences, reported as similarity in
[0, 1]. Tokens, not characters, so that whitespace and line-wrapping differences
between a human transcription and the model's do not dominate the number.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

TOKEN_RE = re.compile(r"\\[a-zA-Z]+\*?|\\.|[{}\[\]()&_^$]|[A-Za-z]+|\d+|\S")
# Comments are our own annotations, not content; they must not affect the score.
COMMENT_RE = re.compile(r"^[ \t]*%.*$", re.MULTILINE)


def tokenize(tex: str) -> list[str]:
    tex = COMMENT_RE.sub("", tex)
    tex = unicodedata.normalize("NFKC", tex)
    return TOKEN_RE.findall(tex)


def edit_distance(a: list[str], b: list[str]) -> int:
    """Levenshtein, two-row. Sequences here are short enough for O(n*m)."""
    if len(a) < len(b):
        a, b = b, a
    if not b:
        return len(a)

    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            current.append(min(
                previous[j] + 1,          # deletion
                current[j - 1] + 1,       # insertion
                previous[j - 1] + (ca != cb),  # substitution
            ))
        previous = current
    return previous[-1]


def similarity(reference: str, candidate: str) -> float:
    ref, cand = tokenize(reference), tokenize(candidate)
    if not ref and not cand:
        return 1.0
    if not ref or not cand:
        return 0.0
    return 1.0 - edit_distance(ref, cand) / max(len(ref), len(cand))


@dataclass
class PageScore:
    name: str
    similarity: float
    compiled: bool
    ref_tokens: int
    cand_tokens: int


@dataclass
class ModelScore:
    model: str
    pages: list[PageScore]

    @property
    def mean_similarity(self) -> float:
        return sum(p.similarity for p in self.pages) / len(self.pages) if self.pages else 0.0

    @property
    def compile_rate(self) -> float:
        return sum(p.compiled for p in self.pages) / len(self.pages) if self.pages else 0.0


def find_pairs(pages_dir: Path, truth_dir: Path) -> list[tuple[Path, Path]]:
    """Match each photo to its hand-transcribed .tex by stem."""
    from word2latex.preprocess import SUPPORTED_SUFFIXES

    pairs = []
    for img in sorted(pages_dir.iterdir()):
        if img.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue
        truth = truth_dir / f"{img.stem}.tex"
        if truth.exists():
            pairs.append((img, truth))
    return pairs


def format_report(scores: list[ModelScore]) -> str:
    lines = []
    width = max((len(s.model) for s in scores), default=5)
    lines.append(f"{'model'.ljust(width)}  similarity  compiles")
    lines.append(f"{'-' * width}  ----------  --------")
    for s in sorted(scores, key=lambda s: s.mean_similarity, reverse=True):
        lines.append(
            f"{s.model.ljust(width)}  {s.mean_similarity:>9.1%}  {s.compile_rate:>7.0%}"
        )

    lines.append("")
    lines.append("per page:")
    for s in scores:
        lines.append(f"  {s.model}")
        for p in sorted(s.pages, key=lambda p: p.similarity):
            flag = "" if p.compiled else "  [did not compile]"
            lines.append(f"    {p.similarity:>6.1%}  {p.name}{flag}")
    return "\n".join(lines)
