"""Document assembly: model output -> a complete, compilable .tex file."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

PREAMBLE = r"""\documentclass[11pt]{article}
\usepackage[utf8]{inputenc}
\usepackage[margin=1in]{geometry}
\usepackage{amsmath,amssymb,amsthm}
\usepackage{graphicx}
\usepackage{enumitem}
\usepackage[normalem]{ulem}
\usepackage{marginnote}
\usepackage{xcolor}
\usepackage{framed}

\newtheorem{theorem}{Theorem}
\newtheorem{lemma}[theorem]{Lemma}
\newtheorem{claim}[theorem]{Claim}
\newtheorem{corollary}[theorem]{Corollary}
\theoremstyle{definition}
\newtheorem{definition}[theorem]{Definition}
\newtheorem{example}[theorem]{Example}

% Diagrams that were not transcribed, embedded from the original photo.
% Deliberately loud: an unvectorised figure should be obvious at a glance.
\newcommand{\w2lfigure}[2]{%
  \begin{center}
  \fcolorbox{red!60!black}{red!3}{%
    \begin{minipage}{0.86\linewidth}
    \centering
    \includegraphics[width=\linewidth]{#1}\\[0.4em]
    {\small\color{red!60!black}\textbf{[embedded from photo — not transcribed]} #2}
    \end{minipage}}
  \end{center}}

\setlength{\parindent}{0pt}
\setlength{\parskip}{0.6em}

\begin{document}
"""

POSTAMBLE = "\n\\end{document}\n"

# %% DIAGRAM [0.1,0.2,0.8,0.5]: a DFA with three states
DIAGRAM_RE = re.compile(
    r"^[ \t]*%%[ \t]*DIAGRAM[ \t]*"
    r"\[[ \t]*([\d.]+)[ \t]*,[ \t]*([\d.]+)[ \t]*,[ \t]*([\d.]+)[ \t]*,[ \t]*([\d.]+)[ \t]*\]"
    r"[ \t]*:?[ \t]*(.*)$",
    re.MULTILINE,
)
# Tolerate the model omitting the bounding box.
DIAGRAM_NOBOX_RE = re.compile(r"^[ \t]*%%[ \t]*DIAGRAM[ \t]*:?[ \t]*(.*)$", re.MULTILINE)
UNSURE_RE = re.compile(r"^[ \t]*%%[ \t]*UNSURE[ \t]*:?[ \t]*(.*)$", re.MULTILINE)


@dataclass
class Page:
    """One converted photo."""

    source: Path
    body: str
    unsure: list[str] = field(default_factory=list)
    figures: int = 0


def _crop(img: Image.Image, box: tuple[float, float, float, float], pad: float = 0.02):
    """Crop a normalised box, padded, clamped to the image."""
    x0, y0, x1, y1 = box
    x0, x1 = sorted((x0, x1))
    y0, y1 = sorted((y0, y1))

    # Judge the estimate before padding, or padding turns a useless box into a
    # plausible-looking sliver. Below ~5% of a page dimension is not an estimate.
    if (x1 - x0) < 0.05 or (y1 - y0) < 0.05:
        return img

    x0 = max(0.0, x0 - pad)
    y0 = max(0.0, y0 - pad)
    x1 = min(1.0, x1 + pad)
    y1 = min(1.0, y1 + pad)
    px = (
        int(x0 * img.width),
        int(y0 * img.height),
        int(x1 * img.width),
        int(y1 * img.height),
    )
    # Guard against a box that is fractionally valid but tiny in pixel terms.
    if px[2] - px[0] < 16 or px[3] - px[1] < 16:
        return img
    return img.crop(px)


def process_page(
    source: Path,
    raw_body: str,
    image: Image.Image,
    assets_dir: Path,
    page_index: int,
) -> Page:
    """Replace diagram markers with cropped figures; collect uncertainty notes."""
    assets_dir.mkdir(parents=True, exist_ok=True)
    counter = [0]

    def emit_figure(box: tuple[float, float, float, float] | None, caption: str) -> str:
        counter[0] += 1
        name = f"p{page_index:03d}_fig{counter[0]}.png"
        crop = _crop(image, box) if box else image
        crop.save(assets_dir / name)
        caption = caption.strip().rstrip(".") or "hand-drawn figure"
        return f"\\w2lfigure{{{assets_dir.name}/{name}}}{{{_escape(caption)}}}"

    def sub_boxed(m: re.Match) -> str:
        try:
            box = tuple(float(m.group(i)) for i in range(1, 5))
        except ValueError:
            return emit_figure(None, m.group(5))
        if not all(0.0 <= v <= 1.0 for v in box):
            box = None  # type: ignore[assignment]
        return emit_figure(box, m.group(5))  # type: ignore[arg-type]

    body = DIAGRAM_RE.sub(sub_boxed, raw_body)
    body = DIAGRAM_NOBOX_RE.sub(lambda m: emit_figure(None, m.group(1)), body)

    unsure = [m.strip() for m in UNSURE_RE.findall(raw_body) if m.strip()]
    return Page(source=source, body=body, unsure=unsure, figures=counter[0])


def _escape(text: str) -> str:
    for char, repl in (
        ("\\", r"\textbackslash{}"),
        ("&", r"\&"), ("%", r"\%"), ("$", r"\$"), ("#", r"\#"),
        ("_", r"\_"), ("{", r"\{"), ("}", r"\}"), ("~", r"\textasciitilde{}"),
        ("^", r"\textasciicircum{}"),
    ):
        text = text.replace(char, repl)
    return text


def build_document(pages: list[Page], title: str | None = None) -> str:
    """Wrap one or more page bodies into a standalone document."""
    parts = [PREAMBLE]
    if title:
        parts.append(f"\\begin{{center}}\\Large\\textbf{{{_escape(title)}}}\\end{{center}}\n\n")

    for i, page in enumerate(pages):
        if i:
            parts.append("\n\\clearpage\n")
        parts.append(f"% ---- source: {page.source.name} ----\n")
        parts.append(page.body.strip())
        parts.append("\n")

    total_unsure = sum(len(p.unsure) for p in pages)
    if total_unsure:
        parts.append("\n\\clearpage\n")
        parts.append("\\section*{Review these}\n")
        parts.append(
            f"{total_unsure} passage(s) the model was unsure of. "
            "Each is also marked with a \\texttt{\\%\\% UNSURE} comment in the source "
            "at the point it occurs.\n\n"
        )
        parts.append("\\begin{itemize}[leftmargin=*]\n")
        for page in pages:
            for note in page.unsure:
                parts.append(
                    f"  \\item \\textbf{{{_escape(page.source.name)}}}: {_escape(note)}\n"
                )
        parts.append("\\end{itemize}\n")

    parts.append(POSTAMBLE)
    return "".join(parts)
