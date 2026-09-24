"""What a report says, in the few fields a reader scans before opening it.

``compute_reader_block(report)`` derives, from files already on disk:

- ``headline {en, zh}`` — the first sentence of the memo's decision: the
  ``investment_decision`` section of a late-stage package, or Section I of
  a Buffett-method memo (after its bold "Buy." lead);
- ``decision`` — the Buffett call (Buy / Pass / Too Hard) or, for runs on
  the flag-gated v2 structure, the spine's verdict;
- ``buy_price_text`` / ``pass_kind`` — the Buffett price condition;
- ``memo_as_of``, ``evidence_latest`` (the newest dated source, not an
  "evidence through" claim), ``sources_dated`` / ``sources_total``;
- ``source`` — where the block came from: ``package``, ``buffett`` or
  ``spine``.

The block is computed once — at completion (the pipeline calls
``persist_reader_block``) or lazily the first time a list GET meets an old
record (``ensure_reader_block``) — and stored on the record, so the Reports
list never parses a 170 KB package per request.

Also here, for the same reader-facing summary: the compact fact-check
summary, the plain-language failure explanation (``classify_failure``) and
the company-identity snapshot a report keeps of the company it was run on.
"""
from __future__ import annotations

import json
import logging
import re
import threading
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from . import memo_prep, storage

logger = logging.getLogger(__name__)

READER_VERSION = 1
COMPLETE_STATUSES = ("complete", "complete_with_warnings")
# Records whose documents a reader can open: the finished ones, and a run
# paused after English acceptance (I11, 2026-09-23) — its English memo,
# fact check and quality metrics exist and are read the same way.
READABLE_STATUSES = COMPLETE_STATUSES + ("english_ready_paused",)

# Optional structured Buffett price fields (R17). Present on newer records
# and packages only; every one of them is optional.
PRICE_FIELDS = (
    "price",
    "price_date",
    "currency",
    "value_low",
    "value_central",
    "value_high",
    "buy_price_value",
    "mos_pct",
)

_JSON_CACHE: dict[str, tuple[tuple[int, int], Any]] = {}
_JSON_CACHE_LOCK = threading.Lock()
_JSON_CACHE_MAX = 64


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def run_dir_for(report: dict) -> Path | None:
    rel = report.get("run_dir")
    if not rel:
        return None
    return memo_prep.DATA_DIR.parent / str(rel)


def _load_json(path: Path | None, *, cache: bool = False) -> Any:
    if path is None:
        return None
    try:
        stat = path.stat()
    except OSError:
        return None
    key = str(path)
    stamp = (stat.st_mtime_ns, stat.st_size)
    if cache:
        with _JSON_CACHE_LOCK:
            hit = _JSON_CACHE.get(key)
            if hit is not None and hit[0] == stamp:
                return hit[1]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if cache:
        with _JSON_CACHE_LOCK:
            if len(_JSON_CACHE) >= _JSON_CACHE_MAX:
                _JSON_CACHE.clear()
            _JSON_CACHE[key] = (stamp, payload)
    return payload


def load_package(report: dict) -> dict | None:
    """The run's bilingual package; for an English-only delivery (the
    Chinese stage failed) the accepted English package, whose Chinese
    halves are blank."""
    run_dir = run_dir_for(report)
    if run_dir is None:
        return None
    for name in ("memo_package.json", "memo_package.en.json"):
        payload = _load_json(run_dir / "logs" / name)
        if isinstance(payload, dict):
            return payload
    return None


def load_spine_facts(report: dict) -> dict | None:
    """``shared_facts`` from ``logs/english_units/spine.json`` (parallel and
    v2 runs), or None."""
    run_dir = run_dir_for(report)
    if run_dir is None:
        return None
    payload = _load_json(run_dir / "logs" / "english_units" / "spine.json")
    if not isinstance(payload, dict):
        return None
    facts = payload.get("shared_facts")
    return facts if isinstance(facts, dict) else None


# ---- text helpers ------------------------------------------------------------------

