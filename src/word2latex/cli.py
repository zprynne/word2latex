"""Command-line interface."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from word2latex import __version__, evaluate, latex, preprocess, prompt
from word2latex.backend import DEFAULT_MODEL, BackendError, Ollama
from word2latex.compile import compile_tex, find_engine, install_hint


def _log(msg: str = "") -> None:
    print(msg, file=sys.stderr, flush=True)


def _read_glossary(path: Path | None) -> str | None:
    if path is None:
        return None
    if not path.exists():
        raise SystemExit(f"glossary not found: {path}")
    return path.read_text()


def _convert_one(client, image_path, out_dir, index, glossary, max_edge, color):
    img = preprocess.load(image_path, max_edge=max_edge, grayscale=not color)
    raw = client.transcribe(
        preprocess.to_base64_png(img),
        prompt.SYSTEM,
        prompt.build_user_prompt(glossary),
    )
    return latex.process_page(
        source=image_path,
        raw_body=raw,
        image=img,
        assets_dir=out_dir / "figures",
        page_index=index,
    )


def cmd_convert(args: argparse.Namespace) -> int:
    images = preprocess.collect([Path(p) for p in args.images])
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    client = Ollama(model=args.model, host=args.host)
    try:
        client.check()
    except BackendError as e:
        _log(f"error: {e}")
        return 1

    if find_engine() is None and not args.no_compile:
        _log("note: no LaTeX engine found — writing .tex only, skipping PDF.")
        for line in install_hint().splitlines():
            _log(f"    {line}")
        _log("")

    glossary = _read_glossary(Path(args.glossary) if args.glossary else None)
    _log(f"{len(images)} page(s), model {args.model}\n")

    pages = []
    for i, image_path in enumerate(images, start=1):
        _log(f"  [{i}/{len(images)}] {image_path.name} ... ")
        try:
            page = _convert_one(
                client, image_path, out_dir, i, glossary, args.max_edge, args.color
            )
        except BackendError as e:
            _log(f"      failed: {e}")
            if args.keep_going:
                continue
            return 1
        notes = []
        if page.unsure:
            notes.append(f"{len(page.unsure)} unsure")
        if page.figures:
            notes.append(f"{page.figures} figure(s) embedded")
        _log(f"      ok{' — ' + ', '.join(notes) if notes else ''}")
        pages.append(page)

    if not pages:
        _log("\nnothing converted.")
        return 1

    groups = [pages] if args.merge else [[p] for p in pages]
    written: list[Path] = []

    for group in groups:
        stem = args.name if args.merge else group[0].source.stem
        tex_path = out_dir / f"{stem}.tex"
        tex_path.write_text(latex.build_document(group, title=args.title))
        written.append(tex_path)

        if args.no_compile:
            continue
        result = compile_tex(tex_path)
        if result.ok:
            _log(f"\n  {tex_path.name} -> {result.pdf.name}")
        else:
            _log(f"\n  {tex_path.name}: compile failed")
            for line in result.log.splitlines()[:12]:
                _log(f"      {line}")

    total_unsure = sum(len(p.unsure) for p in pages)
    _log(f"\nwrote {len(written)} document(s) to {out_dir}/")
    if total_unsure:
        _log(f"{total_unsure} passage(s) flagged — see the 'Review these' page, "
             f"or grep for '%% UNSURE' in the .tex")
    return 0


def cmd_eval(args: argparse.Namespace) -> int:
    pages_dir, truth_dir = Path(args.pages), Path(args.truth)
    pairs = evaluate.find_pairs(pages_dir, truth_dir)
    if not pairs:
        _log(f"no (image, .tex) pairs found between {pages_dir}/ and {truth_dir}/.")
        _log("Each photo needs a hand-transcribed .tex of the same stem.")
        return 1

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    glossary = _read_glossary(Path(args.glossary) if args.glossary else None)
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    _log(f"{len(pairs)} page(s) x {len(models)} model(s)\n")

    scores = []
    for model in models:
        client = Ollama(model=model, host=args.host)
        try:
            client.check()
        except BackendError as e:
            _log(f"skipping {model}: {e}")
            continue

        _log(f"{model}")
        page_scores = []
        for i, (image_path, truth_path) in enumerate(pairs, start=1):
            model_dir = out_dir / model.replace(":", "_").replace("/", "_")
            model_dir.mkdir(parents=True, exist_ok=True)
            try:
                page = _convert_one(
                    client, image_path, model_dir, i, glossary, args.max_edge, args.color
                )
            except BackendError as e:
                _log(f"  {image_path.name}: {e}")
                continue

            tex_path = model_dir / f"{image_path.stem}.tex"
            tex_path.write_text(latex.build_document([page]))
            compiled = compile_tex(tex_path).ok if find_engine() else False

            reference = truth_path.read_text()
            sim = evaluate.similarity(reference, page.body)
            page_scores.append(evaluate.PageScore(
                name=image_path.name,
                similarity=sim,
                compiled=compiled,
                ref_tokens=len(evaluate.tokenize(reference)),
                cand_tokens=len(evaluate.tokenize(page.body)),
            ))
            _log(f"  {sim:>6.1%}  {image_path.name}")

        if page_scores:
            scores.append(evaluate.ModelScore(model=model, pages=page_scores))

    if not scores:
        _log("\nno model produced results.")
        return 1

    report = evaluate.format_report(scores)
    _log("\n" + report)
    report_path = out_dir / "report.txt"
    report_path.write_text(report + "\n")
    _log(f"\nreport: {report_path}")
    if find_engine() is None:
        _log("note: no LaTeX engine, so the 'compiles' column is 0% for every model.")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    ok = True
    client = Ollama(model=args.model, host=args.host)
    try:
        models = client.available_models()
        _log(f"ollama      ok — {len(models)} model(s): {', '.join(models) or 'none'}")
        try:
            client.check()
            _log(f"model       ok — {args.model}")
        except BackendError as e:
            _log(f"model       MISSING — {e}")
            ok = False
    except BackendError as e:
        _log(f"ollama      UNREACHABLE — {e}")
        ok = False

    engine = find_engine()
    if engine:
        _log(f"latex       ok — {engine}")
    else:
        _log("latex       MISSING")
        for line in install_hint().splitlines():
            _log(f"            {line.strip()}")
        ok = False

    try:
        import PIL
        _log(f"pillow      ok — {PIL.__version__}")
    except ImportError:
        _log("pillow      MISSING — pip install pillow")
        ok = False

    _log("\nready." if ok else "\nsome components missing (see README).")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="w2l",
        description="Convert photos of handwritten notes into LaTeX, fully offline.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(p, with_model=True):
        if with_model:
            p.add_argument("--model", default=DEFAULT_MODEL, help="Ollama model tag")
        p.add_argument("--host", default="http://127.0.0.1:11434")
        p.add_argument("--glossary", help="text file of handwriting quirks for the prompt")
        p.add_argument("--max-edge", type=int, default=preprocess.MAX_EDGE)
        p.add_argument("--color", action="store_true", help="keep colour (default: grayscale)")

    c = sub.add_parser("convert", help="convert photos to .tex + .pdf")
    c.add_argument("images", nargs="+", help="image files or a directory of them")
    c.add_argument("-o", "--out", default="out", help="output directory (default: out)")
    c.add_argument("--merge", action="store_true", help="one document for all pages")
    c.add_argument("--name", default="notes", help="filename stem when merging")
    c.add_argument("--title", help="title to print at the top of the document")
    c.add_argument("--no-compile", action="store_true", help="write .tex, skip the PDF")
    c.add_argument("--keep-going", action="store_true", help="continue past a failed page")
    add_common(c)
    c.set_defaults(func=cmd_convert)

    e = sub.add_parser("eval", help="score models against hand-transcribed ground truth")
    e.add_argument("--pages", required=True, help="directory of sample photos")
    e.add_argument("--truth", required=True, help="directory of reference .tex, matched by stem")
    e.add_argument("--models", default=DEFAULT_MODEL, help="comma-separated Ollama tags")
    e.add_argument("-o", "--out", default="out/eval")
    add_common(e, with_model=False)
    e.set_defaults(func=cmd_eval)

    k = sub.add_parser("check", help="report what is installed and what is missing")
    add_common(k)
    k.set_defaults(func=cmd_check)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        _log("\ninterrupted.")
        return 130
    except (ValueError, OSError) as exc:
        _log(f"error: {exc}")
        return 1
