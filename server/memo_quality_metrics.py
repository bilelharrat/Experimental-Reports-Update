"""Quality metrics for one memo run — pure, deterministic, no model.

``compute(run_dir, package, report)`` reads what the run already wrote
(``logs/fact_check.json``, ``logs/glossary.json``) and the package itself,
and returns one flat dict the pipeline copies to the record as
``report["quality_metrics"]`` (``memo_analysis`` calls it once in finalize,
inside try/except) and the API exposes through ``report_reader``:

- ``traced_pct`` — the fact check's coverage (figures traced to a source
  on file), None when the check never ran;
- ``unsupported_headline_figures`` — unsupported figures in the executive
  summary, key-metrics table or recommendation (``memo_fact_check``'s
  ``headline`` flag, else the section-id rule);
- ``repetition_index`` — share of English sentences (8+ words) whose
  8-word run appears in another sentence of the memo;
- ``words_total`` / ``words_by_section`` — the renderer's word count;
- ``over_cap_sections`` — sections over their profile's hard word cap
  (``[{section, words, cap}]``), empty for profiles without budgets;
- ``metric_conflicts`` — count of ``memo_fact_check.metric_conflicts``;
- ``zh_term_drift`` — count of glossary terms rendered more than one way
  (``memo_chinese_parity.glossary_term_drift``; 0 without a glossary);
- ``untranslated_zh_lines`` — Chinese strings still in English
  (``memo_chinese_parity.untranslated_zh_lines``).

Written to ``<run>/logs/quality_metrics.json`` when ``run_dir`` is given.
Never raises: a metric that cannot be computed is None (or 0 for counts).
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from server import memo_chinese_parity, memo_docx_renderer, memo_fact_check, memo_structure

logger = logging.getLogger(__name__)

METRICS_VERSION = 1
METRICS_FILENAME = "quality_metrics.json"
_NGRAM = 8
_CITATION_RE = re.compile(r"\[(?:[SC]\d+)(?:\s*,\s*[SC]\d+)*\]")
_SENTENCE_END_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'(\[$])")
_WORD_RE = re.compile(r"[a-z0-9$%.']+")


def _en_strings(package: dict, *, skip_sources: bool = True):
    """Every English string in the package's sections (not the sources)."""

    def walk(value: Any):
        if isinstance(value, dict):
            if isinstance(value.get("en"), str):
                yield value["en"]
                return
            for key, item in value.items():
                if key in {"id", "type", "component", "level", "zh", "source_ids"}:
                    continue
                yield from walk(item)
        elif isinstance(value, list):
            for item in value:
                yield from walk(item)

    for section in package.get("sections") or []:
        if not isinstance(section, dict):
            continue
        if skip_sources and str(section.get("id") or "") == "sources":
            continue
        yield from walk(section.get("blocks"))


def sentences_en(text: str) -> list[str]:
    return [part.strip() for part in _SENTENCE_END_RE.split(text or "") if part.strip()]


def _words(sentence: str) -> list[str]:
    return _WORD_RE.findall(_CITATION_RE.sub(" ", sentence.lower()))


def repetition_index(package: dict) -> float | None:
    """Share of sentences (8+ words) whose 8-gram appears in some OTHER
    sentence of the memo. 0.0 for a memo that says everything once; None
    when the memo has no such sentences."""
    sentences: list[list[str]] = []
    for text in _en_strings(package):
        for sentence in sentences_en(text):
            words = _words(sentence)
            if len(words) >= _NGRAM:
                sentences.append(words)
    if not sentences:
        return None
    owners: dict[tuple[str, ...], set[int]] = {}
    for index, words in enumerate(sentences):
        for start in range(len(words) - _NGRAM + 1):
            owners.setdefault(tuple(words[start : start + _NGRAM]), set()).add(index)
    repeated = 0
    for index, words in enumerate(sentences):
        if any(
            len(owners[tuple(words[start : start + _NGRAM])]) > 1
            for start in range(len(words) - _NGRAM + 1)
        ):
            repeated += 1
    return round(repeated / len(sentences), 3)


def word_counts(package: dict) -> tuple[int, dict[str, int]]:
    by_section: dict[str, int] = {}
    for index, section in enumerate(package.get("sections") or []):
        if not isinstance(section, dict):
            continue
        section_id = str(section.get("id") or f"sections[{index}]")
        by_section[section_id] = memo_docx_renderer.section_en_word_count(section)
    return sum(by_section.values()), by_section