_CITATION_RE = re.compile(r"\s*\[(?:[SC]\d+)(?:\s*[,;]\s*[SC]\d+)*\]")
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\((?:[^)]+)\)")
# A short bold lead that is a label, not part of the sentence: it ends in
# punctuation inside ("**Buy.**", "**买入。**") or right after the bold
# ("**Decision**:"). "**BSH is not committing** at …" is left alone.
_BOLD_LEAD_RE = re.compile(
    r"^\s*(?:(?:\*\*|__)[^*_\n]{1,40}?[.。:：!！](?:\*\*|__)"
    r"|(?:\*\*|__)[^*_\n]{1,40}?(?:\*\*|__)\s*[.。:：])\s*"
)
_ABBREVIATIONS = {
    "u.s", "u.k", "u.s.a", "e.g", "i.e", "inc", "corp", "co", "ltd", "llc",
    "plc", "vs", "approx", "no", "nos", "st", "mr", "mrs", "ms", "dr", "jr",
    "sr", "etc", "est", "fig", "jan", "feb", "mar", "apr", "jun", "jul",
    "aug", "sep", "sept", "oct", "nov", "dec", "p.a", "a.m", "p.m", "ph.d",
    "bn", "mn", "tn", "hr", "hrs", "min", "mins",
}
_CLOSERS = "\"'”’)]"


def _plain(text: Any) -> str:
    value = str(text or "")
    value = _MD_LINK_RE.sub(r"\1", value)
    value = _CITATION_RE.sub("", value)
    value = value.replace("`", "")
    value = re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+", "", value)
    value = re.sub(r"^\s*#+\s*", "", value)
    return re.sub(r"\s+", " ", value).strip()


def _strip_lead(text: str) -> str:
    """Drop a short bold lead such as "**Buy.**", "**Decision.**" or
    "**买入。**" so the headline starts at the sentence itself."""
    stripped = _BOLD_LEAD_RE.sub("", str(text or ""), count=1)
    return stripped if stripped.strip() else str(text or "")


def _unbold(text: str) -> str:
    return re.sub(r"(\*\*|__)", "", text)


