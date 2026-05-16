"""Date-organized Hormuz source library + appendix output layout.

Two trees, both keyed by ``YYYY-MM-DD``:

  data/external/hormuz_research/sources/<date>/<filename>
      Raw daily source report(s). The date is extracted from the
      uploaded filename (convention e.g. ``中东局势每日研判2026-05-13.pdf``).

  data/hormuz_appendix/<date>/
      One idempotent run folder per target date holding the generated
      bilingual appendix: ``v3_appendix_cn_<date>.md/.pdf`` and
      ``v3_appendix_en_<date>.md/.pdf`` plus ``logs/stream.jsonl``.

Re-running a date overwrites that date's appendix in place — there is no
per-attempt versioning (the source reports are the durable history).
"""
from __future__ import annotations

import re
from pathlib import Path

from .files_store import _sanitize_filename

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
REPO_ROOT = DATA_DIR.parent
SOURCES_ROOT = DATA_DIR / "external" / "hormuz_research" / "sources"
APPENDIX_ROOT = DATA_DIR / "hormuz_appendix"

# Matches a YYYY-MM-DD date anywhere in a filename, with or without
# separators: 2026-05-13, 2026_05_13, 2026.05.13, 20260513. Year 2000-2099.
_DATE_RE = re.compile(r"(20\d{2})[-_.]?(0[1-9]|1[0-2])[-_.]?(0[1-9]|[12]\d|3[01])")


def _rel(path: Path | str) -> str:
    p = Path(path)
    try:
        return str(p.relative_to(REPO_ROOT))
    except ValueError:
        return str(p)


def extract_date_from_filename(name: str) -> str | None:
    """Pull a ``YYYY-MM-DD`` date out of a source filename, or None."""
    if not name:
        return None
    m = _DATE_RE.search(name)
    if not m:
        return None
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"


def is_valid_date(date: str) -> bool:
    return bool(re.fullmatch(r"20\d{2}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])", date or ""))


def source_dir(date: str) -> Path:
    return SOURCES_ROOT / date


def save_source(filename: str, data: bytes) -> dict:
    """Store one uploaded source file under sources/<date>/.

    The date is taken from the filename. Raises ValueError if no date can
    be parsed (so the caller can tell the user to fix the filename).
    Returns ``{date, filename, path, size_bytes, replaced}``.
    """
    safe = _sanitize_filename(filename)
    date = extract_date_from_filename(safe) or extract_date_from_filename(filename)
    if not date:
        raise ValueError(
            "Could not find a YYYY-MM-DD date in the filename. Expected "
            "something like 中东局势每日研判2026-05-13.pdf"
        )
    d = source_dir(date)
    d.mkdir(parents=True, exist_ok=True)
    dest = d / safe
    replaced = dest.exists()
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(dest)
    return {
        "date": date,
        "filename": safe,
        "path": _rel(dest),
        "size_bytes": len(data),
        "replaced": replaced,
    }


def source_files(date: str) -> list[Path]:
    d = source_dir(date)
    if not d.exists():
        return []
    return sorted(p for p in d.iterdir() if p.is_file() and not p.name.endswith(".tmp"))


def list_source_dates() -> list[str]:
    """All dates that have at least one source file, newest first."""
    if not SOURCES_ROOT.exists():
        return []
    dates = [
        p.name
        for p in SOURCES_ROOT.iterdir()
        if p.is_dir() and is_valid_date(p.name) and source_files(p.name)
    ]
    return sorted(dates, reverse=True)


def previous_date(date: str) -> str | None:
    """Most recent source date strictly before ``date`` (the baseline)."""
    earlier = [d for d in list_source_dates() if d < date]
    return max(earlier) if earlier else None


def resolve_source_file(date: str, filename: str) -> Path | None:
    safe = _sanitize_filename(filename)
    p = source_dir(date) / safe
    return p if p.is_file() else None


# --- Appendix output layout ------------------------------------------------

def appendix_dir(date: str) -> Path:
    return APPENDIX_ROOT / date


def output_basenames(date: str) -> tuple[str, str]:
    """(cn_basename, en_basename) e.g. v3_appendix_cn_2026_05_15."""
    tag = date.replace("-", "_")
    return f"v3_appendix_cn_{tag}", f"v3_appendix_en_{tag}"


def appendix_output_paths(date: str) -> dict[str, Path]:
    """Absolute paths for the four appendix output files."""
    d = appendix_dir(date)
    cn, en = output_basenames(date)
    return {
        "cn_md": d / f"{cn}.md",
        "cn_pdf": d / f"{cn}.pdf",
        "en_md": d / f"{en}.md",
        "en_pdf": d / f"{en}.pdf",
    }


def import_legacy_hormuz_files() -> dict:
    """Fold files attached to the legacy Hormuz Research items into the
    date-organized source library.

    Idempotent and non-destructive: the legacy items are left untouched;
    each attached file whose (original) filename carries a parseable
    YYYY-MM-DD date is copied into ``sources/<date>/`` if it isn't
    already there. A same-size file at the destination is treated as
    already-imported and skipped; a different-size collision is written
    under a disambiguated name so nothing is lost.

    Returns ``{imported: [...], skipped: int, undated: [...]}``.
    """
    from . import external_store  # local import avoids any import cycle

    files_dir = external_store._kind_dir("hormuz_research") / "files"
    summary: dict = {"imported": [], "skipped": 0, "undated": []}
    if not files_dir.exists():
        return summary

    for item in external_store.list_items("hormuz_research"):
        stored = item.get("stored_name")
        if not stored:
            continue
        src = files_dir / stored
        if not src.is_file():
            continue
        original = item.get("filename") or stored
        date = extract_date_from_filename(original) or extract_date_from_filename(stored)
        if not date:
            summary["undated"].append(original)
            continue
        d = source_dir(date)
        d.mkdir(parents=True, exist_ok=True)
        safe = _sanitize_filename(original)
        dest = d / safe
        try:
            src_size = src.stat().st_size
            if dest.exists():
                if dest.stat().st_size == src_size:
                    summary["skipped"] += 1
                    continue
                # Distinct file with the same name+date — disambiguate.
                dest = d / f"{dest.stem}__{item.get('id', 'x')[:8]}{dest.suffix}"
                if dest.exists():
                    summary["skipped"] += 1
                    continue
            tmp = dest.with_suffix(dest.suffix + ".tmp")
            tmp.write_bytes(src.read_bytes())
            tmp.replace(dest)
            summary["imported"].append({"date": date, "filename": dest.name})
        except OSError:
            continue
    return summary


def appendix_status(date: str) -> dict:
    """Which of the four output files currently exist on disk."""
    paths = appendix_output_paths(date)
    present = {k: v.exists() for k, v in paths.items()}
    return {
        "date": date,
        "files": {k: (_rel(v) if present[k] else None) for k, v in paths.items()},
        "complete": all(present.values()),
        "any": any(present.values()),
    }
