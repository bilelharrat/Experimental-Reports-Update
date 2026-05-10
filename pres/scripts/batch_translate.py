#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "Pillow>=10.0.0",
#     "reportlab>=4.0.0",
#     "numpy>=1.24",
#     "opencv-python-headless>=4.8",
# ]
# ///
"""
Orchestrator for the batch-translate skill.

For every image in a directory:
    1. Run OCR + layout extraction via the claude CLI.
    2. Translate to Simplified Chinese via the claude CLI, using the
       full slide as context.
    3. Write `<image_stem>_overlay.json` next to the image, augmenting
       each text element with `en_text` and `zh_text`.

Then, render a single 2-up bilingual PDF with one page per image:
    [ original  |  faded original + Chinese overlay ]

Per user policy this script always reprocesses; existing
`*_overlay.json` files are overwritten.

Usage:
    python batch_translate.py /path/to/slides_dir
    python batch_translate.py /path/to/slides_dir --pdf-only
    python batch_translate.py /path/to/slides_dir --json-only
    python batch_translate.py /path/to/slides_dir --pdf-out /tmp/decks.pdf
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# Make sibling scripts importable when run as `python batch_translate.py`.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from extract_text import extract_text, ClaudeCLIError as OCRError  # noqa: E402
from translate import translate_overlay, ClaudeCLIError as TranslateError  # noqa: E402
from render_pdf import render_pdf, IMAGE_EXTS  # noqa: E402


def _discover_images(directory: Path) -> list[Path]:
    return sorted(
        p for p in directory.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS
    )


def _process_one(image_path: Path) -> Path | None:
    """
    Run the OCR + translation pipeline for a single image. Returns the
    overlay JSON path on success, None on failure (after logging).
    """
    overlay_path = image_path.with_name(f"{image_path.stem}_overlay.json")
    try:
        t0 = time.time()
        print(f"  [1/2] OCR        ... ", end="", flush=True)
        ocr_data = extract_text(image_path)
        n_elem = len(ocr_data.get("elements", []))
        print(f"ok ({n_elem} elements, {time.time() - t0:.1f}s)")

        t1 = time.time()
        print(f"  [2/2] translate  ... ", end="", flush=True)
        overlay = translate_overlay(ocr_data)
        print(f"ok ({time.time() - t1:.1f}s)")

        overlay_path.write_text(
            json.dumps(overlay, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"        -> wrote {overlay_path.name}")
        return overlay_path
    except (OCRError, TranslateError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return None
    except Exception as exc:  # surface unexpected errors but keep going
        print(f"FAIL (unexpected): {exc}", file=sys.stderr)
        return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Batch OCR + translate slide images, then render a bilingual PDF."
    )
    parser.add_argument("directory", type=Path, help="Directory containing slide images.")
    parser.add_argument(
        "--pdf-only",
        action="store_true",
        help="Skip extraction and translation; only render the PDF from existing *_overlay.json files.",
    )
    parser.add_argument(
        "--json-only",
        action="store_true",
        help="Run extraction + translation but skip the PDF.",
    )
    parser.add_argument(
        "--pdf-out",
        type=Path,
        default=None,
        help="PDF output path. Default: <dir>/<dir_name>_translations.pdf",
    )
    parser.add_argument(
        "--fade",
        type=float,
        default=0.9,
        help="Right-panel white-wash opacity (0..1). Default 0.9.",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip images that already have a `<stem>_overlay.json` next to them. "
             "Useful for retrying only the slides that failed in a previous run.",
    )
    args = parser.parse_args()

    directory: Path = args.directory.resolve()
    if not directory.is_dir():
        print(f"ERROR: not a directory: {directory}", file=sys.stderr)
        return 1
    if args.pdf_only and args.json_only:
        print("ERROR: --pdf-only and --json-only are mutually exclusive.", file=sys.stderr)
        return 2

    images = _discover_images(directory)
    if not images:
        print(f"ERROR: no images ({sorted(IMAGE_EXTS)}) found in {directory}", file=sys.stderr)
        return 1

    print(f"Found {len(images)} image(s) in {directory}")

    successful_pairs: list[tuple[Path, Path]] = []

    if not args.pdf_only:
        for idx, image_path in enumerate(images, 1):
            existing = image_path.with_name(f"{image_path.stem}_overlay.json")
            if args.skip_existing and existing.is_file():
                print(f"\n[{idx}/{len(images)}] {image_path.name}  (skip — overlay exists)")
                successful_pairs.append((image_path, existing))
                continue
            print(f"\n[{idx}/{len(images)}] {image_path.name}")
            overlay_path = _process_one(image_path)
            if overlay_path:
                successful_pairs.append((image_path, overlay_path))
    else:
        # PDF-only: pair images with already-existing overlays.
        for image_path in images:
            overlay_path = image_path.with_name(f"{image_path.stem}_overlay.json")
            if overlay_path.is_file():
                successful_pairs.append((image_path, overlay_path))
        print(f"PDF-only mode: found {len(successful_pairs)} existing overlay JSONs.")

    if args.json_only:
        print(f"\nDone. {len(successful_pairs)}/{len(images)} overlay JSONs written.")
        return 0 if successful_pairs else 1

    if not successful_pairs:
        print("\nNo overlay pairs available; skipping PDF.", file=sys.stderr)
        return 1

    pdf_out = args.pdf_out or directory / f"{directory.name}_translations.pdf"
    print(f"\nRendering PDF -> {pdf_out}")
    render_pdf(successful_pairs, pdf_out, fade_alpha=args.fade)
    print(f"Done. PDF: {pdf_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