def _cap(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(",;:—–- ")
    return cut + "…"


def _sentence_ends_en(value: str):
    """Offsets just past each English sentence end, careful with "U.S.",
    "Inc.", initials and decimals."""
    for match in re.finditer(r"[.!?]", value):
        end = match.end()
        while end < len(value) and value[end] in _CLOSERS:
            end += 1
        if end < len(value) and not value[end].isspace():
            continue  # "1.5", "e.g.x", "$1.2T"
        if match.group() == ".":
            # The whole word before the period: "U.S", "Inc", an initial
            # "J" — but not "$1.2T", where the letter is a unit.
            token = re.search(r"(?:^|[\s(\"'“‘])([A-Za-z][A-Za-z.]*)$", value[: match.start()])
            if token:
                word = token.group(1).lower().rstrip(".")
                if word in _ABBREVIATIONS or len(word) == 1:
                    continue
        rest = value[end:].lstrip()
        if rest and not re.match(r"[A-Z0-9\"'“‘(\[$€£¥*]", rest):
            continue
        yield end


def sentences_en(text: Any) -> list[str]:
    value = _plain(_unbold(_strip_lead(str(text or ""))))
    out: list[str] = []
    start = 0
    for end in _sentence_ends_en(value):
        sentence = value[start:end].strip()
        if sentence:
            out.append(sentence)
        start = end
    tail = value[start:].strip()
    if tail:
        out.append(tail)
    return out


def sentences_zh(text: Any) -> list[str]:
    value = _plain(_unbold(_strip_lead(str(text or ""))))
    out: list[str] = []
    start = 0
    for match in re.finditer(r"[。！？]|[.!?](?=\s|$)", value):
        end = match.end()
        while end < len(value) and value[end] in "”’」』）)":
            end += 1
        sentence = value[start:end].strip()
        if sentence:
            out.append(sentence)
        start = end
    tail = value[start:].strip()
    if tail:
        out.append(tail)
    return out


def first_sentence_en(text: Any, *, limit: int = 400) -> str:
    """The first sentence of English prose."""
    found = sentences_en(text)
    return _cap(found[0], limit) if found else ""


def first_sentence_zh(text: Any, *, limit: int = 200) -> str:
    """The first sentence of Chinese prose, split on 。！？ (and a period
    followed by a space, for mixed-script text)."""
    found = sentences_zh(text)
    if not found:
        return ""
    value = found[0]
    return value if len(value) <= limit else value[:limit].rstrip() + "…"


# A sentence that only restates the call ("Pass.", "The call is Pass.",
# "结论是放弃（Pass）。") says nothing the decision chip does not.
_CALL_WORDS = (
    "strong buy", "too hard", "buy", "pass", "watch", "hold",
    "暂不买入", "超出能力圈", "强烈推荐", "推荐投资", "观察名单", "不建议投资",
    "买入", "放弃", "太难", "观察",
)
_CALL_FILLERS = (
    "the call is", "my call is", "our call is", "the decision is", "my decision is",
    "our decision is", "decision", "verdict", "call",
    "我们的结论是", "我的结论是", "结论是", "决策", "结论",
)


def restates_the_call(sentence: str) -> bool:
    text = _unbold(sentence).lower()
    text = re.sub(r"[\s.,:;!?。，：；！？()（）\[\]“”\"'—–\-]+", " ", text).strip()
    if not text or len(text) > 40:
        return False
    for filler in _CALL_FILLERS:
        text = text.replace(filler, " ")
    for word in _CALL_WORDS:
        text = text.replace(word, " ")
    return not text.strip()


def headline_sentence(paragraphs: list[Any], locale: str) -> str:
    """The first sentence across ``paragraphs`` that says more than the call."""
    split = sentences_zh if locale == "zh" else sentences_en
    limit = 200 if locale == "zh" else 400
    for paragraph in paragraphs:
        for sentence in split(paragraph):
            if restates_the_call(sentence):
                continue
            if len(sentence) <= limit:
                return sentence
            return (sentence[:limit].rstrip() + "…") if locale == "zh" else _cap(sentence, limit)
    return ""


def _loc(value: Any, locale: str) -> str:
    if isinstance(value, dict):
        text = value.get(locale)
        return text if isinstance(text, str) else ""
    if locale == "en" and isinstance(value, str):
        return value
    return ""


# ---- late-stage package --------------------------------------------------------------


def _section(package: dict, section_id: str) -> dict | None:
    for section in package.get("sections") or []:
        if isinstance(section, dict) and section.get("id") == section_id:
            return section
    return None


def _late_stage_headline(package: dict) -> dict | None:
    section = _section(package, "investment_decision")
    if section is None:
        return None
    blocks = [b for b in section.get("blocks") or [] if isinstance(b, dict)]
    candidates: list[Any] = [b.get("text") for b in blocks if b.get("type") == "paragraph"]
    for block in blocks:
        if block.get("type") == "bullets":
            candidates.extend(block.get("items") or [])
    headline = {
        "en": headline_sentence([_loc(c, "en") for c in candidates], "en"),
        "zh": headline_sentence([_loc(c, "zh") for c in candidates], "zh"),
    }
    if not headline["en"] and not headline["zh"]:
        return None
    return {"en": headline["en"] or None, "zh": headline["zh"] or None}


_DATE_RE = re.compile(r"(\d{4})(?:-(\d{1,2}))?(?:-(\d{1,2}))?")


def _period_end(raw: Any) -> tuple[date, str] | None:
    """The latest calendar day a source date string covers, plus the date
    at its own precision ("2026-08" stays "2026-08")."""
    text = str(raw or "").strip()
    best: tuple[date, str] | None = None
    for match in _DATE_RE.finditer(text):
        year = int(match.group(1))
        if year < 1900 or year > 2200:
            continue
        month = int(match.group(2)) if match.group(2) else None
        day = int(match.group(3)) if match.group(3) else None
        try:
            if month and day:
                end = date(year, month, day)
                label = f"{year:04d}-{month:02d}-{day:02d}"
            elif month:
                if not 1 <= month <= 12:
                    continue
                next_month = date(year + (month == 12), month % 12 + 1, 1)
                end = date.fromordinal(next_month.toordinal() - 1)
                label = f"{year:04d}-{month:02d}"
            else:
                end = date(year, 12, 31)
                label = f"{year:04d}"
        except ValueError:
            continue
        if best is None or end > best[0]:
            best = (end, label)
    return best


def _parse_day(raw: Any) -> date | None:
    match = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(raw or ""))
    if not match:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def _source_dates(sources: Any, memo_as_of: str | None) -> tuple[str | None, int, int]:
    """(newest source date, dated count, total). Dates after the memo's own
    date are forward-looking or misdated and are not counted as evidence."""
    if not isinstance(sources, list):
        return None, 0, 0
    ceiling = _parse_day(memo_as_of)
    latest: tuple[date, str] | None = None
    dated = 0
    total = 0
    for source in sources:
        if not isinstance(source, dict):
            continue
        total += 1
        parsed = _period_end(source.get("as_of") or source.get("date") or source.get("published"))
        if parsed is None:
            continue
        end, label = parsed
        if ceiling is not None and end > ceiling:
            # A period that runs past the memo date ("2026" in a September
            # memo) still counts as dated, but only up to the memo date.
            if label.count("-") == 2:
                continue
            end = ceiling
        dated += 1
        if latest is None or end > latest[0]:
            latest = (end, label)
    return (latest[1] if latest else None), dated, total


