"""LaTeX compilation.

Model-generated LaTeX is untrusted input to TeX. Two consequences, both handled here:
shell-escape stays off, and every run is bounded by a timeout — runaway macro expansion
in generated source is common enough to matter.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

TIMEOUT = 120

# TeX packages this project's preamble needs beyond a minimal install.
TEX_PACKAGES = "latexmk enumitem ulem marginnote framed"


def install_hint() -> str:
    """Platform-appropriate instructions for getting a TeX engine."""
    if sys.platform == "darwin":
        return (
            "  brew install --cask basictex\n"
            f"  sudo tlmgr update --self && sudo tlmgr install {TEX_PACKAGES}"
        )
    if sys.platform == "win32":
        return (
            "  winget install MiKTeX.MiKTeX\n"
            "  (MiKTeX installs missing packages on demand; accept the prompts)"
        )
    return (
        "  sudo apt install texlive-latex-recommended texlive-latex-extra latexmk\n"
        "  (or your distribution's equivalent)"
    )


@dataclass
class CompileResult:
    ok: bool
    pdf: Path | None
    log: str
    engine: str | None


def find_engine() -> str | None:
    for name in ("latexmk", "pdflatex"):
        if shutil.which(name):
            return name
    return None


def compile_tex(tex_path: Path, assets_dir: Path | None = None) -> CompileResult:
    """Compile in place. Assets are referenced relative to the .tex file."""
    engine = find_engine()
    if engine is None:
        return CompileResult(
            ok=False,
            pdf=None,
            engine=None,
            log=(
                "No LaTeX engine found. The .tex file was still written.\n"
                "Install one with:\n" + install_hint()
            ),
        )

    workdir = tex_path.parent
    if engine == "latexmk":
        cmd = [
            "latexmk", "-pdf", "-interaction=nonstopmode",
            "-no-shell-escape", "-halt-on-error", tex_path.name,
        ]
    else:
        cmd = [
            "pdflatex", "-interaction=nonstopmode",
            "-no-shell-escape", "-halt-on-error", tex_path.name,
        ]

    try:
        proc = subprocess.run(
            cmd,
            cwd=workdir,
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
            # An unattended run must never sit waiting on TeX's error prompt.
            stdin=subprocess.DEVNULL,
        )
        output = proc.stdout + proc.stderr
        ok = proc.returncode == 0
    except subprocess.TimeoutExpired:
        return CompileResult(
            ok=False, pdf=None, engine=engine,
            log=f"{engine} exceeded {TIMEOUT}s and was killed.",
        )

    pdf = tex_path.with_suffix(".pdf")
    if ok and pdf.exists():
        _clean_aux(tex_path)
        return CompileResult(ok=True, pdf=pdf, engine=engine, log=_tail(output))
    return CompileResult(ok=False, pdf=None, engine=engine, log=_errors_from(output))


def _clean_aux(tex_path: Path) -> None:
    for suffix in (".aux", ".log", ".out", ".fls", ".fdb_latexmk", ".toc"):
        tex_path.with_suffix(suffix).unlink(missing_ok=True)


def _errors_from(output: str) -> str:
    """TeX logs are long and mostly noise; keep the lines that explain the failure."""
    lines = output.splitlines()
    picked = [
        line for line in lines
        if line.startswith("!") or line.startswith("l.") or "Error" in line
    ]
    return "\n".join(picked[:40]) if picked else _tail(output)


def _tail(output: str, n: int = 25) -> str:
    return "\n".join(output.splitlines()[-n:])
