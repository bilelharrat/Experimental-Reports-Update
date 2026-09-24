"""Background worker for Buffett-method memo generation.

Mirrors the late-stage memo handshake (run folder, stream.jsonl, bilingual
DOCX) but uses a dedicated skill and renderer. Claude writes
``logs/memo_package.json``; Python validates and renders.

The run is connected to the same provenance layer as the late-stage memo:
the company's research folder (fact ledger, tracked news, known sources)
reaches the prompt, every WebSearch/WebFetch is captured into the source
cache and the run's ``sources/manifest.jsonl``, and the share price and the
10-year Treasury yield are pinned from live quotes at run start
(``logs/market_inputs.json``) so two runs on one day use the same numbers.
At finalize the deterministic checks in ``buffett_checks`` run (voice,
valuation arithmetic, fact check, EN/ZH number parity, research signals);
they only ever add warnings.
"""
from __future__ import annotations

import atexit
import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import (
    buffett_checks,
    buffett_memo_renderer,
    claude_runner,
    job_progress,
    memo_prep,
    research_store,
    storage,
)
from .company_names import clean_display_name

logger = logging.getLogger(__name__)

_ACTIVE_LOCK = threading.Lock()
_ACTIVE_RUNS: set[str] = set()

# Statuses a finished (or refused) Buffett run ends in: recovery and the
# shutdown hook leave these alone.
TERMINAL_STATUSES = frozenset({"complete", "complete_with_warnings", "failed_scope_check"})

MARKET_INPUTS_FILENAME = "market_inputs.json"
# CNBC's symbol for the 10-year US Treasury yield (in percent); Yahoo's
# ^TNX is the fallback.
UST10Y_SYMBOL = "US10Y"


def _register_active_run(report_id: str) -> None:
    with _ACTIVE_LOCK:
        _ACTIVE_RUNS.add(report_id)


def _unregister_active_run(report_id: str) -> None:
    with _ACTIVE_LOCK:
        _ACTIVE_RUNS.discard(report_id)


def is_active(report_id: str) -> bool:
    with _ACTIVE_LOCK:
        return report_id in _ACTIVE_RUNS


@atexit.register
def _fail_active_runs_at_exit() -> None:
    with _ACTIVE_LOCK:
        active = list(_ACTIVE_RUNS)
    for report_id in active:
        try:
            report = storage.get_report(report_id)
            status = str((report or {}).get("status") or "")
            if not report or status.startswith("failed") or status in TERMINAL_STATUSES:
                continue
            message = "interrupted by server shutdown"
            storage.update_report(
                report_id,
                status="failed_during_analysis",
                stage="Analysis interrupted",
                error=message,
                failure_phase="shutdown",
                failure_detail=message,
            )
            run_dir = _resolve_run_dir(report)
            if run_dir is not None:
                stream = job_progress.ProgressLog(
                    memo_prep.stream_path(run_dir), truncate=False
                )
                stream.emit("error", error=message, phase="shutdown")
        except Exception:  # noqa: BLE001
            logger.exception(
                "failed to mark Buffett memo run %s interrupted at shutdown",
                report_id,
            )


def _resolve_run_dir(report: dict) -> Path | None:
    run_dir_rel = report.get("run_dir")
    if not run_dir_rel:
        return None
    return memo_prep.DATA_DIR.parent / str(run_dir_rel)


def _memo_paths_abs(report: dict) -> dict[str, Path]:
    return {
        str(entry.get("language")): memo_prep.DATA_DIR.parent / str(entry.get("path"))
        for entry in report.get("memo_files") or []
        if entry.get("language") and entry.get("path")
    }


def _fail(
    report_id: str,
    stream: job_progress.ProgressLog,
    *,
    message: str,
    stage: str,
    phase: str,
    result: dict[str, Any] | None = None,
) -> None:
    result = result or {}
    storage.update_report(
        report_id,
        status="failed_during_analysis",
        stage=stage,
        error=message,
        failure_phase=phase,
        failure_detail=message,
        claude_cost_usd=result.get("cost_usd"),
        claude_duration_ms=result.get("duration_ms"),
    )
    stream.emit("error", error=message, phase=phase)


# ---- provenance and pinned inputs ------------------------------------------------