# ---- Buffett markdown ----------------------------------------------------------------

_DECISION_HEADING_RE = re.compile(r"decision|投资决策|决策|结论|recommendation", re.I)


def _section_one_paragraphs(markdown: str) -> list[str]:
    lines = str(markdown or "").splitlines()
    headings = [i for i, line in enumerate(lines) if re.match(r"^##\s+\S", line)]
    if not headings:
        return []
    start = next(
        (i for i in headings if _DECISION_HEADING_RE.search(lines[i])),
        headings[0],
    )
    body: list[str] = []
    for line in lines[start + 1:]:
        if re.match(r"^#{1,2}\s+\S", line):
            break
        body.append(line)
    paragraphs: list[str] = []
    current: list[str] = []
    for line in body + [""]:
        stripped = line.strip()
        if not stripped or stripped.startswith(("|", "#", ">")):
            if current:
                paragraphs.append(" ".join(current))
                current = []
            continue
        current.append(stripped)
    return paragraphs


def _buffett_headline(markdown_en: str, markdown_zh: str) -> dict | None:
    headline = {
        "en": headline_sentence(_section_one_paragraphs(markdown_en), "en") or None,
        "zh": headline_sentence(_section_one_paragraphs(markdown_zh), "zh") or None,
    }
    return headline if headline["en"] or headline["zh"] else None


# ---- the block -----------------------------------------------------------------------


def _memo_as_of(report: dict, package: dict | None) -> str | None:
    run = package.get("run") if isinstance(package, dict) and isinstance(package.get("run"), dict) else {}
    for candidate in (run.get("as_of"), run.get("run_date"), report.get("created_at")):
        day = _parse_day(candidate)
        if day is not None:
            return day.isoformat()
    return None


def price_fields(report: dict, package: dict | None = None) -> dict:
    """The optional structured Buffett price fields. Read, in order, from the
    record's own keys, its ``buffett_valuation`` object (what the Buffett
    finalize step stores), then the package's top-level keys, its optional
    ``valuation`` object and a ``price`` object (``price_at_writing`` /
    ``price_as_of``). Scalars only."""
    pkg = package if isinstance(package, dict) else {}
    stored = report.get("buffett_valuation") if isinstance(report.get("buffett_valuation"), dict) else {}
    nested = pkg.get("valuation") if isinstance(pkg.get("valuation"), dict) else {}
    price_obj = pkg.get("price") if isinstance(pkg.get("price"), dict) else {}
    aliases = {"price": ("price_at_writing",), "price_date": ("price_as_of",)}
    out: dict[str, Any] = {}
    for key in PRICE_FIELDS:
        value = report.get(key)
        if value is None:
            value = stored.get(key)
        if value is None and not (key == "price" and price_obj):
            value = pkg.get(key)
        if value is None:
            value = nested.get(key)
        if value is None:
            for name in (key, *aliases.get(key, ())):
                if price_obj.get(name) is not None:
                    value = price_obj.get(name)
                    break
        if value is not None and not isinstance(value, (dict, list)):
            out[key] = value
    return out


