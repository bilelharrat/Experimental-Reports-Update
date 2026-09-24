"""Render a Buffett-method memo package to Markdown and DOCX.

Claude writes ``logs/memo_package.json``. Python validates the package and
renders both language Word files. Per-run renderer scripts are forbidden.

The memo is BSH Research's owner's analysis written with Warren Buffett's
method, not a memo by Buffett, and the document frame says so: a BSH header
with the review stamp, a "Page X of Y" footer with the confidentiality line
and the disclaimer, document properties, and a decision box under the title.
When the package carries the optional structured valuation fields, the
renderer also draws "The arithmetic" / "估值算术" table in both languages
from those numbers (so the two documents cannot drift), and a "Sources" /
"资料来源" list after section X.

Every structured field is optional: packages written before they existed
(schema_version 1, no fields) validate and render exactly as far as their
content allows, and ``render_package`` is a pure re-render of a stored
package — no model call, nothing read but the package and the run's own
source manifest.
"""
from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .company_names import clean_display_name
from .internal_memo_renderer import InternalMemoRenderError, render_internal_memo

SCHEMA_VERSION = 1
# A package that says 2 (the structured fields) is accepted too; the fields
# are optional either way, so 1 stays the version the skill writes.
ACCEPTED_SCHEMA_VERSIONS = frozenset({1, 2})
KIND = "buffett_investment_memo"
DECISIONS = frozenset({"Buy", "Pass", "Too Hard"})
PASS_KINDS = frozenset({"price", "business"})
RENDERER_VERSION = "buffett-frame-2026-09-22"
# ``render_package(review=…)`` prints the draft/reviewed/withdrawn stamp.
SUPPORTS_REVIEW_STAMP = True

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

# ---- document frame -----------------------------------------------------------

DOC_AUTHOR = "Berkeley Summit House"
HEADER_TEMPLATE = {
    "en": "{company} | BSH Research — Owner's analysis (Buffett method)",
    "zh": "{company} | BSH 研究 — 巴菲特方法所有者分析",
}
DOC_TITLE_TEMPLATE = {
    "en": "{company} — Buffett-Method Memo",
    "zh": "{company} — 巴菲特方法备忘录",
}
DOC_SUBJECT = {
    "en": "BSH Research · Owner's analysis (Buffett method)",
    "zh": "BSH 研究 · 巴菲特方法所有者分析",
}
DISCLAIMER = {
    "en": (
        "Prepared by BSH Research using a Buffett-style owner's framework; "
        "not written or endorsed by Warren Buffett or Berkshire Hathaway."
    ),
    "zh": "本文由 BSH 研究采用巴菲特式所有者分析框架撰写，并非由沃伦·巴菲特或伯克希尔·哈撒韦公司撰写或认可。",
}
CONFIDENTIAL = {"en": "BSH Confidential", "zh": "BSH 机密"}
LANGUAGE_TAG = {"en": "EN", "zh": "中文"}

# Review stamp (header), same wording as the late-stage renderer. The state
# comes from ``package["run"]["review"]`` or the ``review`` argument:
# ``{"state": "draft"|"in_review"|"approved"|"withdrawn", "reviewer", "reviewed_at"}``.
REVIEW_STAMP = {
    "draft": {"en": "DRAFT — AI-generated, not reviewed", "zh": "草稿 — AI 生成，未经审阅"},
    "withdrawn": {"en": "WITHDRAWN — do not rely on this memo", "zh": "已撤回 — 请勿依据本备忘录"},
}
REVIEWED_STAMP = {"en": "Reviewed by {name}, {date}", "zh": "已审阅：{name}，{date}"}
REVIEWED_STAMP_NO_NAME = {"en": "Reviewed, {date}", "zh": "已审阅，{date}"}
STAMP_COLOR = {"draft": "9A6700", "approved": "2E6B45", "withdrawn": "B42318"}

# ---- structured fields ----------------------------------------------------------
#
# Per-share figures are in `currency`; totals (earnings, D&A, capex, working
# capital, owner's earnings) in millions of `currency`; diluted shares in
# millions; percentages as percent numbers (10 = 10%). With value_basis
# "company" the value range and buy price are whole-company values in
# millions of `currency` (private companies with no share count).

NUMERIC_FIELDS = (
    "price",
    "ust10y",
    "hurdle",
    "g",
    "earnings",
    "d_and_a",
    "maintenance_capex",
    "working_capital",
    "owner_earnings",
    "diluted_shares",
    "owner_earnings_per_share",
    "multiple",
    "value_low",
    "value_central",
    "value_high",
    "required_mos_pct",
    "buy_price_value",
    "mos_pct",
)
DATE_FIELDS = ("price_date", "ust10y_date")
# Persisted on the report record (``buffett_valuation``) when present.
RECORD_VALUATION_FIELDS = (
    "currency",
    "price",
    "price_date",
    "ust10y",
    "ust10y_date",
    "hurdle",
    "g",
    "value_basis",
    "value_low",
    "value_central",
    "value_high",
    "required_mos_pct",
    "buy_price_value",
    "mos_pct",
    "owner_earnings",
    "maintenance_capex",
    "d_and_a",
    "diluted_shares",
    "valuation_basis",
)

