---
name: batch-translate
description: Batch-translate a directory of slide images into a Simplified Chinese bilingual PDF. The pipeline OCRs each image with positional metadata, translates every text element to zh-CN with full-slide context, writes one `<image>_overlay.json` per image, then renders a 2-up "translator notes" PDF (original on the left, faded original with Chinese overlays on the right). Trigger this skill whenever the user wants to translate a folder of slides, decks, screenshots, or images; produce bilingual or zh-CN versions of presentation content; OCR slides and overlay translations; or generate a "Google Translate-style" overlay PDF for a presentation. Use this skill even if the user does not say the word "skill" — phrases like "translate these slides to Chinese," "make a bilingual deck," "OCR this folder of decks," or "overlay translations on these images" should all trigger it.
---

# batch-translate

Translate a directory of slide images into Simplified Chinese and produce a 2-up bilingual PDF. The skill is a three-stage pipeline:

1. **OCR + layout extraction.** For each image, call the local `claude` CLI with a high-precision OCR prompt to extract every visible text element with pixel-accurate `render_box` and `tight_glyph_box` geometry, plus typography metadata (font size, weight, color, alignment).
2. **Contextual translation.** Send the full OCR JSON as slide context, plus a compact element list, back to `claude` and ask for `{id, zh_text}` translations. Merge translations into the OCR JSON as `zh_text` and `en_text` (en_text is `text_logical`).
3. **PDF rendering.** Build one Letter-landscape page per image: original slide on the left, the same slide rendered at ~10% opacity (white wash at 90% alpha) on the right with Chinese translations overlaid in the original positions, like a Google Translate-style overlay.

Per overlay JSON file is written as `<image_stem>_overlay.json` next to each image. The combined PDF lands at `<dir>/<dir_name>_translations.pdf` by default.

Per user policy this skill **always reprocesses every image** on each run; existing `*_overlay.json` files are overwritten.

## When to use

Trigger this skill when the user mentions:
- translating a folder/directory of slides, decks, screenshots, or PNG/JPG images
- producing a bilingual deck, a Chinese (zh-CN / Simplified Chinese) version of slides, or a translation overlay
- OCRing slides and laying translations on top
- generating Google-Translate-style overlays for a deck
- "batch translate", "multi-image translate", "batch OCR slides"

Do not use for single-image OCR with no translation goal, or for translating documents that aren't presentation/slide images.

## Dependencies

- `claude` CLI must be on PATH (this is what powers OCR and translation).
- Python 3.10+ with `Pillow` and `reportlab` installed:
  ```bash
  pip install -r requirements.txt
  ```
- A system CJK font is recommended (e.g., PingFang SC on macOS, Noto Sans CJK on Linux, Microsoft YaHei on Windows). If no system CJK font is found, the renderer falls back to ReportLab's built-in `STSong-Light` CIDFont, which renders Simplified Chinese without any extra assets.

## How to run

The orchestrator is `scripts/batch_translate.py`. Always pass an absolute directory path.

```bash
python scripts/batch_translate.py /absolute/path/to/slides_dir
```

Useful flags:
- `--json-only` — run OCR + translation, skip PDF.
- `--pdf-only` — skip OCR/translation, render PDF from existing `*_overlay.json` files.
- `--pdf-out PATH` — override the output PDF path.
- `--fade FLOAT` — opacity of the white wash on the right panel (default `0.9`; smaller value = the source slide bleeds through more).

When invoking from a chat session: prefer running the orchestrator end-to-end (no flags) on the directory the user supplies. If the user only wants to re-render the PDF after hand-editing a translation, use `--pdf-only`.

## File layout produced

```
slides_dir/
├── Andruil-01.png
├── Andruil-01_overlay.json     <- written by step 2
├── Andruil-02.png
├── Andruil-02_overlay.json
├── ...
└── slides_dir_translations.pdf <- written by step 3
```

Each `*_overlay.json` is the original OCR JSON with two new fields per element:
- `en_text` — the source text (copy of `text_logical`)
- `zh_text` — the Simplified Chinese translation

A small `translation` block at the top level records `target_language`, `source_count`, and `translated_count` for traceability.

## Image formats

PNG, JPG/JPEG, and WebP are recognized. Other extensions are ignored.

## Internals

- `prompts/ocr_overlay.txt` — the OCR + layout extraction prompt. Sent to `claude -p` along with `@<absolute_image_path>`.
- `prompts/translate_zh.txt` — the translation prompt. Sent with the full OCR JSON as `SLIDE_CONTEXT` and the element list as `ELEMENTS`.
- `scripts/extract_text.py` — OCR step. Defensive JSON parsing handles stray code fences. Saves raw output to `<image>.ocr_raw.txt` if JSON parsing fails.
- `scripts/translate.py` — translation step. Returns `{id, zh_text}` array; merger preserves all OCR fields and adds `en_text` and `zh_text` to each element.
- `scripts/render_pdf.py` — PDF builder. Letter landscape, 2-up. Tries system CJK fonts in this order: PingFang SC, STHeiti, Hiragino Sans GB (macOS); Noto Sans CJK, WQY ZenHei (Linux); Microsoft YaHei, SimHei, SimSun (Windows). Falls back to `UnicodeCIDFont('STSong-Light')`.

## Known caveats

- OCR + translation each call `claude` once per image. A 30-image deck makes ~60 CLI calls; total runtime depends on slide complexity.
- The faded right panel paints a small white background pad behind each Chinese overlay so text stays legible on busy slide backgrounds. To remove the pad, edit `_draw_zh_overlay` in `scripts/render_pdf.py`.
- If a slide's Chinese translation overflows its `render_box`, the renderer first retries at 60% font size; if it still doesn't fit it may clip. Slides with very tight layouts may benefit from increasing `--fade` so original geometry is more visible, or post-editing the `render_box` in the JSON.