def _research_dir(company_id: str) -> Path:
    """The company's research folder (``data/research/<storage key>``) —
    the same directory the source cache, fact ledger and fact check use.
    Always returned (it may not exist yet); never None."""
    try:
        from . import company_paths

        return research_store.RESEARCH_ROOT / company_paths.storage_key(company_id)
    except ValueError:
        return research_store.RESEARCH_ROOT / str(company_id)


def _prepare_provenance(report: dict, run_dir: Path, research_dir: Path) -> None:
    """Point source capture at this run and refresh the research digests
    (tracked news, known sources) the prompt reads. The decision-record
    digest is skipped on purpose: BSH's own process stays out of an owner's
    analysis. Best-effort: nothing here can fail a run."""
    company_id = str(report.get("company_id") or run_dir.parent.name)
    try:
        claude_runner.register_memo_run_source_capture(
            run_dir,
            company_id=company_id,
            run_id=str(report.get("run_id") or run_dir.name),
            research_dir=research_dir,
        )
    except Exception:  # noqa: BLE001
        logger.exception("source capture registration failed for %s", company_id)
    try:
        from . import memo_analysis

        memo_analysis._write_recent_news_file(company_id, research_dir)
        memo_analysis._write_known_sources_file(company_id, research_dir)
    except Exception:  # noqa: BLE001
        logger.exception("research digests failed for %s", company_id)


def _security(company: dict, company_name: str) -> dict[str, Any]:
    """The facts the prompt's ``## Security`` block states."""
    return {
        "name": company_name,
        "legal_name": clean_display_name(company.get("legal_name")) or None,
        "ticker": str(company.get("ticker") or "").strip() or None,
        "exchange": str(company.get("exchange") or "").strip() or None,
        "status": str(company.get("status") or "").strip() or None,
        "parent": str(company.get("parent_company") or company.get("parent") or "").strip() or None,
        "hq": str(company.get("hq") or "").strip() or None,
        "language": str(company.get("language") or "").strip() or None,
    }


def _quotes_enabled() -> bool:
    raw = os.environ.get("BSH_BUFFETT_PIN_QUOTES", "1")
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def _date_of(value: Any) -> str | None:
    text = str(value or "")
    return text[:10] if len(text) >= 10 and text[4] == "-" and text[7] == "-" else None


def _yahoo_tnx() -> dict | None:
    """The 10-year yield from Yahoo's ^TNX chart (fallback when CNBC has no
    US10Y). ^TNX has historically been quoted at ten times the yield."""
    from . import live_quotes

    payload = live_quotes._http_get_json(live_quotes._yahoo_chart_url("^TNX", "5d", "1d"))
    chart = live_quotes._parse_yahoo_chart(payload)
    value = chart.get("last_price")
    if value is None:
        return None
    value = float(value)
    if value > 25:
        value = value / 10.0
    return {"last_price": value, "as_of": chart.get("as_of"), "source": "yahoo ^TNX"}


def _pin_market_inputs(company: dict, run_dir: Path) -> dict[str, Any]:
    """The share price (when the company has a ticker) and the 10-year US
    Treasury yield, fetched once at run start with their dates and written
    to ``logs/market_inputs.json``. A quote fetch, not a model call; never
    raises. A missing value is recorded as missing — the prompt then asks
    for a model-sourced, dated figure and the finalize check warns."""
    ticker = str(company.get("ticker") or "").strip().upper() or None
    inputs: dict[str, Any] = {
        "ticker": ticker,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "price": None,
        "ust10y": None,
    }
    if not _quotes_enabled():
        inputs["status"] = "disabled"
        inputs["error"] = "BSH_BUFFETT_PIN_QUOTES=0"
    else:
        quotes: dict[str, Any] = {}
        try:
            from . import live_quotes

            wanted = [symbol for symbol in (ticker, UST10Y_SYMBOL) if symbol]
            quotes = (live_quotes.fetch_quotes(wanted) or {}).get("quotes") or {}
        except Exception as exc:  # noqa: BLE001
            inputs["error"] = f"{type(exc).__name__}: {exc}"
        quote = quotes.get(ticker) if ticker else None
        if isinstance(quote, dict) and quote.get("last_price") is not None:
            inputs.update(
                price=quote.get("last_price"),
                currency=quote.get("currency") or "USD",
                price_as_of=_date_of(quote.get("as_of")),
                price_source=quote.get("source"),
            )
        ust = quotes.get(UST10Y_SYMBOL)
        if not (isinstance(ust, dict) and ust.get("last_price") is not None):
            try:
                ust = _yahoo_tnx()
            except Exception as exc:  # noqa: BLE001
                ust = None
                inputs.setdefault("error", f"^TNX: {type(exc).__name__}: {exc}")
        if isinstance(ust, dict) and ust.get("last_price") is not None:
            value = float(ust["last_price"])
            if 0 < value < 25:
                inputs.update(
                    ust10y=round(value, 3),
                    ust10y_as_of=_date_of(ust.get("as_of")),
                    ust10y_source=ust.get("source") or "cnbc",
                )
        wanted_ok = [inputs.get("ust10y") is not None]
        if ticker:
            wanted_ok.append(inputs.get("price") is not None)
        inputs["status"] = (
            "pinned" if all(wanted_ok) else "partial" if any(wanted_ok) else "unavailable"
        )
    try:
        path = run_dir / "logs" / MARKET_INPUTS_FILENAME
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(inputs, indent=2) + "\n", encoding="utf-8")
    except OSError:
        logger.warning("could not write %s", MARKET_INPUTS_FILENAME, exc_info=True)
    return inputs


