"""Pipeline tests. Standard library only; no network, no model, no LaTeX needed.

The live seams this cannot cover are documented in HANDOFF.md: an actual Ollama
generation, and an actual pdflatex run. Everything either side of those is here.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from PIL import Image, ImageDraw

from word2latex import evaluate, latex, preprocess
from word2latex.backend import BackendError, Ollama, _strip_fences


def make_photo(path: Path, size=(2400, 3200)) -> Path:
    img = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(img)
    draw.rectangle([600, 1600, 1800, 2400], outline="black", width=8)
    img.save(path)
    return path


class TestPreprocess(unittest.TestCase):
    def test_downscales_and_grayscales(self):
        with TemporaryDirectory() as td:
            src = make_photo(Path(td) / "p.png")
            img = preprocess.load(src)
            self.assertLessEqual(max(img.size), preprocess.MAX_EDGE)
            self.assertEqual(img.mode, "L")

    def test_preserves_aspect_ratio(self):
        with TemporaryDirectory() as td:
            src = make_photo(Path(td) / "p.png", size=(4000, 2000))
            img = preprocess.load(src)
            self.assertAlmostEqual(img.width / img.height, 2.0, places=2)

    def test_small_image_not_upscaled(self):
        with TemporaryDirectory() as td:
            src = make_photo(Path(td) / "p.png", size=(400, 300))
            self.assertEqual(preprocess.load(src).size, (400, 300))

    def test_collect_sorts_and_filters(self):
        with TemporaryDirectory() as td:
            d = Path(td)
            for name in ("b.jpg", "a.png", "notes.txt"):
                (d / name).touch()
            found = preprocess.collect([d])
            self.assertEqual([p.name for p in found], ["a.png", "b.jpg"])

    def test_collect_rejects_empty(self):
        with TemporaryDirectory() as td:
            with self.assertRaises(ValueError):
                preprocess.collect([Path(td)])


class TestDiagramMarkers(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.img = Image.new("L", (1000, 1000), "white")

    def tearDown(self):
        self.tmp.cleanup()

    def process(self, body):
        return latex.process_page(
            Path("page01.jpg"), body, self.img, self.dir / "figures", 1
        )

    def test_boxed_diagram_is_cropped(self):
        page = self.process("%% DIAGRAM [0.2,0.2,0.6,0.6]: a DFA")
        self.assertEqual(page.figures, 1)
        self.assertIn(r"\w2lfigure", page.body)
        self.assertNotIn("%% DIAGRAM", page.body)
        crop = Image.open(next((self.dir / "figures").iterdir()))
        # 0.4 of 1000 plus 0.02 padding each side.
        self.assertEqual(crop.size, (440, 440))

    def test_diagram_without_box_uses_full_page(self):
        page = self.process("%% DIAGRAM: some sketch")
        self.assertEqual(page.figures, 1)
        self.assertEqual(
            Image.open(next((self.dir / "figures").iterdir())).size, (1000, 1000)
        )

    def test_out_of_range_box_falls_back(self):
        page = self.process("%% DIAGRAM [0,0,5.0,5.0]: bad estimate")
        self.assertEqual(page.figures, 1)
        self.assertEqual(
            Image.open(next((self.dir / "figures").iterdir())).size, (1000, 1000)
        )

    def test_degenerate_box_falls_back(self):
        page = self.process("%% DIAGRAM [0.5,0.5,0.5,0.5]: zero area")
        self.assertEqual(
            Image.open(next((self.dir / "figures").iterdir())).size, (1000, 1000)
        )

    def test_inverted_box_is_normalised(self):
        page = self.process("%% DIAGRAM [0.6,0.6,0.2,0.2]: reversed corners")
        self.assertEqual(
            Image.open(next((self.dir / "figures").iterdir())).size, (440, 440)
        )

    def test_multiple_diagrams_get_distinct_files(self):
        page = self.process(
            "%% DIAGRAM [0.1,0.1,0.3,0.3]: one\ntext\n%% DIAGRAM [0.5,0.5,0.7,0.7]: two"
        )
        self.assertEqual(page.figures, 2)
        self.assertEqual(len(list((self.dir / "figures").iterdir())), 2)

    def test_caption_is_latex_escaped(self):
        page = self.process("%% DIAGRAM [0.1,0.1,0.3,0.3]: costs 50% & rising")
        self.assertIn(r"50\%", page.body)
        self.assertIn(r"\&", page.body)


class TestUnsureMarkers(unittest.TestCase):
    def process(self, body):
        with TemporaryDirectory() as td:
            return latex.process_page(
                Path("p.jpg"), body, Image.new("L", (100, 100)), Path(td) / "f", 1
            )

    def test_collects_notes(self):
        page = self.process("x = 1\n%% UNSURE: might be 7\ny = 2\n%% UNSURE: smudged")
        self.assertEqual(len(page.unsure), 2)
        self.assertEqual(page.unsure[0], "might be 7")

    def test_clean_page_has_none(self):
        self.assertEqual(self.process(r"$x = 1$").unsure, [])

    def test_review_section_appears_only_when_needed(self):
        flagged = self.process("%% UNSURE: unreadable")
        clean = self.process("all clear")
        self.assertIn("Review these", latex.build_document([flagged]))
        self.assertNotIn("Review these", latex.build_document([clean]))


class TestDocument(unittest.TestCase):
    def page(self, body="content"):
        with TemporaryDirectory() as td:
            return latex.process_page(
                Path("p.jpg"), body, Image.new("L", (100, 100)), Path(td) / "f", 1
            )

    def test_is_standalone(self):
        doc = latex.build_document([self.page()])
        for required in (r"\documentclass", r"\begin{document}", r"\end{document}",
                         r"\usepackage{amsmath,amssymb,amsthm}"):
            self.assertIn(required, doc)

    def test_merge_inserts_page_breaks(self):
        doc = latex.build_document([self.page(), self.page(), self.page()])
        self.assertEqual(doc.count(r"\clearpage"), 2)

    def test_single_page_has_no_break(self):
        self.assertNotIn(r"\clearpage", latex.build_document([self.page()]))

    def test_title_is_escaped(self):
        doc = latex.build_document([self.page()], title="Week 3 & 4 (100%)")
        self.assertIn(r"\&", doc)
        self.assertIn(r"\%", doc)


class TestEvaluate(unittest.TestCase):
    def test_identical_scores_one(self):
        self.assertEqual(evaluate.similarity(r"\alpha + \beta", r"\alpha + \beta"), 1.0)

    def test_unrelated_scores_low(self):
        self.assertLess(evaluate.similarity(r"\alpha", "completely other words"), 0.5)

    def test_comments_do_not_affect_score(self):
        base = r"$x=1$"
        self.assertEqual(evaluate.similarity(base, base + "\n%% UNSURE: whatever"), 1.0)

    def test_whitespace_does_not_affect_score(self):
        self.assertEqual(
            evaluate.similarity(r"\alpha  +   \beta", "\\alpha\n+\n\\beta"), 1.0
        )

    def test_tokenizer_keeps_commands_whole(self):
        self.assertIn(r"\alpha", evaluate.tokenize(r"\alpha_1"))
        self.assertIn(r"\begin", evaluate.tokenize(r"\begin{align*}"))

    def test_empty_inputs(self):
        self.assertEqual(evaluate.similarity("", ""), 1.0)
        self.assertEqual(evaluate.similarity(r"\alpha", ""), 0.0)

    def test_symmetric(self):
        a, b = r"\alpha + \beta", r"\alpha - \gamma"
        self.assertAlmostEqual(evaluate.similarity(a, b), evaluate.similarity(b, a))

    def test_find_pairs_matches_by_stem(self):
        with TemporaryDirectory() as td:
            pages, truth = Path(td) / "p", Path(td) / "t"
            pages.mkdir(), truth.mkdir()
            (pages / "a.jpg").touch()
            (pages / "b.jpg").touch()
            (truth / "a.tex").touch()  # b has no ground truth
            pairs = evaluate.find_pairs(pages, truth)
            self.assertEqual([p[0].name for p in pairs], ["a.jpg"])


class TestOllamaClient(unittest.TestCase):
    """Covers the request shape and response handling without a live server."""

    def test_transcribe_builds_correct_request(self):
        captured = {}

        def fake_post(self, path, payload, timeout=None):
            captured["path"] = path
            captured["payload"] = payload
            return {"response": r"\section{Hi}"}

        with mock.patch.object(Ollama, "_post", fake_post):
            out = Ollama(model="m").transcribe("BASE64", "SYSTEM", "USER")

        self.assertEqual(captured["path"], "/api/generate")
        p = captured["payload"]
        self.assertEqual(p["model"], "m")
        self.assertEqual(p["system"], "SYSTEM")
        self.assertEqual(p["prompt"], "USER")
        self.assertEqual(p["images"], ["BASE64"])
        self.assertFalse(p["stream"])
        self.assertEqual(out, r"\section{Hi}")
        json.dumps(p)  # must be serialisable

    def test_error_field_raises(self):
        with mock.patch.object(Ollama, "_post", lambda *a, **k: {"error": "no model"}):
            with self.assertRaises(BackendError):
                Ollama().transcribe("x", "s", "u")

    def test_empty_response_raises(self):
        with mock.patch.object(Ollama, "_post", lambda *a, **k: {"response": "   "}):
            with self.assertRaises(BackendError):
                Ollama().transcribe("x", "s", "u")

    def test_check_accepts_bare_name_for_tagged_model(self):
        with mock.patch.object(Ollama, "available_models", lambda s: ["qwen2.5vl:7b"]):
            Ollama(model="qwen2.5vl").check()          # bare name matches
            Ollama(model="qwen2.5vl:7b").check()       # exact match
            with self.assertRaises(BackendError):
                Ollama(model="absent").check()

    def test_strip_fences(self):
        self.assertEqual(_strip_fences("```latex\n\\alpha\n```"), r"\alpha")
        self.assertEqual(_strip_fences("```\n\\alpha\n```"), r"\alpha")
        self.assertEqual(_strip_fences(r"\alpha"), r"\alpha")
        # An unterminated fence should not eat the content.
        self.assertEqual(_strip_fences("```latex\n\\alpha"), r"\alpha")


if __name__ == "__main__":
    unittest.main()