def over_cap_sections(package: dict, by_section: dict[str, int] | None = None) -> list[dict]:
    """Sections over their profile's hard cap, the way the renderer's
    word-budget gate measures it."""
    by_section = by_section if by_section is not None else word_counts(package)[1]
    try:
        structure = memo_structure.for_package(package)
    except Exception:  # noqa: BLE001
        return []
    out: list[dict] = []
    for sdef in structure.sections:
        budget = getattr(sdef, "budget_words", None)
        if not budget or sdef.id not in by_section:
            continue
        multiple = getattr(sdef, "budget_hard_multiple", None) or memo_docx_renderer._BUDGET_GRACE
        cap = int(budget * multiple)
        words = by_section[sdef.id]
        if words > cap:
            out.append({"section": sdef.id, "words": words, "cap": cap, "target": budget})
    return out


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _fact_check_payload(run_dir: Path | None, report: dict | None) -> dict | None:
    if isinstance(report, dict):
        stored = report.get("memo_fact_check")
        if isinstance(stored, dict) and ("findings" in stored or "coverage_pct" in stored):
            return stored
    if run_dir is not None:
        payload = _load_json(Path(run_dir) / "logs" / "fact_check.json")
        if isinstance(payload, dict):
            return payload
    if isinstance(report, dict) and isinstance(report.get("memo_fact_check"), dict):
        return report["memo_fact_check"]
    return None


def unsupported_headline_figures(fact_check: dict | None) -> int | None:
    if not isinstance(fact_check, dict):
        return None
    if isinstance(fact_check.get("unsupported_headline"), int):
        return int(fact_check["unsupported_headline"])
    findings = fact_check.get("findings")
    if not isinstance(findings, list):
        return None
    count = 0
    for finding in findings:
        if not isinstance(finding, dict) or finding.get("code") != "unsupported_figure":
            continue
        if finding.get("headline") is True or (
            "headline" not in finding
            and memo_fact_check.headline_section(str(finding.get("section_id") or ""))
        ):
            count += 1
    return count


def compute(
    run_dir: Path | str | None,
    package: dict | None,
    report: dict | None = None,
    *,
    write: bool = True,
) -> dict:
    """The metrics dict (see the module docstring). With ``run_dir`` and
    ``write``, also written to ``logs/quality_metrics.json``."""
    run_path = Path(run_dir) if run_dir is not None else None
    metrics: dict[str, Any] = {
        "v": METRICS_VERSION,
        "traced_pct": None,
        "unsupported_headline_figures": None,
        "repetition_index": None,
        "words_total": None,
        "words_by_section": None,
        "over_cap_sections": [],
        "metric_conflicts": 0,
        "zh_term_drift": 0,
        "untranslated_zh_lines": 0,
    }
    fact_check = None
    try:
        fact_check = _fact_check_payload(run_path, report)
        if isinstance(fact_check, dict):
            coverage = fact_check.get("coverage_pct")
            metrics["traced_pct"] = int(coverage) if isinstance(coverage, (int, float)) else None
            metrics["unsupported_headline_figures"] = unsupported_headline_figures(fact_check)
    except Exception:  # noqa: BLE001
        logger.warning("quality metrics: fact check unreadable", exc_info=True)
    if isinstance(package, dict):
        for key, fn in (
            ("repetition_index", lambda: repetition_index(package)),
            ("metric_conflicts", lambda: len(memo_fact_check.metric_conflicts(package))),
            ("untranslated_zh_lines", lambda: _untranslated_count(package, run_path)),
            ("zh_term_drift", lambda: _term_drift_count(package, run_path)),
        ):
            try:
                metrics[key] = fn()
            except Exception:  # noqa: BLE001
                logger.warning("quality metrics: %s failed", key, exc_info=True)
        try:
            total, by_section = word_counts(package)
            metrics["words_total"] = total
            metrics["words_by_section"] = by_section
            metrics["over_cap_sections"] = over_cap_sections(package, by_section)
        except Exception:  # noqa: BLE001
            logger.warning("quality metrics: word counts failed", exc_info=True)
    if write and run_path is not None:
        try:
            logs = run_path / "logs"
            logs.mkdir(parents=True, exist_ok=True)
            (logs / METRICS_FILENAME).write_text(
                json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError:
            logger.warning("quality metrics: could not write %s", run_path, exc_info=True)
    return metrics


def _glossary(run_path: Path | None) -> list[dict]:
    return memo_chinese_parity.load_run_glossary(run_path) if run_path is not None else []


def _untranslated_count(package: dict, run_path: Path | None) -> int:
    findings = memo_chinese_parity.untranslated_zh_lines(package, glossary=_glossary(run_path))
    if not findings:
        return 0
    # The first finding carries the total when the list was capped.
    match = re.search(r"\((\d+) such lines in all\)", findings[0].suggestion)
    return int(match.group(1)) if match else len(findings)


def _term_drift_count(package: dict, run_path: Path | None) -> int:
    glossary = _glossary(run_path)
    if not glossary:
        return 0
    return len(memo_chinese_parity.glossary_term_drift(package, glossary))


def load(run_dir: Path | str | None) -> dict | None:
    """The stored ``logs/quality_metrics.json`` of a run, or None."""
    if run_dir is None:
        return None
    payload = _load_json(Path(run_dir) / "logs" / METRICS_FILENAME)
    return payload if isinstance(payload, dict) else None
