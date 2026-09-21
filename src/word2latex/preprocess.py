"""Image preparation.

Deliberately minimal, per intentions.md Section 8: orientation, contrast and
downscaling only. No perspective or skew correction in v1.
"""

from __future__ import annotations

import base64
import io
from pathlib import Path

from PIL import Image, ImageOps

# Long-edge cap. Large enough to keep small handwriting legible, small enough to
# keep the model's image tokenisation from ballooning.
MAX_EDGE = 1568

SUPPORTED_SUFFIXES = {".jpg", ".jpeg", ".png", ".heic", ".webp", ".tif", ".tiff"}


def load(path: Path, max_edge: int = MAX_EDGE, grayscale: bool = True) -> Image.Image:
    """Open a photo and normalise it for inference."""
    img = Image.open(path)
    # Phone photos carry rotation in EXIF rather than in the pixel data.
    img = ImageOps.exif_transpose(img)
    img = img.convert("L" if grayscale else "RGB")
    img = ImageOps.autocontrast(img, cutoff=1)

    if max(img.size) > max_edge:
        scale = max_edge / max(img.size)
        new_size = (round(img.width * scale), round(img.height * scale))
        img = img.resize(new_size, Image.LANCZOS)

    return img


def to_base64_png(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def collect(paths: list[Path]) -> list[Path]:
    """Expand directories into a sorted list of image files.

    Sorted by name, which is what determines page order on a merged run.
    """
    found: list[Path] = []
    for p in paths:
        if p.is_dir():
            found.extend(
                c for c in sorted(p.iterdir())
                if c.suffix.lower() in SUPPORTED_SUFFIXES
            )
        elif p.suffix.lower() in SUPPORTED_SUFFIXES:
            found.append(p)
        else:
            raise ValueError(f"not a supported image: {p}")
    if not found:
        raise ValueError("no images found")
    return found
