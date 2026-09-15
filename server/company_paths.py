"""One rule for turning a company id into an on-disk directory name.

Plain ids (``[a-z0-9_-]`` only, up to 100 characters) map to themselves, so the
directories that already exist stay where they are. Anything else — dots,
accented or CJK letters, over-long ids — gets a best-effort ASCII slug plus a
short stable hash of the lowercased id (ids are case-insensitive, as the
stripping rule always was), so two different ids never share a directory and an id made only of non-ASCII letters still gets a name. The
result never contains ``/``, ``.`` at the start, or anything outside
``[a-z0-9_.-]``, so path traversal is impossible.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import unicodedata
from pathlib import Path

from . import storage

logger = logging.getLogger(__name__)

_PLAIN = re.compile(r"[a-z0-9_-]+")
MAX_PLAIN_LENGTH = 100
SLUG_LENGTH = 60


def storage_key(company_id: object) -> str:
    raw = unicodedata.normalize("NFC", str(company_id or "")).strip()
    if not raw or not any(ch.isalnum() for ch in raw):
        raise ValueError("Invalid company id")
    lowered = raw.lower()
    if len(lowered) <= MAX_PLAIN_LENGTH and _PLAIN.fullmatch(lowered):
        return lowered
    ascii_form = unicodedata.normalize("NFKD", lowered).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9_-]", "", ascii_form).strip("-_")[:SLUG_LENGTH]
    digest = hashlib.sha1(lowered.encode("utf-8")).hexdigest()[:8]
    return f"{slug or 'id'}.{digest}"


def company_dir(company_id: object) -> Path:
    return storage.DATA_DIR / "companies" / storage_key(company_id)


__all__ = ["storage_key", "company_dir", "legacy_key", "migrate_legacy_dirs", "MAX_PLAIN_LENGTH"]


# ---- Legacy layout -------------------------------------------------------------
#
# Before ``storage_key`` every per-company store stripped the id down to
# ``[a-z0-9_-]`` (``brk.b`` -> ``brkb``, ``ceinet-data-co-ltd-中经网`` ->
# ``ceinet-data-co-ltd-``). Data written under those names is moved under
# the storage key once, at startup, when the mapping is unambiguous.

_LEGACY_STRIP = re.compile(r"[^a-z0-9_-]")


def legacy_key(company_id: object) -> str:
    """The directory name the pre-``storage_key`` stores used for ``company_id``."""
    return _LEGACY_STRIP.sub("", str(company_id or "").lower())


def _legacy_roots() -> list[tuple[Path, str]]:
    """(root, filename suffix) for every store that keys files by storage key."""
    from . import files_store, memo_editor_store, research_store, serena_analysis

    return [
        (storage.DATA_DIR / "companies", ""),
        (files_store.UPLOADS_ROOT, ""),
        (research_store.RESEARCH_ROOT, ""),
        (memo_editor_store.EDITOR_ROOT, ""),
        (serena_analysis.ANALYSIS_ROOT, ""),
        (storage.DATA_DIR / "comments", ".json"),
    ]


def migrate_legacy_dirs(companies: list[dict] | None = None) -> list[tuple[Path, Path]]:
    """Rename legacy stripped directories/files to their storage keys.

    Only ids whose storage key differs from the stripped name are affected,
    and a legacy name is moved only when exactly one company maps to it and
    no company owns that name outright. Ambiguous names are logged and left
    alone. Returns the (old, new) pairs that were moved.
    """
    rows = storage.list_companies() if companies is None else companies
    keys: dict[str, str] = {}
    for row in rows:
        cid = str((row or {}).get("id") or "")
        try:
            keys[cid] = storage_key(cid)
        except ValueError:
            continue
    owned = set(keys.values())
    by_legacy: dict[str, list[str]] = {}
    for cid, key in keys.items():
        old = legacy_key(cid)
        if old and old != key:
            by_legacy.setdefault(old, []).append(cid)
    moved: list[tuple[Path, Path]] = []
    for old, ids in sorted(by_legacy.items()):
        if old in owned or len(ids) != 1:
            if any((root / f"{old}{suffix}").exists() for root, suffix in _legacy_roots()):
                logger.warning(
                    "Legacy company data %r is claimed by %s; left in place for manual assignment",
                    old, ", ".join(sorted(ids + [c for c, k in keys.items() if k == old]))
                )
            continue
        key = keys[ids[0]]
        for root, suffix in _legacy_roots():
            src = root / f"{old}{suffix}"
            dst = root / f"{key}{suffix}"
            if src.exists() and not dst.exists():
                os.replace(src, dst)
                moved.append((src, dst))
    return moved
