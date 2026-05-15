"""Convert a ``.docx`` to PDF via Microsoft Word (macOS osascript).

This mirrors the PowerPoint→PDF helper in ``files_store.py``: the memo
skill renders professional ``.docx`` files with the docx skill, and we
need faithful PDF renditions for the in-app preview popup. Word renders
both the English and the Simplified-Chinese (CJK) memo correctly, and
osascript automation of Office is already the sanctioned pattern in this
codebase, so we reuse it here rather than introducing LibreOffice/pandoc.

macOS only. On any other platform, or if Word/automation isn't available,
``convert_docx_to_pdf`` returns ``(False, reason)`` and the caller is
expected to treat the PDF as optional (the ``.docx`` is the real
deliverable; the preview just won't be offered).
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

CONVERSION_TIMEOUT = float(os.environ.get("DOCX_PDF_TIMEOUT", "180"))

# Word runs in macOS's App Sandbox and can't read project paths
# (data/memos/...) or per-process tempdirs (/var/folders/...). /tmp is
# world-writable and Office's sandbox allows it, so stage there. Shared
# with the PPTX path's default root on purpose — same sandbox constraint.
_DEFAULT_STAGE_ROOT = Path("/tmp/bsh-research-center")
_STAGE_ROOT = Path(os.environ.get("PPT_STAGE_DIR") or _DEFAULT_STAGE_ROOT)

# Open the input, save as PDF, close without saving. `launch` (vs
# `activate`) keeps Word in the background so it doesn't steal focus.
# Word's `open` verb does NOT reliably bind its result to a variable
# (`set x to open ...` errors with -2753), so we open and then grab
# `active document`. `save as` takes a POSIX path for `file name` and
# the `format PDF` enum on modern Word.
_WORD_APPLESCRIPT = """on run argv
    set inputPath to item 1 of argv
    set outputPath to item 2 of argv
    tell application "Microsoft Word"
        launch
        open POSIX file inputPath
        set theDoc to active document
        save as theDoc file name outputPath file format format PDF
        close theDoc saving no
    end tell
end run
"""


def _interpret_applescript_error(detail: str) -> str:
    """Map common AppleScript / Word error codes to a plain-English hint."""
    if "-1743" in detail or "Not authorized" in detail:
        return (
            "macOS Automation permission denied. Open System Settings → "
            "Privacy & Security → Automation, find the terminal / IDE "
            "running uvicorn, and enable the checkbox next to "
            "Microsoft Word."
        )
    if "-9074" in detail or "-1728" in detail or "-43" in detail:
        return (
            "Word can't read or write the file at the chosen path. This "
            "usually means macOS App Sandbox is blocking access. Grant "
            "Full Disk Access to Microsoft Word in System Settings → "
            "Privacy & Security → Full Disk Access."
        )
    return detail[:600]


def convert_docx_to_pdf(src: Path, dst: Path) -> tuple[bool, str | None]:
    """Render ``src`` (.docx) to ``dst`` (.pdf) via Word.

    Returns ``(success, error_message)``. Idempotent — a fast no-op if
    ``dst`` already exists. macOS only.
    """
    if dst.exists():
        return True, None
    if not src.exists():
        return False, f"Source file missing: {src.name}"
    if sys.platform != "darwin":
        msg = f"Word conversion is macOS-only (running on {sys.platform})."
        logger.warning("%s Skipping %s", msg, src)
        return False, msg

    script_file: Path | None = None
    stage_dir: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".applescript", delete=False
        ) as f:
            f.write(_WORD_APPLESCRIPT)
            script_file = Path(f.name)

        # Stage input + output where Word's sandbox can reach them.
        _STAGE_ROOT.mkdir(parents=True, exist_ok=True)
        stage_dir = Path(tempfile.mkdtemp(prefix="docx-", dir=str(_STAGE_ROOT)))
        staged_in = stage_dir / src.name  # preserve .docx extension
        shutil.copy2(src, staged_in)
        staged_out = stage_dir / "out.pdf"

        try:
            subprocess.run(
                [
                    "osascript",
                    str(script_file),
                    str(staged_in),
                    str(staged_out),
                ],
                check=True,
                timeout=CONVERSION_TIMEOUT,
                capture_output=True,
            )
        except FileNotFoundError as exc:
            msg = f"osascript not found: {exc}"
            logger.warning("Can't convert %s: %s", src, msg)
            return False, msg
        except subprocess.TimeoutExpired:
            msg = (
                f"Word conversion timed out after {CONVERSION_TIMEOUT:.0f}s. "
                "Set DOCX_PDF_TIMEOUT to raise the cap."
            )
            logger.warning("%s (%s)", msg, src)
            return False, msg
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or b"").decode("utf-8", "ignore").strip()
            stdout = (exc.stdout or b"").decode("utf-8", "ignore").strip()
            detail = stderr or stdout or "(no output)"
            msg = f"Word conversion failed: {_interpret_applescript_error(detail)}"
            logger.warning("%s (raw: %s) (%s)", msg, detail[:300], src)
            return False, msg

        if not staged_out.exists():
            msg = "Word produced no output (no PDF written)."
            logger.warning("%s (%s)", msg, src)
            return False, msg

        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(staged_out), str(dst))
        return True, None
    finally:
        if script_file is not None:
            try:
                script_file.unlink(missing_ok=True)
            except Exception:
                pass
        if stage_dir is not None:
            try:
                shutil.rmtree(stage_dir, ignore_errors=True)
            except Exception:
                pass