CURRENCY_SYMBOL = {
    "USD": "$",
    "HKD": "HK$",
    "TWD": "NT$",
    "CNY": "CN¥",
    "RMB": "CN¥",
    "EUR": "€",
    "GBP": "£",
    "JPY": "¥",
    "CAD": "C$",
    "AUD": "A$",
    "SGD": "S$",
}
CURRENCY_ZH = {
    "USD": "美元",
    "HKD": "港元",
    "TWD": "新台币",
    "CNY": "元人民币",
    "RMB": "元人民币",
    "EUR": "欧元",
    "GBP": "英镑",
    "JPY": "日元",
    "CAD": "加元",
    "AUD": "澳元",
    "SGD": "新加坡元",
}


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
    """Hard checks only (the ones a renderable memo needs); every structured
    field is optional and a malformed one is dropped, never an error —
    ``check_valuation`` and ``buffett_checks`` report on them as warnings."""
    errors: list[str] = []
    version = package.get("schema_version")
    if version not in ACCEPTED_SCHEMA_VERSIONS:
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
    fields = structured_fields(package)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "company_name": clean_display_name(package.get("company_name")),
        "company_name_zh": _text(package.get("company_name_zh")),
        "decision": decision,
        "pass_kind": fields.get("pass_kind") if decision == "Pass" else None,
        "buy_price": str(package.get("buy_price") or "").strip(),
        "buy_price_zh": _text(package.get("buy_price_zh")),
        "fields": fields,
        "sources": normalize_sources(package.get("sources")),
        "markdown_en": markdown_en,
        "markdown_zh": markdown_zh,
    }