def compute_reader_block(report: dict) -> dict:
    """Derive the reader block for one report record. Never raises; fields
    it cannot find are None."""
    block: dict[str, Any] = {
        "v": READER_VERSION,
        "headline": None,
        "decision": None,
        "buy_price_text": None,
        "buy_price_text_zh": None,
        "pass_kind": None,
        "memo_as_of": None,
        "evidence_latest": None,
        "sources_dated": 0,
        "sources_total": 0,
        "source": None,
        "computed_at": _now(),
    }
    try:
        kind = report.get("kind")
        package = load_package(report)
        block["memo_as_of"] = _memo_as_of(report, package)
        if memo_prep.is_buffett_kind(kind):
            pkg = package or {}
            markdown_en = pkg.get("markdown_en") or report.get("content_en") or report.get("content") or ""
            markdown_zh = pkg.get("markdown_zh") or report.get("content_zh") or ""
            block["headline"] = _buffett_headline(markdown_en, markdown_zh)
            block["decision"] = report.get("decision") or pkg.get("decision")
            buy_price = report.get("buy_price") or pkg.get("buy_price")
            if isinstance(buy_price, dict):
                block["buy_price_text"] = buy_price.get("en") or None
                block["buy_price_text_zh"] = buy_price.get("zh") or None
            elif buy_price:
                block["buy_price_text"] = str(buy_price)
            price = pkg.get("price") if isinstance(pkg.get("price"), dict) else {}
            zh_text = report.get("buy_price_zh") or pkg.get("buy_price_zh") or price.get("text_zh")
            if not block["buy_price_text_zh"] and zh_text:
                block["buy_price_text_zh"] = str(zh_text)
            label = report.get("call_label")
            if isinstance(label, dict) and (label.get("en") or label.get("zh")):
                block["call_label"] = {"en": label.get("en"), "zh": label.get("zh")}
            block["pass_kind"] = report.get("pass_kind") or pkg.get("pass_kind")
            latest, dated, total = _source_dates(pkg.get("sources"), block["memo_as_of"])
            block.update(evidence_latest=latest, sources_dated=dated, sources_total=total)
            structured = price_fields(report, package)
            if structured:
                block["price_fields"] = structured
            block["source"] = "buffett" if (package or markdown_en) else None
        elif memo_prep.is_memo_kind(kind):
            if package is not None:
                block["headline"] = _late_stage_headline(package)
                latest, dated, total = _source_dates(package.get("sources"), block["memo_as_of"])
                block.update(evidence_latest=latest, sources_dated=dated, sources_total=total)
                decision = package.get("decision")
                if isinstance(decision, dict) and decision.get("label"):
                    block["decision"] = str(decision.get("label"))
                block["source"] = "package"
            facts = load_spine_facts(report)
            if facts and facts.get("verdict"):
                block["decision"] = str(facts.get("verdict"))
                block["source"] = "spine"
                if block["headline"] is None and facts.get("recommendation_sentence"):
                    block["headline"] = {
                        "en": first_sentence_en(facts.get("recommendation_sentence")),
                        "zh": None,
                    }
    except Exception:  # noqa: BLE001 — a reader block must never break a list
        logger.warning("reader block failed for %s", report.get("id"), exc_info=True)
    return block


def _eligible(report: dict) -> bool:
    return memo_prep.is_memo_kind(report.get("kind")) and str(
        report.get("status") or ""
    ) in READABLE_STATUSES


