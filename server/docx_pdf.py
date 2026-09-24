"""Convert a ``.docx`` to PDF via Microsoft Word (macOS osascript).

This mirrors the PowerPoint→PDF helper in ``files_store.py``: the memo
worker renders professional ``.docx`` files with the fixed renderer, and
we need faithful PDF renditions for the in-app preview popup. Word renders
both the English and the Simplified-Chinese (CJK) memo correctly, and
osascript automation of Office is already the sanctioned pattern in this
codebase, so we reuse it here rather than introducing LibreOffice/pandoc.

Word is the primary converter (macOS only). Word jobs are serialized with a
process-wide lock: two concurrent automations of the same Word instance
collide. When Word is unavailable or fails and LibreOffice's ``soffice`` is
on PATH, ``soffice --headless --convert-to pdf`` is tried instead (its
fidelity differs from Word's for YaHei / Aptos). With neither,
``convert_docx_to_pdf`` returns ``(False, reason)`` and the caller is
expected to treat the PDF as optional (the ``.docx`` is the real
deliverable; the preview just won't be offered).
"""
from __future__ import annotations

import logging
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

CONVERSION_TIMEOUT = float(os.environ.get("DOCX_PDF_TIMEOUT", "45"))

# One Word (or soffice) conversion at a time, process-wide. Waiting callers
# give up after this long rather than stacking behind a stuck automation.
_CONVERSION_LOCK = threading.Lock()
LOCK_WAIT_SECONDS = float(os.environ.get("DOCX_PDF_LOCK_WAIT", "120"))

_WORD_APP_PATHS = (
    Path("/Applications/Microsoft Word.app"),
    Path.home() / "Applications" / "Microsoft Word.app",
)


def word_available() -> bool:
    """Word automation is possible here: macOS, osascript, and Word installed."""
    if sys.platform != "darwin" or shutil.which("osascript") is None:
        return False
    return any(path.exists() for path in _WORD_APP_PATHS)


def soffice_path() -> str | None:
    """LibreOffice's command-line converter, when installed."""
    return shutil.which("soffice") or shutil.which("libreoffice")


_AVAILABLE_TTL_SECONDS = 60.0
_available_cache: tuple[float, bool] | None = None


def converter_available() -> bool:
    """Word or LibreOffice is present. Cached for a minute: the Reports list
    asks once per document, and PATH lookups add up."""
    global _available_cache
    import time

    now = time.monotonic()
    cached = _available_cache
    if cached is not None and now - cached[0] < _AVAILABLE_TTL_SECONDS:
        return cached[1]
    value = word_available() or soffice_path() is not None
    _available_cache = (now, value)
    return value

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


def _run_osascript(args: list[str]) -> subprocess.CompletedProcess[bytes]:
    """Run osascript with a timeout that also cleans up stuck children."""
    proc = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        stdout, stderr = proc.communicate(timeout=CONVERSION_TIMEOUT)
    except subprocess.TimeoutExpired as exc:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        try:
            stdout, stderr = proc.communicate(timeout=5.0)
        except Exception:
            stdout = exc.output or b""
            stderr = exc.stderr or b""
        raise subprocess.TimeoutExpired(
            args,
            CONVERSION_TIMEOUT,
            output=stdout,
            stderr=stderr,
        ) from exc
    if proc.returncode:
        raise subprocess.CalledProcessError(
            proc.returncode,
            args,
            output=stdout,
            stderr=stderr,
        )
    return subprocess.CompletedProcess(args, proc.returncode, stdout, stderr)


def convert_docx_to_pdf(src: Path, dst: Path) -> tuple[bool, str | None]:
    """Render ``src`` (.docx) to ``dst`` (.pdf): Word first, then LibreOffice
    when ``soffice`` is on PATH.

    Returns ``(success, error_message)``. Idempotent — a fast no-op if
    ``dst`` already exists. Conversions are serialized process-wide.
    """
    if dst.exists():
        return True, None
    if not src.exists():
        return False, f"Source file missing: {src.name}"
    if not _CONVERSION_LOCK.acquire(timeout=LOCK_WAIT_SECONDS):
        return False, (
            f"Another document conversion is still running after "
            f"{LOCK_WAIT_SECONDS:.0f}s; try again shortly."
        )
    try:
        if dst.exists():  # finished by the caller we waited behind
            return True, None
        word_error: str | None = None
        if sys.platform == "darwin":
            ok, word_error = _convert_with_word(src, dst)
            if ok:
                return True, None
        else:
            word_error = f"Word conversion is macOS-only (running on {sys.platform})."
        soffice = soffice_path()
        if soffice:
            ok, soffice_error = _convert_with_soffice(soffice, src, dst)
            if ok:
                return True, None
            return False, f"{word_error} LibreOffice: {soffice_error}"
        logger.warning("%s Skipping %s", word_error, src)
        return False, word_error
    finally:
        _CONVERSION_LOCK.release()


def _convert_with_soffice(soffice: str, src: Path, dst: Path) -> tuple[bool, str | None]:
    """``soffice --headless --convert-to pdf`` into a private temp dir."""
    out_dir = Path(tempfile.mkdtemp(prefix="bsh-soffice-"))
    try:
        try:
            proc = subprocess.run(
                [soffice, "--headless", "--convert-to", "pdf", "--outdir", str(out_dir), str(src)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=CONVERSION_TIMEOUT,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return False, f"LibreOffice conversion timed out after {CONVERSION_TIMEOUT:.0f}s."
        except OSError as exc:
            return False, f"LibreOffice could not start: {exc}"
        produced = out_dir / f"{src.stem}.pdf"
        if proc.returncode or not produced.exists():
            detail = (proc.stderr or proc.stdout or b"").decode("utf-8", "ignore").strip()
            return False, (detail or f"exit {proc.returncode}")[:300]
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(produced), str(dst))
        return True, None
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)


def _convert_with_word(src: Path, dst: Path) -> tuple[bool, str | None]:
    """The Word/osascript conversion (macOS). The caller holds the lock."""
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
            _run_osascript([
                "osascript",
                str(script_file),
                str(staged_in),
                str(staged_out),
            ])
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