def preview_text(markdown: str, *, limit: int = 12000) -> str:
    text = (markdown or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


# ---- field parsing ----------------------------------------------------------------


def _text(value: Any) -> str | None:
    text = " ".join(str(value or "").split())
    return text or None


def _number(value: Any) -> float | None:
    """A JSON number, or a numeric string such as "$92.10", "4.25%",
    "1,012" or "−3.5". Anything else is None."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        text = str(value).strip().replace("−", "-").replace(",", "")
        text = re.sub(r"^(?:US\$|NT\$|HK\$|[A-Z]{3}\s*|[$€£¥])", "", text)
        text = text.rstrip("%x× ").strip()
        try:
            number = float(text)
        except ValueError:
            return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _date(value: Any) -> str | None:
    match = re.match(r"^\s*(\d{4}-\d{2}-\d{2})", str(value or ""))
    return match.group(1) if match else None


def structured_fields(package: dict[str, Any]) -> dict[str, Any]:
    """The optional structured fields, parsed. Top-level keys win over the
    same keys inside an optional ``valuation`` object; malformed values are
    dropped."""
    merged: dict[str, Any] = {}
    nested = package.get("valuation")
    if isinstance(nested, dict):
        merged.update(nested)
    merged.update({key: value for key, value in package.items() if value is not None})
    out: dict[str, Any] = {}
    for key in NUMERIC_FIELDS:
        number = _number(merged.get(key))
        if number is not None:
            out[key] = number
    # Hurdle and required MoS are house percentages (≥ 10); a fraction
    # such as 0.10 is the same rate written the other way.
    for key in ("hurdle", "required_mos_pct"):
        if key in out and 0 < out[key] < 1:
            out[key] = round(out[key] * 100, 6)
    for key in DATE_FIELDS:
        parsed = _date(merged.get(key) or (merged.get("price_as_of") if key == "price_date" else None))
        if parsed:
            out[key] = parsed
    currency = str(merged.get("currency") or "").strip().upper()
    if re.fullmatch(r"[A-Z]{3}", currency):
        out["currency"] = currency
    basis = str(merged.get("value_basis") or "").strip().lower().replace("-", "_")
    if basis in {"per_share", "company"}:
        out["value_basis"] = basis
    elif any(key in out for key in ("value_low", "value_central", "value_high", "buy_price_value")):
        out["value_basis"] = "per_share"
    valuation_basis = str(merged.get("valuation_basis") or "").strip().lower()
    if valuation_basis in {"disclosed", "assumed"}:
        out["valuation_basis"] = valuation_basis
    pass_kind = str(merged.get("pass_kind") or "").strip().lower()
    if pass_kind in PASS_KINDS:
        out["pass_kind"] = pass_kind
    adjustments = []
    for item in merged.get("adjustments") or []:
        if not isinstance(item, dict):
            continue
        per_share = _number(item.get("per_share"))
        label = _text(item.get("label"))
        if per_share is None or not label:
            continue
        adjustments.append(
            {
                "label": label,
                "label_zh": _text(item.get("label_zh")),
                "per_share": per_share,
                "why": _text(item.get("why")),
            }
        )
    if adjustments:
        out["adjustments"] = adjustments
    return out


def normalize_sources(raw: Any) -> list[dict[str, Any]]:
    """``sources[]`` as ``{n, title, url, accessed}``, numbered and sorted.
    Accepts ``n``/``id``/``number`` for the marker and ``accessed``/
    ``accessed_at``/``date`` for the access date."""
    out: list[dict[str, Any]] = []
    seen: set[int] = set()
    for index, item in enumerate(raw or [], start=1):
        if not isinstance(item, dict):
            continue
        marker = item.get("n", item.get("id", item.get("number")))
        number = _number(re.sub(r"[^\d.]", "", str(marker)) if marker is not None else None)
        n = int(number) if number is not None and number > 0 else index
        if n in seen:
            continue
        title = _text(item.get("title"))
        url = _text(item.get("url"))
        if not title and not url:
            continue
        seen.add(n)
        out.append(
            {
                "n": n,
                "title": title or url or "",
                "url": url,
                "accessed": _date(item.get("accessed") or item.get("accessed_at") or item.get("date")),
            }
        )
    out.sort(key=lambda row: row["n"])
    return out


# ---- sections -------------------------------------------------------------------------


def split_sections(markdown: str) -> list[tuple[str, str]]:
    """``(heading, body)`` for every ``## `` section, in order; text before
    the first section is returned under the heading ``""``."""
    sections: list[tuple[str, str]] = []
    heading = ""
    body: list[str] = []
    for line in (markdown or "").splitlines():
        if line.startswith("## "):
            sections.append((heading, "\n".join(body)))
            heading = line[3:].strip()
            body = []
        else:
            body.append(line)
    sections.append((heading, "\n".join(body)))
    return sections


def section_body(markdown: str, heading: str) -> str:
    """Body of the ``## `` section whose heading starts with ``heading``
    (given with or without the ``## `` prefix)."""
    wanted = heading[3:] if heading.startswith("## ") else heading
    for title, body in split_sections(markdown):
        if title.startswith(wanted):
            return body
    return ""


def _title_company(markdown: str) -> str | None:
    """The company in the memo's ``#`` title (after the dash)."""
    for line in (markdown or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if not stripped.startswith("# "):
            return None
        match = re.match(r"^#\s+.*?\s[—–-]\s*(.+)$", stripped)
        return _text(match.group(1)) if match else None
    return None


# ---- formatting -------------------------------------------------------------------------


def _trim(value: float) -> str:
    """Up to one decimal below 100, none above; thousands separators."""
    if abs(value) >= 100 or abs(value - round(value)) < 0.05:
        return f"{round(value):,}"
    return f"{value:,.1f}"


def _per_share_text(value: float) -> str:
    if abs(value - round(value)) < 0.005:
        return f"{round(value):,}"
    return f"{value:,.2f}"


def _sign(text: str, value: float) -> str:
    return ("−" + text.lstrip("-")) if value < 0 else text


def format_money(
    value: float,
    currency: str | None,
    locale: str,
    *,
    millions: bool = False,
) -> str:
    """A per-share amount ("$92.10" / "92.10 美元"), or with ``millions`` a
    total given in millions ("$13.5 billion" / "135 亿美元")."""
    code = (currency or "USD").upper()
    magnitude = abs(value)
    if locale == "zh":
        unit = CURRENCY_ZH.get(code, code)
        if not millions:
            return _sign(f"{_per_share_text(magnitude)} {unit}", value)
        if magnitude >= 1_000_000:
            return _sign(f"{_trim(magnitude / 1_000_000)} 万亿{unit}", value)
        if magnitude >= 100:
            return _sign(f"{_trim(magnitude / 100)} 亿{unit}", value)
        return _sign(f"{_trim(magnitude * 100)} 万{unit}", value)
    symbol = CURRENCY_SYMBOL.get(code)
    prefix = symbol if symbol else f"{code} "
    if not millions:
        return _sign(f"{prefix}{_per_share_text(magnitude)}", value)
    if magnitude >= 1_000_000:
        return _sign(f"{prefix}{_trim(magnitude / 1_000_000)} trillion", value)
    if magnitude >= 1_000:
        return _sign(f"{prefix}{_trim(magnitude / 1_000)} billion", value)
    return _sign(f"{prefix}{_trim(magnitude)} million", value)


def format_pct(value: float) -> str:
    text = f"{abs(value):.2f}".rstrip("0").rstrip(".")
    return _sign(f"{text}%", value) if value < 0 else f"{text}%"


def _format_shares(value: float, locale: str) -> str:
    if locale == "zh":
        if value >= 100:
            return f"{_trim(value / 100)} 亿股"
        return f"{_trim(value * 100)} 万股"
    if value >= 1_000:
        return f"{_trim(value / 1_000)} billion shares"
    return f"{_trim(value)} million shares"


def _value_text(fields: dict[str, Any], key: str, locale: str) -> str | None:
    """A value-range or buy-price field in its basis (per share or whole
    company)."""
    value = fields.get(key)
    if value is None:
        return None
    company = fields.get("value_basis") == "company"
    return format_money(value, fields.get("currency"), locale, millions=company)


# ---- call labels and the decision box ------------------------------------------------------


def call_label(
    decision: str,
    pass_kind: str | None,
    fields: dict[str, Any] | None = None,
) -> dict[str, str]:
    """The call as a reader-facing label, EN and ZH. A price-conditional
    Pass reads "暂不买入（买入价 ≤ X）" in Chinese; a Pass at any price reads
    放弃; Too Hard keeps "Too Hard（超出能力圈）"."""
    fields = fields or {}
    buy_en = _value_text(fields, "buy_price_value", "en")
    buy_zh = _value_text(fields, "buy_price_value", "zh")
    if decision == "Buy":
        return {
            "en": f"Buy — at or below {buy_en}" if buy_en else "Buy",
            "zh": f"买入（买入价 ≤ {buy_zh}）" if buy_zh else "买入",
        }
    if decision == "Pass":
        if pass_kind == "price":
            return {
                "en": (
                    f"Pass at today's price — buy at or below {buy_en}"
                    if buy_en
                    else "Pass at today's price"
                ),
                "zh": f"暂不买入（买入价 ≤ {buy_zh}）" if buy_zh else "暂不买入",
            }
        if pass_kind == "business":
            return {"en": "Pass — not at any price", "zh": "放弃"}
        return {"en": "Pass", "zh": "放弃"}
    if decision == "Too Hard":
        return {"en": "Too Hard", "zh": "Too Hard（超出能力圈）"}
    return {"en": decision, "zh": decision}


_LEGACY_MONEY_RE = re.compile(
    r"(?P<cur>US\$|NT\$|HK\$|\$)\s?(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"(?:\s?(?P<scale>million|billion|trillion)\b)?",
    re.I,
)
_LEGACY_CURRENCY = {"US$": "USD", "$": "USD", "NT$": "TWD", "HK$": "HKD"}
_LEGACY_SCALE = {"million": 1.0, "billion": 1_000.0, "trillion": 1_000_000.0}


def _legacy_buy_price_zh(text: str) -> str:
    """A Chinese reading of an English-only buy price (packages written
    before ``buy_price_zh`` existed): its first money figure in Chinese
    units, pointing to section 一 for the wording; just the pointer when
    the text states no figure."""
    match = _LEGACY_MONEY_RE.search(text or "")
    if not match:
        return "见第一节"
    currency = _LEGACY_CURRENCY.get(match.group("cur").upper(), "USD")
    value = float(match.group("num").replace(",", ""))
    scale = (match.group("scale") or "").lower()
    if scale:
        amount = format_money(value * _LEGACY_SCALE[scale], currency, "zh", millions=True)
    else:
        amount = format_money(value, currency, "zh")
    return f"{amount}（详见第一节）"


def _buy_price_display(validated: dict[str, Any], locale: str) -> str | None:
    fields = validated["fields"]
    if locale == "zh":
        if validated.get("buy_price_zh"):
            return validated["buy_price_zh"]
    elif validated.get("buy_price"):
        return validated["buy_price"]
    formatted = _value_text(fields, "buy_price_value", locale)
    if formatted:
        if fields.get("value_basis") == "company":
            return f"整体 {formatted}" if locale == "zh" else f"{formatted} for the whole company"
        return f"每股 {formatted}" if locale == "zh" else f"{formatted} a share"
    # Legacy packages carry only the English text.
    if locale == "zh" and validated.get("buy_price"):
        return _legacy_buy_price_zh(validated["buy_price"])
    return validated.get("buy_price") or None


def decision_rows(validated: dict[str, Any], locale: str) -> list[tuple[str, str]]:
    fields = validated["fields"]
    label = call_label(validated["decision"], validated.get("pass_kind"), fields)[locale]
    rows: list[tuple[str, str]] = []
    zh = locale == "zh"
    rows.append(("结论" if zh else "Call", label))
    buy = _buy_price_display(validated, locale)
    if buy:
        rows.append(("买入价" if zh else "Buy price", buy))
    price = fields.get("price")
    if price is not None:
        text = format_money(price, fields.get("currency"), locale)
        if fields.get("price_date"):
            text += f"（{fields['price_date']}）" if zh else f" ({fields['price_date']})"
        rows.append(("股价与日期" if zh else "Price & date", text))
    low = _value_text(fields, "value_low", locale)
    high = _value_text(fields, "value_high", locale)
    central = _value_text(fields, "value_central", locale)
    if low and high:
        text = f"{low} – {high}"
        if central:
            text += f"（中值 {central}）" if zh else f" (central {central})"
        rows.append(("价值区间" if zh else "Value range", text))
    elif central:
        rows.append(("价值区间" if zh else "Value range", f"中值 {central}" if zh else f"central {central}"))
    mos = fields.get("mos_pct")
    required = fields.get("required_mos_pct")
    pieces = []
    if mos is not None:
        pieces.append(
            f"当前价格下为 {format_pct(mos)}" if zh else f"{format_pct(mos)} at today's price"
        )
    if required is not None:
        pieces.append(f"要求 {format_pct(required)}" if zh else f"{format_pct(required)} required")
    if pieces:
        rows.append(("安全边际" if zh else "Margin of safety", ("；" if zh else "; ").join(pieces)))
    return rows


# ---- the arithmetic table ----------------------------------------------------------------------


def owner_earnings_per_share(fields: dict[str, Any]) -> float | None:
    if fields.get("owner_earnings_per_share") is not None:
        return fields["owner_earnings_per_share"]
    owner = fields.get("owner_earnings")
    shares = fields.get("diluted_shares")
    if owner is not None and shares:
        return owner / shares
    return None


def arithmetic_rows(fields: dict[str, Any], locale: str) -> list[tuple[str, str]]:
    """Rows of "The arithmetic" table, built only from the structured
    fields. Empty when the package carries too few of them to be worth a
    table (legacy packages carry none)."""
    zh = locale == "zh"
    currency = fields.get("currency")
    rows: list[tuple[str, str]] = []

    def total(key: str, en: str, cn: str) -> None:
        if fields.get(key) is not None:
            rows.append((cn if zh else en, format_money(fields[key], currency, locale, millions=True)))

    total("earnings", "Normalized earnings (excl. non-operating gains)", "正常化净利润（剔除非经营性收益）")
    total("d_and_a", "+ Depreciation and amortization", "加：折旧与摊销")
    total("maintenance_capex", "− Maintenance capex", "减：维持性资本开支")
    total("working_capital", "± Working capital", "加减：营运资本变动")
    total("owner_earnings", "= Owner's earnings", "= 股东盈余")
    if fields.get("diluted_shares") is not None:
        rows.append(("稀释后股本" if zh else "Diluted shares", _format_shares(fields["diluted_shares"], locale)))
    per_share = owner_earnings_per_share(fields)
    if per_share is not None and fields.get("value_basis") != "company":
        rows.append(
            ("每股股东盈余" if zh else "Owner's earnings per share", format_money(per_share, currency, locale))
        )
    hurdle = fields.get("hurdle")
    if hurdle is not None:
        text = format_pct(hurdle)
        if fields.get("ust10y") is not None:
            ust = format_pct(fields["ust10y"])
            date = fields.get("ust10y_date")
            if zh:
                text += f"（10 年期美债收益率 {ust}" + (f"，{date}" if date else "") + "）"
            else:
                text += f" (10-year UST {ust}" + (f" on {date}" if date else "") + ")"
        rows.append(
            (
                "门槛收益率 r = max(10 年期美债收益率 + 3%, 10%)"
                if zh
                else "Hurdle r = max(10-year UST + 3%, 10%)",
                text,
            )
        )
    if fields.get("g") is not None:
        rows.append(("长期增长率 g" if zh else "Long-run growth g", format_pct(fields["g"])))
    if fields.get("multiple") is not None:
        multiple = _per_share_text(fields["multiple"])
        rows.append(("股东盈余倍数" if zh else "Multiple of owner's earnings", f"{multiple} 倍" if zh else f"{multiple}×"))
    for item in fields.get("adjustments") or []:
        label = (item.get("label_zh") or item["label"]) if zh else item["label"]
        amount = format_money(item["per_share"], currency, locale)
        if item["per_share"] > 0:
            amount = "+" + amount
        rows.append((f"调整项：{label}" if zh else f"Adjustment: {label}", f"每股 {amount}" if zh else f"{amount} a share"))
    values = [
        _value_text(fields, key, locale) for key in ("value_low", "value_central", "value_high")
    ]
    if any(values):
        rows.append(
            (
                "内在价值（低 / 中 / 高）" if zh else "Intrinsic value (low / central / high)",
                " / ".join(value or "—" for value in values),
            )
        )
    if fields.get("required_mos_pct") is not None:
        rows.append(("要求的安全边际" if zh else "Required margin of safety", format_pct(fields["required_mos_pct"])))
    buy = _value_text(fields, "buy_price_value", locale)
    if buy:
        rows.append(
            (
                "买入价 = 中值 × (1 − 要求的安全边际)" if zh else "Buy price = central × (1 − required)",
                buy,
            )
        )
    if fields.get("price") is not None:
        text = format_money(fields["price"], currency, locale)
        if fields.get("price_date"):
            text += f"（{fields['price_date']}）" if zh else f" ({fields['price_date']})"
        rows.append(("股价与日期" if zh else "Price & date", text))
    if fields.get("mos_pct") is not None:
        rows.append(("当前价格下的安全边际" if zh else "Margin of safety at today's price", format_pct(fields["mos_pct"])))
    core = {"owner_earnings", "multiple", "value_central", "value_low", "buy_price_value", "hurdle"}
    if len(rows) < 3 or not core & set(fields):
        return []
    return rows


def _table_markdown(rows: list[tuple[str, str]], header: tuple[str, str]) -> str:
    def cell(text: str) -> str:
        return str(text).replace("|", "/").replace("\n", " ")

    lines = [f"| {cell(header[0])} | {cell(header[1])} |", "|---|---|"]
    lines.extend(f"| {cell(label)} | {cell(value)} |" for label, value in rows)
    return "\n".join(lines)


def _insert_before_heading(markdown: str, heading: str, block: str) -> str:
    lines = markdown.splitlines()
    for index, line in enumerate(lines):
        if line.startswith(heading):
            return "\n".join(lines[:index] + [block.rstrip(), ""] + lines[index:])
    return markdown.rstrip() + "\n\n" + block.rstrip()


_TITLE_EDGAR_SUFFIX_RE = re.compile(r"(?:\s*/\s*[A-Za-z]{2,4}\s*/?)+\s*$")


def _clean_title_line(markdown: str) -> str:
    """Drop an EDGAR state token (" /De/") from the end of the ``#`` title
    — the registry name leaked it into titles before names were cleaned at
    the source. Only the title line is touched."""
    lines = markdown.splitlines()
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        if line.startswith("# "):
            lines[index] = _TITLE_EDGAR_SUFFIX_RE.sub("", line).rstrip()
        break
    return "\n".join(lines)


def _render_markdown(validated: dict[str, Any], sources: list[dict[str, Any]], locale: str) -> str:
    """The text the Word file is rendered from: the memo as written, plus
    the renderer-owned arithmetic table (end of section VIII) and Sources
    list (after section X)."""
    zh = locale == "zh"
    markdown = _clean_title_line(validated["markdown_zh" if zh else "markdown_en"])
    rows = arithmetic_rows(validated["fields"], locale)
    if rows:
        heading = "### 估值算术" if zh else "### The arithmetic"
        table = _table_markdown(rows, ("步骤", "数值") if zh else ("Step", "Figure"))
        markdown = _insert_before_heading(
            markdown,
            REQUIRED_HEADINGS_ZH[8] if zh else REQUIRED_HEADINGS_EN[8],
            f"{heading}\n\n{table}\n",
        )
    if sources:
        lines = ["## 资料来源" if zh else "## Sources", ""]
        for source in sources:
            entry = f"[{source['n']}] {source['title']}"
            if source.get("url") and source["url"] != source["title"]:
                entry += f" — {source['url']}"
            if source.get("accessed"):
                entry += f"（访问于 {source['accessed']}）" if zh else f" (accessed {source['accessed']})"
            lines.extend([entry, ""])
        markdown = markdown.rstrip() + "\n\n" + "\n".join(lines)
    return markdown


# ---- sources ----------------------------------------------------------------------------


def _tokens(text: Any) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9一-鿿]{3,}", str(text or "").lower())}


def fill_source_urls(sources: list[dict[str, Any]], run_dir: Path | str | None) -> list[str]:
    """Give sources without a URL the URL of the page this run fetched
    under a matching title (``sources/manifest.jsonl``), like
    ``memo_fact_check.attach_source_urls`` does for late-stage memos. Only
    a strong match attaches; returns one note per attachment."""
    if run_dir is None:
        return []
    manifest = Path(run_dir) / "sources" / "manifest.jsonl"
    rows: list[dict[str, Any]] = []
    try:
        for line in manifest.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict) and str(row.get("url") or "").startswith("http"):
                rows.append(row)
    except OSError:
        return []
    notes: list[str] = []
    for source in sources:
        if source.get("url"):
            continue
        query = _tokens(source.get("title"))
        if len(query) < 2:
            continue
        best: tuple[float, dict[str, Any]] | None = None
        for row in rows:
            tokens = _tokens(row.get("title")) | _tokens(
                re.sub(r"[/._-]+", " ", str(row.get("url")).split("://", 1)[-1])
            )
            if not tokens:
                continue
            score = len(query & tokens) / len(query)
            if score >= 0.6 and (best is None or score > best[0]):
                best = (score, row)
        if best is None:
            continue
        source["url"] = str(best[1]["url"])
        if not source.get("accessed"):
            source["accessed"] = _date(best[1].get("at"))
        notes.append(f"[{source['n']}] ← {source['url']} (score {best[0]:.2f})")
    return notes


# ---- review stamp and dates ------------------------------------------------------------------


def review_stamp(review: Any) -> dict[str, str]:
    """``{"state", "en", "zh", "color"}`` for the header stamp."""
    review = review if isinstance(review, dict) else {}
    state = str(review.get("state") or "draft").strip().lower()
    if state == "approved":
        date = _date(review.get("reviewed_at")) or ""
        name = _text(review.get("reviewer"))
        template = REVIEWED_STAMP if name else REVIEWED_STAMP_NO_NAME
        return {
            "state": "approved",
            "en": template["en"].format(name=name, date=date).rstrip(", "),
            "zh": template["zh"].format(name=name, date=date).rstrip("，"),
            "color": STAMP_COLOR["approved"],
        }
    if state == "withdrawn":
        return {"state": "withdrawn", **REVIEW_STAMP["withdrawn"], "color": STAMP_COLOR["withdrawn"]}
    return {"state": "draft", **REVIEW_STAMP["draft"], "color": STAMP_COLOR["draft"]}


def _run_date(package: dict[str, Any], run_dir: Path | str | None) -> str:
    run = package.get("run") if isinstance(package.get("run"), dict) else {}
    for candidate in (run.get("as_of"), run.get("run_id")):
        parsed = _date(candidate)
        if parsed:
            return parsed
    if run_dir is not None:
        parsed = _date(Path(run_dir).name)
        if parsed:
            return parsed
    return datetime.now(timezone.utc).date().isoformat()


# ---- valuation arithmetic check -------------------------------------------------------------

_VALUE_TOLERANCE = 0.05


def _close(a: float, b: float, tolerance: float = _VALUE_TOLERANCE) -> bool:
    scale = max(abs(a), abs(b))
    if scale == 0:
        return True
    return abs(a - b) / scale <= tolerance


def _finding(code: str, snippet: str, suggestion: str, *, severity: str = "P1") -> dict[str, str]:
    return {
        "severity": severity,
        "code": code,
        "location": "valuation",
        "snippet": snippet,
        "suggestion": suggestion,
    }


def _section_values(markdown_en: str) -> dict[str, list[float]]:
    """Figures section VIII states, by class, for the "appears in §VIII"
    check (per-share amounts, scaled totals, percentages)."""
    from . import memo_fact_check

    body = section_body(markdown_en, REQUIRED_HEADINGS_EN[7])
    values: dict[str, list[float]] = {"amount": [], "pct": [], "mult": []}
    for figure in memo_fact_check.extract_figures(re.sub(r"\[\d{1,3}\]", "   ", body)):
        values.setdefault(figure.klass, []).append(figure.value)
    for match in re.finditer(r"(\d+(?:\.\d+)?)\s*(?:times|x\b|×)", body):
        values["mult"].append(float(match.group(1)))
    return values


def check_valuation(package: dict[str, Any]) -> list[dict[str, str]]:
    """Deterministic reconciliation of the structured valuation fields —
    warnings only (P1), never a render failure. Silent when the fields are
    absent (legacy packages).

    - owner's earnings ≈ earnings + D&A − maintenance capex ± working capital (±5%)
    - value ≈ owner's earnings per share × multiple + listed adjustments (±5%)
    - buy price ≤ central × (1 − required MoS), or ≤ value_low without a required MoS
    - Buy ⇒ price ≤ buy price; a price-conditional Pass carries a buy price
    - MoS = (central − price) ÷ central; hurdle = max(10-year UST + 3%, 10%); g ≤ ~4%
    - each headline figure appears in section VIII
    """
    fields = structured_fields(package)
    findings: list[dict[str, str]] = []
    decision = str(package.get("decision") or "").strip()
    company = fields.get("value_basis") == "company"

    earnings = fields.get("earnings")
    d_and_a = fields.get("d_and_a")
    capex = fields.get("maintenance_capex")
    owner = fields.get("owner_earnings")
    if None not in (earnings, d_and_a, capex, owner):
        expected = earnings + d_and_a - capex + (fields.get("working_capital") or 0.0)
        if not _close(owner, expected):
            findings.append(
                _finding(
                    "owner_earnings_mismatch",
                    f"owner_earnings {owner:,.0f} vs earnings + D&A − maintenance capex ± working capital = {expected:,.0f}",
                    "Owner's earnings = normalized earnings + D&A − maintenance capex ± working capital; "
                    "reconcile the figure or the inputs.",
                )
            )
    elif owner is not None and earnings is not None and capex is not None and d_and_a is None:
        if _close(owner, earnings - capex, 0.01) and not _close(earnings - capex, earnings, 0.01):
            findings.append(
                _finding(
                    "owner_earnings_no_d_and_a",
                    f"owner_earnings {owner:,.0f} = earnings − maintenance capex, with no D&A added back",
                    "Add depreciation and amortization back before subtracting maintenance capex.",
                )
            )

    per_share = owner_earnings_per_share(fields)
    multiple = fields.get("multiple")
    central = fields.get("value_central")
    if central is None and fields.get("value_low") is not None and fields.get("value_high") is not None:
        central = (fields["value_low"] + fields["value_high"]) / 2
    if per_share is not None and multiple is not None and central is not None and not company:
        adjustments = sum(item["per_share"] for item in fields.get("adjustments") or [])
        expected = per_share * multiple + adjustments
        if not _close(central, expected):
            findings.append(
                _finding(
                    "intrinsic_value_mismatch",
                    f"central value {central:,.2f} vs owner's earnings per share {per_share:,.2f} × "
                    f"{multiple:g} + adjustments {adjustments:,.2f} = {expected:,.2f}",
                    "The central value should equal the per-share owner's earnings times the multiple, "
                    "plus the listed adjustments.",
                )
            )

    low = fields.get("value_low")
    high = fields.get("value_high")
    if low is not None and high is not None and low > high:
        findings.append(
            _finding("value_range_inverted", f"value_low {low:g} > value_high {high:g}", "Order the range low → high.")
        )

    buy = fields.get("buy_price_value")
    required = fields.get("required_mos_pct")
    if buy is not None:
        if central is not None and required is not None:
            ceiling = central * (1 - required / 100)
            if buy > ceiling * 1.01:
                findings.append(
                    _finding(
                        "buy_price_above_mos_rule",
                        f"buy price {buy:,.2f} > central {central:,.2f} × (1 − {required:g}%) = {ceiling:,.2f}",
                        "Buy price = central value × (1 − required margin of safety).",
                    )
                )
        elif low is not None and buy > low * 1.01:
            findings.append(
                _finding(
                    "buy_price_above_value_low",
                    f"buy price {buy:,.2f} > value_low {low:,.2f} with no required margin of safety stated",
                    "State the required margin of safety, or buy at or below the low end of the range.",
                )
            )

    price = fields.get("price")
    if decision == "Buy" and price is not None and buy is not None and price > buy * 1.005:
        findings.append(
            _finding(
                "buy_above_buy_price",
                f"Buy at {price:,.2f} but the buy price is {buy:,.2f}",
                "A Buy needs today's price at or below the buy price; otherwise the call is a Pass at today's price.",
            )
        )
    if decision == "Pass" and fields.get("pass_kind") == "price" and buy is None and not str(package.get("buy_price") or "").strip():
        findings.append(
            _finding(
                "pass_without_buy_price",
                "pass_kind 'price' with no buy price",
                "A Pass at today's price must state the price at which it becomes a Buy.",
            )
        )

    mos = fields.get("mos_pct")
    if mos is not None and price is not None and central and not company:
        expected_mos = (central - price) / central * 100
        if abs(expected_mos - mos) > 1.5:
            findings.append(
                _finding(
                    "mos_mismatch",
                    f"mos_pct {mos:g} vs (central − price) ÷ central = {expected_mos:.1f}",
                    "Margin of safety = (central value − price) ÷ central value.",
                )
            )
    hurdle = fields.get("hurdle")
    ust = fields.get("ust10y")
    if hurdle is not None and ust is not None:
        expected_hurdle = max(ust + 3.0, 10.0)
        if abs(expected_hurdle - hurdle) > 0.26:
            findings.append(
                _finding(
                    "hurdle_mismatch",
                    f"hurdle {hurdle:g}% vs max(10-year UST {ust:g}% + 3%, 10%) = {expected_hurdle:.2f}%",
                    "Hurdle r = max(10-year UST + 3 points, 10%).",
                )
            )
    g = fields.get("g")
    if g is not None and g > 4.5:
        findings.append(
            _finding(
                "long_run_growth_above_cap",
                f"g = {g:g}% (house cap about 4%)",
                "Keep long-run g at or below about 4%; price faster near-term growth as N years of above-trend growth.",
            )
        )

    # Each headline figure should be visible where the valuation is argued.
    markdown_en = str(package.get("markdown_en") or "")
    stated: dict[str, list[float]] | None = None
    if markdown_en and any(key in fields for key in ("price", "value_central", "buy_price_value", "hurdle")):
        try:
            stated = _section_values(markdown_en)
        except Exception:  # noqa: BLE001 — a check must never sink a render
            stated = None
    if stated is not None:
        scale = 1_000_000 if company else 1
        checks = [
            ("price", fields.get("price"), "amount", 1),
            ("value_low", low, "amount", scale),
            ("value_central", fields.get("value_central"), "amount", scale),
            ("value_high", high, "amount", scale),
            ("buy_price_value", buy, "amount", scale),
            ("hurdle", hurdle, "pct", 1),
            ("required_mos_pct", required, "pct", 1),
        ]
        missing = []
        for key, value, klass, factor in checks:
            if value is None:
                continue
            target = value * factor
            if not any(_close(target, found, 0.01) for found in stated.get(klass, [])):
                missing.append(f"{key}={value:g}")
        if missing:
            findings.append(
                _finding(
                    "valuation_figure_not_in_section_viii",
                    "not stated in §VIII: " + ", ".join(missing),
                    "Every figure the valuation uses (price, range, buy price, hurdle, required margin of "
                    "safety) should appear in section VIII.",
                    severity="P2",
                )
            )
    return findings


# ---- render ------------------------------------------------------------------------------------


def render_package(
    package: dict[str, Any],
    *,
    run_dir: Path | str,
    memo_paths: dict[str, Path | str],
    review: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate, write Markdown working copies, and render both DOCX files.

    A pure re-render of a stored package: ``render_package(load_package(
    run_dir), run_dir=run_dir, memo_paths={"en": …, "zh": …})`` reproduces
    the documents with today's frame. ``review`` (``{state, reviewer,
    reviewed_at}``) overrides ``package["run"]["review"]`` for the header
    stamp; neither present means the DRAFT stamp.
    """
    validated = validate_package(package)
    root = Path(run_dir)
    memo_dir = root / "memo"
    memo_dir.mkdir(parents=True, exist_ok=True)
    en_md = memo_dir / "buffett_memo.en.md"
    zh_md = memo_dir / "buffett_memo.zh.md"
    en_md.write_text(validated["markdown_en"] + "\n", encoding="utf-8")
    zh_md.write_text(validated["markdown_zh"] + "\n", encoding="utf-8")

    sources = [dict(source) for source in validated["sources"]]
    source_notes = fill_source_urls(sources, root)

    run = package.get("run") if isinstance(package.get("run"), dict) else {}
    stamp = review_stamp(review if review is not None else run.get("review"))
    run_date = _run_date(package, root)
    name_en = (
        clean_display_name(_title_company(validated["markdown_en"]))
        or validated["company_name"]
        or "Company"
    )
    name_zh = (
        clean_display_name(validated.get("company_name_zh"))
        or clean_display_name(_title_company(validated["markdown_zh"]))
        or name_en
    )
    names = {"en": name_en, "zh": name_zh}

    en_docx = Path(memo_paths["en"])
    zh_docx = Path(memo_paths["zh"])
    try:
        for locale, md_path, docx_path in (("en", en_md, en_docx), ("zh", zh_md, zh_docx)):
            render_internal_memo(
                md_path,
                docx_path,
                markdown_text=_render_markdown(validated, sources, locale),
                locale=locale,
                header_text=HEADER_TEMPLATE[locale].format(company=names[locale]),
                stamp_text=stamp[locale],
                stamp_color=stamp["color"],
                footer_label=f"{CONFIDENTIAL[locale]} · {run_date} · {LANGUAGE_TAG[locale]}",
                footer_note=DISCLAIMER[locale],
                doc_title=DOC_TITLE_TEMPLATE[locale].format(company=names[locale]),
                doc_subject=DOC_SUBJECT[locale],
                author=DOC_AUTHOR,
                created=run_date,
                decision_rows=decision_rows(validated, locale),
            )
    except InternalMemoRenderError as exc:
        raise BuffettMemoPackageError(str(exc)) from exc

    fields = validated["fields"]
    return {
        "ok": True,
        "renderer_version": RENDERER_VERSION,
        "decision": validated["decision"],
        "pass_kind": validated["pass_kind"],
        "buy_price": validated["buy_price"],
        "buy_price_zh": validated.get("buy_price_zh"),
        "call_label": call_label(validated["decision"], validated["pass_kind"], fields),
        "fields": fields,
        "sources": sources,
        "source_url_notes": source_notes,
        "company_name": name_en,
        "company_name_zh": name_zh,
        "run_date": run_date,
        "review_stamp": {"state": stamp["state"], "en": stamp["en"], "zh": stamp["zh"]},
        "markdown_en": str(en_md),
        "markdown_zh": str(zh_md),
        "docx_en": str(en_docx),
        "docx_zh": str(zh_docx),
        "content_en": preview_text(validated["markdown_en"]),
        "content_zh": preview_text(validated["markdown_zh"]),
    }


def report_fields(rendered: dict[str, Any]) -> dict[str, Any]:
    """The report-record fields a render produces: the call, the buy price
    (text), the kind of Pass, a reader-facing call label and the optional
    valuation figures. Shared by the pipeline's finalize step and any
    re-render script."""
    fields = rendered.get("fields") or {}
    valuation = {key: fields[key] for key in RECORD_VALUATION_FIELDS if key in fields}
    return {
        "decision": rendered.get("decision"),
        "buy_price": rendered.get("buy_price") or None,
        "buy_price_zh": rendered.get("buy_price_zh") or None,
        "pass_kind": rendered.get("pass_kind"),
        "call_label": rendered.get("call_label"),
        "buffett_valuation": valuation or None,
    }