def documents_stamp(report: dict) -> str | None:
    """Which rendering of the documents a block was computed for: the memo
    files' modification times. A resume, regeneration or re-render rewrites
    them, so a stored block from before is recomputed once."""
    parts: list[str] = []
    for entry in report.get("memo_files") or []:
        if not isinstance(entry, dict) or not entry.get("path"):
            continue
        try:
            mtime = (memo_prep.DATA_DIR.parent / str(entry["path"])).stat().st_mtime_ns
        except OSError:
            continue
        parts.append(f"{entry.get('language')}:{mtime}")
    return ",".join(sorted(parts)) or None


def _fresh(block: Any, report: dict) -> bool:
    return (
        isinstance(block, dict)
        and block.get("v") == READER_VERSION
        and block.get("docs_stamp") == documents_stamp(report)
    )


def _compute_and_store(report_id: str) -> dict | None:
    """Recompute from a fresh read of the record (never from a caller's
    possibly stale copy) and store it; None when not a finished memo."""
    record = storage.get_report(report_id)
    if record is None or not _eligible(record):
        return None
    block = compute_reader_block(record)
    block["docs_stamp"] = documents_stamp(record)
    try:
        storage.update_report(report_id, reader=block)
    except Exception:  # noqa: BLE001
        logger.warning("could not persist reader block for %s", report_id, exc_info=True)
    return block


def persist_reader_block(report_id: str) -> dict | None:
    """Compute and store the reader block for a finished memo. The pipelines
    call this once a run completes (late-stage and Buffett) and after any
    re-render. Returns the block, or None when the report is missing or not
    a finished memo."""
    return _compute_and_store(report_id)


def ensure_reader_block(report: dict) -> dict | None:
    """The stored block when it matches the current documents; otherwise
    computed and persisted once for a finished memo (lazy backfill). None
    for anything else."""
    existing = report.get("reader")
    if _fresh(existing, report):
        return existing
    if not _eligible(report) or not report.get("id"):
        return existing if isinstance(existing, dict) else None
    block = _compute_and_store(str(report["id"]))
    if block is None:
        return existing if isinstance(existing, dict) else None
    report["reader"] = block
    return block


def report_decision(report: dict) -> str | None:
    """The call a report makes: the stored Buffett decision, else the reader
    block's (v2 spine) decision."""
    decision = report.get("decision")
    if decision:
        return str(decision)
    reader = report.get("reader")
    if isinstance(reader, dict) and reader.get("decision"):
        return str(reader.get("decision"))
    return None


# ---- fact check ------------------------------------------------------------------------

_FACT_CHECK_SUMMARY_KEYS = (
    "status",
    "checked",
    "verified",
    "found_elsewhere",
    "supported",
    "derived",
    "company_reported",
    "registry_only",
    "not_traced",
    "unsupported",
    "coverage_pct",
    "thin_corpus",
    "p0_count",
)


def fact_check_full(report: dict) -> dict | None:
    """The full fact-check payload: the record's, else ``logs/fact_check.json``.
    None for runs that predate the check."""
    stored = report.get("memo_fact_check")
    if isinstance(stored, dict) and ("findings" in stored or "corpus" in stored):
        return stored
    run_dir = run_dir_for(report)
    payload = (
        _load_json(run_dir / "logs" / "fact_check.json", cache=True)
        if run_dir is not None
        else None
    )
    if isinstance(payload, dict):
        return payload
    return stored if isinstance(stored, dict) else None


def fact_check_summary(report: dict) -> dict | None:
    """The compact fact-check summary for list rows (None when the run never
    had a fact check — the UI then says "checks not run")."""
    full = fact_check_full(report)
    if not isinstance(full, dict):
        return None
    try:
        from . import memo_fact_check

        summarize = getattr(memo_fact_check, "summarize_fact_check", None)
        if callable(summarize):
            summary = summarize(full)
            if isinstance(summary, dict):
                return summary
    except Exception:  # noqa: BLE001
        logger.debug("summarize_fact_check failed", exc_info=True)
    return {key: full.get(key) for key in _FACT_CHECK_SUMMARY_KEYS if key in full}