def _load_market_inputs(run_dir: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(
            (run_dir / "logs" / MARKET_INPUTS_FILENAME).read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _review_from_report(report: dict) -> dict | None:
    """The review record for the header stamp: ``report["review"]`` when it
    is a dict, else the flat ``review_state`` / ``reviewer`` /
    ``reviewed_at`` fields. None (no review yet) stamps DRAFT."""
    review = report.get("review")
    if isinstance(review, dict):
        return review
    state = report.get("review_state")
    if state:
        return {
            "state": state,
            "reviewer": report.get("reviewer") or report.get("reviewed_by"),
            "reviewed_at": report.get("reviewed_at"),
        }
    return None


def _run_checks(
    *,
    report: dict,
    run_dir: Path,
    package: dict,
    result: dict[str, Any],
    stream: job_progress.ProgressLog,
) -> buffett_checks.BuffettCheckReport | None:
    company_id = str(report.get("company_id") or run_dir.parent.name)
    web_lookups = result.get("web_lookups")
    try:
        checks = buffett_checks.run_checks(
            package,
            run_dir=run_dir,
            company_id=company_id,
            research_dir=_research_dir(company_id),
            market_inputs=_load_market_inputs(run_dir),
            web_lookups=int(web_lookups) if web_lookups is not None else None,
        )
    except Exception:  # noqa: BLE001 — checks never sink a finished memo
        logger.exception("Buffett memo checks failed for %s", report.get("id"))
        return None
    fact = checks.fact_check or {}
    stream.emit(
        "stage",
        stage="buffett_checks",
        message=(
            f"Checks: {len(checks.quality_warnings)} warning(s); fact check "
            f"{fact.get('checked', 0)} figures, {fact.get('unsupported', 0)} unsupported"
            + (" (thin corpus)" if fact.get("thin_corpus") else "")
        ),
        quality_warnings=checks.quality_warnings,
        web_lookups=checks.web_lookups,
        fact_check_status=fact.get("status"),
    )
    return checks


def _finalize_from_package(
    *,
    report_id: str,
    report: dict,
    run_dir: Path,
    stream: job_progress.ProgressLog,
    result: dict[str, Any],
) -> bool:
    memo_paths_abs = _memo_paths_abs(report)
    if "en" not in memo_paths_abs or "zh" not in memo_paths_abs:
        _fail(
            report_id,
            stream,
            message="Buffett memo report is missing English/Chinese output paths",
            stage="Renderer paths missing",
            phase="renderer_contract",
            result=result,
        )
        return False
    from . import memo_analysis

    try:
        package = buffett_memo_renderer.load_package(run_dir)
        # Which model wrote it (role BUFFETT), on the package the documents
        # are rendered from and kept on disk for a later re-render. A
        # package already stamped (a re-finalize) keeps its own stamp.
        run_block = package.get("run") if isinstance(package.get("run"), dict) else {}
        generated_with = run_block.get("generated_with")
        if not isinstance(generated_with, dict):
            generated_with = memo_analysis._stamp_generated_with(
                package, report, run_dir, buffett=True
            )
            if generated_with is not None:
                try:
                    buffett_memo_renderer.package_path(run_dir).write_text(
                        json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8"
                    )
                except OSError:
                    logger.warning("could not persist generated_with", exc_info=True)
        rendered = buffett_memo_renderer.render_package(
            package,
            run_dir=run_dir,
            memo_paths=memo_paths_abs,
            review=_review_from_report(report),
        )
    except buffett_memo_renderer.BuffettMemoPackageError as exc:
        _fail(
            report_id,
            stream,
            message=str(exc),
            stage="Buffett memo package invalid",
            phase="renderer_contract",
            result=result,
        )
        return False

    en_ok = memo_paths_abs["en"].exists()
    zh_ok = memo_paths_abs["zh"].exists()
    if not en_ok or not zh_ok:
        missing = []
        if not en_ok:
            missing.append("English .docx")
        if not zh_ok:
            missing.append("Chinese .docx")
        _fail(
            report_id,
            stream,
            message="Renderer finished but outputs are missing: " + ", ".join(missing),
            stage="Renderer completed but outputs missing",
            phase="post_run_check",
            result=result,
        )
        return False

    decision = rendered.get("decision")
    record = buffett_memo_renderer.report_fields(rendered)
    checks = _run_checks(
        report=report, run_dir=run_dir, package=package, result=result, stream=stream
    )
    check_fields = checks.record_patch() if checks is not None else {}
    quality_warnings = list(checks.quality_warnings) if checks is not None else []
    quality_warnings_zh = list(checks.quality_warnings_zh) if checks is not None else []
    market_inputs = _load_market_inputs(run_dir)
    status = "complete_with_warnings" if quality_warnings else "complete"
    storage.update_report(
        report_id,
        status=status,
        stage="Memo ready (quality warnings)" if quality_warnings else "Memo ready",
        progress=100,
        error=None,
        failure_phase=None,
        failure_detail=None,
        artifacts_available=True,
        content=rendered.get("content_en") or "",
        content_en=rendered.get("content_en"),
        content_zh=rendered.get("content_zh"),
        claude_cost_usd=result.get("cost_usd"),
        claude_duration_ms=result.get("duration_ms"),
        renderer_version=rendered.get("renderer_version"),
        report_ready_at=datetime.now(timezone.utc).isoformat(),
        generated_with=generated_with,
        **record,
        **check_fields,
        quality_warning_items=_warning_items(
            quality_warnings,
            quality_warnings_zh,
            detail_path=memo_prep._rel(run_dir / "logs" / "buffett_checks.md"),
        ),
        **({"market_inputs": market_inputs} if market_inputs is not None else {}),
    )
    stream.emit(
        "done",
        report_id=report_id,
        memo_paths={k: str(v) for k, v in memo_paths_abs.items()},
        cost_usd=result.get("cost_usd"),
        duration_ms=result.get("duration_ms"),
        decision=decision,
        status=status,
        quality_warnings=quality_warnings,
    )
    # What hangs off a finished memo (the list row's verdict and age, the
    # lazily made PDF) — the same hooks the late-stage pipeline runs.
    memo_analysis._run_completion_hooks(report_id)
    return True


def _warning_items(
    en: list[str], zh: list[str], *, detail_path: str | None = None
) -> list[dict] | None:
    """The structured twin of a Buffett run's warnings for the web banner
    ([{gate, language, section, severity, code, summary_en, summary_zh,
    detail_path}]); the aligned English/Chinese strings come from
    buffett_checks."""
    items: list[dict] = []
    for index, text in enumerate(en):
        text_zh = zh[index] if index < len(zh) else ""
        lowered = str(text).lower()
        if "parity" in lowered or "chinese" in lowered:
            gate, language = "chinese_parity", "ZH"
        elif "fact" in lowered:
            gate, language = "fact_check", "EN"
        else:
            gate, language = "quality", "EN"
        items.append(
            {
                "gate": gate,
                "language": language,
                "section": None,
                "severity": "warning",
                "code": "buffett_checks",
                "summary_en": str(text),
                "summary_zh": str(text_zh or text),
                "detail_path": detail_path,
            }
        )
    return items or None


def start_analysis(report_id: str) -> threading.Thread:
    t = threading.Thread(
        target=_run_safe,
        args=(report_id,),
        name=f"buffett-memo-analysis-{report_id}",
        daemon=True,
    )
    t.start()
    return t


def start_resume(report_id: str) -> threading.Thread:
    t = threading.Thread(
        target=_resume_safe,
        args=(report_id,),
        name=f"buffett-memo-resume-{report_id}",
        daemon=True,
    )
    t.start()
    return t


def _run_safe(report_id: str) -> None:
    # Lazy import: memo_analysis owns the shared run-slot registry and does
    # not import this module, so there is no cycle at call time.
    from . import memo_analysis

    _register_active_run(report_id)
    try:
        memo_analysis._with_run_slot(report_id, lambda: _run(report_id))
    except Exception as exc:  # noqa: BLE001
        logger.exception("Buffett memo analysis crashed")
        # The cause on the record ("ValueError: …") and the traceback in
        # logs/crash.txt, never "see server log".
        memo_analysis._record_worker_crash(
            report_id,
            exc,
            phase="analysis",
            stage="Analysis crashed",
            label="Buffett memo analysis worker crashed",
            sync_tracking=False,
        )
    finally:
        _unregister_active_run(report_id)


def _resume_safe(report_id: str) -> None:
    from . import memo_analysis

    _register_active_run(report_id)
    try:
        memo_analysis._with_run_slot(report_id, lambda: _resume(report_id))
    except Exception as exc:  # noqa: BLE001
        logger.exception("Buffett memo resume crashed")
        memo_analysis._record_worker_crash(
            report_id,
            exc,
            phase="resume",
            stage="Resume crashed",
            label="Buffett memo resume worker crashed",
            sync_tracking=False,
        )
    finally:
        _unregister_active_run(report_id)


def _run(report_id: str) -> None:
    report = storage.get_report(report_id)
    if report is None:
        raise RuntimeError(f"Unknown report: {report_id}")
    if not memo_prep.is_buffett_kind(report.get("kind")):
        raise RuntimeError(f"Report {report_id} is not a Buffett investment memo")
    run_dir = _resolve_run_dir(report)
    if run_dir is None or not run_dir.exists():
        raise RuntimeError(f"Run folder missing for report {report_id}")

    stream = job_progress.ProgressLog(memo_prep.stream_path(run_dir), truncate=False)
    company_slug = str(report.get("company_id"))
    company = storage.get_company(company_slug) or {}
    # The clean display name: EDGAR tokens (" /De/") never reach the prompt.
    company_name = (
        clean_display_name(report.get("company_name"))
        or memo_prep.company_display_name(company, fallback=company_slug)
        or company_slug
    )
    run_id = str(report.get("run_id") or "")
    memo_paths_abs = _memo_paths_abs(report)
    # Always the company's research folder (it may not exist yet): source
    # capture writes the known-sources digest there as retrievals land.
    research_dir = _research_dir(company_slug)
    _prepare_provenance(report, run_dir, research_dir)
    market_inputs = _pin_market_inputs(company, run_dir)
    stream.emit(
        "stage",
        stage="market_inputs",
        message=(
            "Market inputs pinned"
            if market_inputs.get("status") == "pinned"
            else f"Market inputs: {market_inputs.get('status')}"
        ),
        **{
            key: market_inputs.get(key)
            for key in ("ticker", "price", "price_as_of", "ust10y", "ust10y_as_of", "status")
        },
    )

    storage.update_report(
        report_id,
        status="analyzing",
        stage="Running Buffett investment-memo skill",
        progress=15,
    )
    stream.emit(
        "stage",
        stage="analysis_starting",
        message="Running Buffett investment analysis and memorandum",
    )

    from . import memo_analysis as _memo_analysis

    with _memo_analysis._creeping_report_progress(
        report_id,
        floor=15,
        ceiling=78,
        stage="Running Buffett investment-memo skill",
    ):
        result = claude_runner.run_buffett_investment_memo(
            run_dir=run_dir,
            company_name=company_name,
            company_slug=company_slug,
            run_id=run_id,
            companies_yaml_path=memo_prep.COMPANIES_FILE,
            memo_paths={k: str(v) for k, v in memo_paths_abs.items()},
            research_dir=research_dir,
            scope_check=report.get("scope_check"),
            warnings=list(report.get("warnings") or []),
            progress=stream,
            timeout_sec=3600,
            security=_security(company, company_name),
            market_inputs=market_inputs,
            today=datetime.now().astimezone().date().isoformat(),
        )
    if result.get("web_lookups") is not None:
        storage.update_report(
            report_id,
            web_lookups=int(result["web_lookups"]),
            **(
                {"retrieved_sources": int(result["retrieved_sources"])}
                if result.get("retrieved_sources") is not None
                else {}
            ),
        )
    if not result.get("ok"):
        message = result.get("error") or "Claude skill run failed"
        if buffett_memo_renderer.package_path(run_dir).exists():
            stream.emit(
                "stage",
                stage="claude_failed_with_package",
                message="Claude returned an error; attempting to render the package on disk",
            )
            if _finalize_from_package(
                report_id=report_id,
                report=report,
                run_dir=run_dir,
                stream=stream,
                result=result,
            ):
                return
        _fail(
            report_id,
            stream,
            message=message,
            stage="Buffett memo skill failed",
            phase="analysis",
            result=result,
        )
        return

    storage.update_report(report_id, stage="Rendering Buffett memorandum", progress=85)
    _finalize_from_package(
        report_id=report_id,
        report=report,
        run_dir=run_dir,
        stream=stream,
        result=result,
    )


def _resume(report_id: str) -> None:
    report = storage.get_report(report_id)
    if report is None:
        raise RuntimeError(f"Unknown report: {report_id}")
    if not memo_prep.is_buffett_kind(report.get("kind")):
        raise RuntimeError(f"Report {report_id} is not a Buffett investment memo")
    run_dir = _resolve_run_dir(report)
    if run_dir is None or not run_dir.exists():
        raise RuntimeError(f"Run folder missing for report {report_id}")

    stream_path = memo_prep.stream_path(run_dir)
    if stream_path.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        archive = stream_path.with_name(f"stream.before_resume.{stamp}.jsonl")
        try:
            stream_path.replace(archive)
        except OSError:
            logger.exception("failed to archive Buffett memo stream before resume")

    stream = job_progress.ProgressLog(stream_path, truncate=True)
    stream.emit("stage", stage="resume_started", message="Resuming Buffett investment memo")
    storage.update_report(
        report_id,
        status="analyzing",
        stage="Resume queued",
        progress=max(int(report.get("progress") or 0), 60),
    )

    if buffett_memo_renderer.package_path(run_dir).exists():
        if _finalize_from_package(
            report_id=report_id,
            report=report,
            run_dir=run_dir,
            stream=stream,
            result={
                "cost_usd": report.get("claude_cost_usd"),
                "duration_ms": report.get("claude_duration_ms"),
                # None → counted from the run's (archived) progress streams.
                "web_lookups": report.get("web_lookups"),
            },
        ):
            return

    _run(report_id)


def recover_stale_reports() -> int:
    """Demote abandoned Buffett memo runs so they become resume-eligible."""
    recovered = 0
    for report in storage.list_reports():
        if not memo_prep.is_buffett_kind(report.get("kind")):
            continue
        status = str(report.get("status") or "")
        if status in TERMINAL_STATUSES or status.startswith("failed"):
            continue
        report_id = str(report.get("id") or "")
        if not report_id or is_active(report_id):
            continue
        run_dir = _resolve_run_dir(report)
        if run_dir is None or not run_dir.exists():
            continue
        package = buffett_memo_renderer.package_path(run_dir)
        if package.exists():
            stream = job_progress.ProgressLog(
                memo_prep.stream_path(run_dir), truncate=False
            )
            if _finalize_from_package(
                report_id=report_id,
                report=report,
                run_dir=run_dir,
                stream=stream,
                result={
                    "cost_usd": report.get("claude_cost_usd"),
                    "duration_ms": report.get("claude_duration_ms"),
                    "web_lookups": report.get("web_lookups"),
                },
            ):
                recovered += 1
                continue
        message = "orphaned by server restart"
        storage.update_report(
            report_id,
            status="failed_during_analysis",
            stage="Analysis orphaned",
            error=message,
            failure_phase="orphaned",
            failure_detail=message,
        )
        stream = job_progress.ProgressLog(
            memo_prep.stream_path(run_dir), truncate=False
        )
        stream.emit("error", error=message, phase="orphaned", recovered=True)
        recovered += 1
    return recovered
