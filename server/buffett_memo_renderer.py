"""Render a Buffett investment-memo package to Markdown and DOCX.

Claude writes ``logs/memo_package.json``. Python validates the package and
renders both language Word files. Per-run renderer scripts are forbidden.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .internal_memo_renderer import InternalMemoRenderError, render_internal_memo

SCHEMA_VERSION = 1
KIND = "buffett_investment_memo"
DECISIONS = frozenset({"Buy", "Pass", "Too Hard"})

REQUIRED_HEADINGS_EN = (
    "## I. Investment Decision",
    "## II. The Business",
    "## III. Circle of Competence",
    "## IV. Economic Characteristics",
    "## V. Durable Competitive Advantage",
    "## VI. Management and Capital Allocation",
    "## VII. Financial Position",
    "## VIII. Intrinsic Value and Margin of Safety",
    "## IX. What Can Go Permanently Wrong",
    "## X. Conclusion",
)
REQUIRED_HEADINGS_ZH = (
    "## 一、投资决策",
    "## 二、这家企业",
    "## 三、能力圈",
    "## 四、经济特征",
    "## 五、持久竞争优势",
    "## 六、管理层与资本配置",
    "## 七、财务状况",
    "## 八、内在价值与安全边际",
    "## 九、可能造成永久损失的因素",
    "## 十、结论",
)

MIN_MARKDOWN_CHARS = 800


class BuffettMemoPackageError(ValueError):
    """Raised when the Buffett memo package cannot be rendered."""


def package_path(run_dir: Path | str) -> Path:
    return Path(run_dir) / "logs" / "memo_package.json"


def load_package(run_dir: Path | str) -> dict[str, Any]:
    path = package_path(run_dir)
    if not path.exists():
        raise BuffettMemoPackageError(f"Buffett memo package missing: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BuffettMemoPackageError(f"Buffett memo package is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise BuffettMemoPackageError("Buffett memo package must be a JSON object")
    return payload


def validate_package(package: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    version = package.get("schema_version")
    if version != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    kind = package.get("kind")
    if kind not in (KIND, None):
        errors.append(f"kind must be {KIND!r}")
    decision = str(package.get("decision") or "").strip()
    if decision not in DECISIONS:
        errors.append("decision must be Buy, Pass, or Too Hard")
    markdown_en = str(package.get("markdown_en") or "").strip()
    markdown_zh = str(package.get("markdown_zh") or "").strip()
    if len(markdown_en) < MIN_MARKDOWN_CHARS:
        errors.append("markdown_en is too short for an investment memorandum")
    if len(markdown_zh) < MIN_MARKDOWN_CHARS:
        errors.append("markdown_zh is too short for an investment memorandum")
    for heading in REQUIRED_HEADINGS_EN:
        if heading not in markdown_en:
            errors.append(f"English memo missing heading: {heading}")
    for heading in REQUIRED_HEADINGS_ZH:
        if heading not in markdown_zh:
            errors.append(f"Chinese memo missing heading: {heading}")
    if decision and decision.lower() not in markdown_en.lower() and decision not in markdown_en:
        # Buy/Pass/Too Hard should appear in Section I.
        if decision not in markdown_en:
            errors.append("English memo does not state the recorded decision")
    if errors:
        raise BuffettMemoPackageError("; ".join(errors))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "company_name": str(package.get("company_name") or "").strip(),
        "decision": decision,
        "buy_price": str(package.get("buy_price") or "").strip(),
        "markdown_en": markdown_en,
        "markdown_zh": markdown_zh,
    }


def preview_text(markdown: str, *, limit: int = 12000) -> str:
    text = (markdown or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def render_package(
    package: dict[str, Any],
    *,
    run_dir: Path | str,
    memo_paths: dict[str, Path | str],
) -> dict[str, Any]:
    """Validate, write Markdown working copies, and render both DOCX files."""
    validated = validate_package(package)
    root = Path(run_dir)
    memo_dir = root / "memo"
    memo_dir.mkdir(parents=True, exist_ok=True)
    en_md = memo_dir / "buffett_memo.en.md"
    zh_md = memo_dir / "buffett_memo.zh.md"
    en_md.write_text(validated["markdown_en"] + "\n", encoding="utf-8")
    zh_md.write_text(validated["markdown_zh"] + "\n", encoding="utf-8")

    en_docx = Path(memo_paths["en"])
    zh_docx = Path(memo_paths["zh"])
    try:
        render_internal_memo(en_md, en_docx)
        render_internal_memo(zh_md, zh_docx)
    except InternalMemoRenderError as exc:
        raise BuffettMemoPackageError(str(exc)) from exc

    return {
        "ok": True,
        "decision": validated["decision"],
        "markdown_en": str(en_md),
        "markdown_zh": str(zh_md),
        "docx_en": str(en_docx),
        "docx_zh": str(zh_docx),
        "content_en": preview_text(validated["markdown_en"]),
        "content_zh": preview_text(validated["markdown_zh"]),
    }
