"""Display names for companies: one clean form for prompts, covers and files.

SEC EDGAR's company tickers file carries filer names such as
``OCCIDENTAL PETROLEUM CORP /DE/`` or ``WELLS FARGO & COMPANY/MN``: the
trailing ``/DE/`` token is the state (or a marker such as ``/NEW/`` or
``/ADR/``), not part of the name. Left in place it leaked into memo titles,
headers and Word filenames — the OXY memo was written into a nested
``Occidental Petroleum Corp /De/`` folder. :func:`clean_display_name`
strips those tokens and makes the result safe as one path component.
"""
from __future__ import annotations

import re
import unicodedata

# A trailing EDGAR suffix token: "/DE/", "/De/", "/MD/", "/NEW/", "/ADR/",
# "/MN" (no closing slash). Two to four letters between slashes; repeated
# tokens ("CORP /DE/ /NEW/") are all removed.
_EDGAR_SUFFIX_RE = re.compile(r"(?:\s*/\s*[A-Za-z]{2,4}\s*/?)+\s*$")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
_SEPARATOR_RE = re.compile(r"\s*[/\\]+\s*")
_SPACE_RE = re.compile(r"\s+")


def clean_display_name(name: object) -> str:
    """``name`` without EDGAR state/suffix tokens, path separators or
    control characters. Ordinary names come back unchanged (apart from
    collapsed whitespace); an empty or unusable name returns ``""``."""
    text = unicodedata.normalize("NFC", str(name or ""))
    text = _CONTROL_RE.sub(" ", text)
    text = _SPACE_RE.sub(" ", text).strip()
    if not text:
        return ""
    stripped = _EDGAR_SUFFIX_RE.sub("", text).strip()
    # Never strip a name down to nothing ("/DE/" alone is not a name).
    if stripped:
        text = stripped
    # Any slash left is inside the name ("AC/DC Holdings"): keep the words,
    # lose the path separator.
    text = _SEPARATOR_RE.sub("-", text)
    # A leading dot would make a hidden file; ".." would climb a directory.
    # Trailing punctuation left behind by a removed token ("Corp , /DE/")
    # goes too; a final "." is part of names like "Apple Inc." and stays.
    text = text.lstrip(". -").rstrip(" -,;:")
    return _SPACE_RE.sub(" ", text).strip()


__all__ = ["clean_display_name"]