def quality_metrics(report: dict) -> dict | None:
    """The run's quality metrics (``memo_quality_metrics.compute``): the
    record's ``quality_metrics``, else ``logs/quality_metrics.json``. None
    for runs that predate the metrics. Same shape on the list row and the
    detail, whatever the record's status (a run paused after English —
    ``english_ready_paused`` — has them too)."""
    stored = report.get("quality_metrics")
    if isinstance(stored, dict) and stored:
        return stored
    run_dir = run_dir_for(report)
    payload = (
        _load_json(run_dir / "logs" / "quality_metrics.json", cache=True)
        if run_dir is not None
        else None
    )
    return payload if isinstance(payload, dict) else None


# ---- failure explanation ------------------------------------------------------------------

FAILURE_KINDS = (
    "interrupted",
    "cancelled",
    "provider_limit",
    "login",
    "timeout",
    "engine_output_malformed",
    "internal_error",
    "out_of_scope",
)

_TIMEOUT_MARKERS = ("timed out", "timeout", "stalled after", "without output", "deadline exceeded")
_MALFORMED_MARKERS = (
    "invalid memo package",
    "memo package",
    "renderer contract",
    "unusable skeleton",
    "unusable",
    "malformed",
    "json",
    "schema",
    "could not parse",
    "structured output",
    "returned no data",
    "outputs are missing",
)

_SUMMARIES: dict[str, tuple[str, str]] = {
    "interrupted": (
        "The run stopped when the server restarted, before the memo was finished.",
        "服务器重启时运行被中断，备忘录尚未完成。",
    ),
    "cancelled": (
        "The run was cancelled before the memo was finished.",
        "运行在备忘录完成前被取消。",
    ),
    "provider_limit": (
        "Claude reached its usage limit, so the run stopped.",
        "Claude 已达到使用上限，运行因此停止。",
    ),
    "login": (
        "The Claude command-line tool is not signed in, so the analysis could not run.",
        "Claude 命令行工具未登录，分析无法进行。",
    ),
    "timeout": (
        "A step took too long and was stopped.",
        "某个步骤耗时过长，已被终止。",
    ),
    "engine_output_malformed": (
        "The model's output could not be turned into a finished document.",
        "模型返回的内容无法生成完整的文档。",
    ),
    "quality_gate": (
        "The memo was written but did not pass the quality checks.",
        "备忘录已写成，但未通过质量检查。",
    ),
    "internal_error": (
        "The run stopped on an internal error.",
        "运行因内部错误而中止。",
    ),
    "out_of_scope": (
        "This company is outside the scope of this memo type, so no memo was written.",
        "该公司不在此类备忘录的适用范围内，因此未撰写备忘录。",
    ),
}


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and number >= 0 else None


def _spend_so_far(report: dict, stream_state: dict | None) -> float | None:
    """The API-equivalent spend recorded before the failure: the largest of
    the phase timings' cost, the stream's last result cost and the record's
    own cost (each is a lower bound of what was actually spent)."""
    candidates: list[float] = []
    state = stream_state or {}
    for timing in state.get("phase_timings") or []:
        if isinstance(timing, dict):
            value = _as_float(timing.get("cost_usd"))
            if value is not None:
                candidates.append(value)
    for value in (state.get("claude_cost_usd"), report.get("claude_cost_usd")):
        number = _as_float(value)
        if number is not None:
            candidates.append(number)
    positive = [value for value in candidates if value > 0]
    return round(max(positive), 4) if positive else None


def _reset_time(text: str, report: dict) -> str | None:
    try:
        from . import provider_limits

        live = provider_limits.current_limit("claude")
        if live and live.get("reset_at"):
            return str(live["reset_at"])
        anchor = None
        for candidate in (report.get("updated_at"), report.get("created_at")):
            try:
                anchor = datetime.fromisoformat(str(candidate).replace("Z", "+00:00"))
                if anchor.tzinfo is None:
                    anchor = anchor.replace(tzinfo=timezone.utc)
                break
            except (TypeError, ValueError):
                continue
        parsed = provider_limits.parse_reset_text(text, now=anchor)
        if parsed is not None:
            return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    except Exception:  # noqa: BLE001
        return None
    return None


def classify_failure(report: dict, stream_state: dict | None = None) -> dict | None:
    """Explain a failed run in plain words, from the failure_phase values the
    pipeline already writes and the CLI failure text.

    Returns ``{failure_kind, failure_summary_en, failure_summary_zh,
    failure_resets_at, failure_spend_usd}`` for failed runs, else None.
    ``failure_kind`` is one of ``FAILURE_KINDS``.
    """
    status = str(report.get("status") or "")
    if not status.startswith("failed"):
        return None
    phase = str(report.get("failure_phase") or "").strip().lower()
    state = stream_state or {}
    text = " | ".join(
        str(part)
        for part in (
            report.get("failure_detail"),
            report.get("error"),
            report.get("analysis_error"),
            state.get("error"),
        )
        if part
    )
    lowered = text.lower()
    summary_key: str | None = None
    try:
        from . import claude_runner

        auth = claude_runner.auth_failure_reason(text)
        limit = claude_runner.provider_limit_reason(text)
    except Exception:  # noqa: BLE001
        auth = limit = None
    if status == "failed_scope_check":
        kind = "out_of_scope"
    elif phase == "cancelled":
        kind = "cancelled"
    elif phase in {"shutdown", "orphaned", "interrupted"}:
        kind = "interrupted"
    elif auth:
        kind = "login"
    elif limit:
        kind = "provider_limit"
    elif any(marker in lowered for marker in _TIMEOUT_MARKERS):
        kind = "timeout"
    elif status == "failed_quality_gate":
        kind = "engine_output_malformed"
        summary_key = "quality_gate"
    elif phase in {"renderer_contract", "post_run_check"} or any(
        marker in lowered for marker in _MALFORMED_MARKERS
    ):
        kind = "engine_output_malformed"
    else:
        kind = "internal_error"
    summary_en, summary_zh = _SUMMARIES[summary_key or kind]
    resets_at = _reset_time(text, report) if kind == "provider_limit" else None
    if resets_at:
        summary_en = summary_en.rstrip(".") + f"; it resets at {resets_at}."
        summary_zh = summary_zh.rstrip("。") + f"，将于 {resets_at} 重置。"
    return {
        "failure_kind": kind,
        "failure_summary_en": summary_en,
        "failure_summary_zh": summary_zh,
        "failure_resets_at": resets_at,
        "failure_spend_usd": _spend_so_far(report, state),
    }


# ---- company identity snapshot -------------------------------------------------------------

IDENTITY_FIELDS = (
    "name",
    "legal_name",
    "disambiguator",
    "ticker",
    "exchange",
    "website",
    "logo_domain",
    "logo_url",
)


def identity_from_company(company: dict | None) -> dict | None:
    """The identity fields worth keeping with a report: who the run was about."""
    if not isinstance(company, dict):
        return None
    snapshot = {
        key: str(company.get(key)).strip()
        for key in IDENTITY_FIELDS
        if company.get(key) not in (None, "") and not isinstance(company.get(key), (dict, list))
    }
    if not snapshot:
        return None
    snapshot["captured_at"] = _now()
    return snapshot


def snapshot_company_identity(report_id: str, company: dict | None = None) -> dict | None:
    """Store the company's identity on a freshly created report so its logo
    and legal name survive later edits (or removal) of the company record.
    Does nothing when the record already carries a snapshot."""
    report = storage.get_report(report_id)
    if report is None or isinstance(report.get("company_identity"), dict):
        return None
    if company is None:
        company = storage.get_company(str(report.get("company_id") or "")) if report.get("company_id") else None
    snapshot = identity_from_company(company)
    if snapshot is None:
        return None
    try:
        storage.update_report(report_id, company_identity=snapshot)
    except Exception:  # noqa: BLE001
        logger.warning("identity snapshot failed for %s", report_id, exc_info=True)
        return None
    return snapshot
