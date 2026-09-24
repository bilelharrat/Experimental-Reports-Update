"""Source reliability tiers and honest source dates — pure helpers.

No I/O and no network: callers pass what they already hold. The memo
renderer uses these to print a tier letter and one stacked date cell per
source in the Sources appendix, to mark a key metric that rests only on
tier-C sources, and to derive an evidence cutoff when a package carries
none. A later pipeline step passes ``fetched_at`` from the source cache.

Tiers are computed from the URL's host, never assigned by a model:

    A   regulators, filings, courts and exchanges (sec.gov, court records,
        exchange disclosure sites, government registries)
    A-  the company's own domain (its site, newsroom or investor pages)
    B   named tier-1 press and data vendors (Reuters, Bloomberg, FT, WSJ,
        CNBC, The Information, PitchBook, Sacra, ...) and other recognised
        news hosts
    C   everything else: unknown blogs, Medium/Substack posts, SEO
        aggregators, social posts

Dates accept the forms a source can honestly carry — ``YYYY``,
``YYYY-MM``, ``YYYY-MM-DD`` — or the literal ``"undated"``.
"""
from __future__ import annotations

import datetime as _dt
import re
from typing import Any, Iterable
from urllib.parse import urlsplit

TIER_A = "A"
TIER_A_MINUS = "A-"
TIER_B = "B"
TIER_C = "C"
TIERS = (TIER_A, TIER_A_MINUS, TIER_B, TIER_C)

UNDATED = "undated"

# One line a reader needs to decode the letter, in both memo languages.
TIER_LEGEND = {
    "en": (
        "Tier: A = regulator, filing, court or exchange · A- = the company's "
        "own site · B = established press or data vendor · C = blog, "
        "aggregator or other unverified page · — = no public link"
    ),
    "zh": (
        "来源等级：A = 监管机构、申报文件、法院或交易所 · A- = 公司自有网站 · "
        "B = 主流媒体或数据服务商 · C = 博客、聚合站点或其他未经核实的网页 · "
        "— = 无公开链接"
    ),
}

# ---- tier map ----------------------------------------------------------------

# Hosts whose content is the record itself: regulators, filings, courts,
# exchanges and official registries. Matched on the host or any subdomain.
_TIER_A_DOMAINS = frozenset(
    {
        # US regulators, filings and official data
        "sec.gov",
        "federalregister.gov",
        "regulations.gov",
        "govinfo.gov",
        "congress.gov",
        "uspto.gov",
        "ftc.gov",
        "fcc.gov",
        "fda.gov",
        "justice.gov",
        "finra.org",
        "federalreserve.gov",
        # courts and court records
        "uscourts.gov",
        "supremecourt.gov",
        "courtlistener.com",
        "law.justia.com",
        "dockets.justia.com",
        # exchanges and listing disclosure sites
        "nyse.com",
        "listingcenter.nasdaq.com",
        "nasdaqtrader.com",
        "londonstockexchange.com",
        "euronext.com",
        "deutsche-boerse.com",
        "six-group.com",
        "hkexnews.hk",
        "hkex.com.hk",
        "sse.com.cn",
        "szse.cn",
        "bse.cn",
        "cninfo.com.cn",
        "jpx.co.jp",
        "sgx.com",
        "asx.com.au",
        "tmx.com",
        "sedarplus.ca",
        "twse.com.tw",
        "dart.fss.or.kr",
        "nseindia.com",
        "bseindia.com",
        # non-US regulators and registries
        "europa.eu",
        "fca.org.uk",
        "bafin.de",
        "amf-france.org",
        "consob.it",
        "finma.ch",
        "sfc.hk",
        "csrc.gov.cn",
        "gsxt.gov.cn",
        # intergovernmental agencies and their official statistics
        "iea.org",
        "imf.org",
        "worldbank.org",
        "oecd.org",
        "bis.org",
        "wto.org",
    }
)

# Government hosts by suffix: *.gov, *.gov.uk, *.gov.cn, *.go.jp, *.gouv.fr ...
_TIER_A_HOST_RE = re.compile(
    r"(?:^|\.)(?:gov|mil)(?:\.[a-z]{2})?$"
    r"|(?:^|\.)(?:gouv|gob|go|gc|gv|admin|bund)\.[a-z]{2}$"
)

# Named tier-1 press, wires and data vendors, plus other recognised news
# hosts (R21: a recognised news host defaults to B, not C).
_TIER_B_DOMAINS = frozenset(
    {
        # the named tier-1 set
        "reuters.com",
        "bloomberg.com",
        "ft.com",
        "wsj.com",
        "cnbc.com",
        "theinformation.com",
        "pitchbook.com",
        "sacra.com",
        # data vendors and research houses
        "crunchbase.com",
        "cbinsights.com",
        "tracxn.com",
        "dealroom.co",
        "preqin.com",
        "mergermarket.com",
        "ionanalytics.com",
        "spglobal.com",
        "morningstar.com",
        "moodys.com",
        "fitchratings.com",
        "gartner.com",
        "idc.com",
        "forrester.com",
        "statista.com",
        "semianalysis.com",
        "woodmac.com",
        "rystadenergy.com",
        "bnef.com",
        "mckinsey.com",
        "bcg.com",
        # wires
        "apnews.com",
        "businesswire.com",
        "prnewswire.com",
        "globenewswire.com",
        # general and business press
        "nytimes.com",
        "washingtonpost.com",
        "economist.com",
        "axios.com",
        "politico.com",
        "semafor.com",
        "bbc.com",
        "bbc.co.uk",
        "cnn.com",
        "theguardian.com",
        "latimes.com",
        "barrons.com",
        "marketwatch.com",
        "fortune.com",
        "forbes.com",
        "businessinsider.com",
        "fastcompany.com",
        "qz.com",
        "thestreet.com",
        "finance.yahoo.com",
        "nasdaq.com",
        "nikkei.com",
        "scmp.com",
        "caixin.com",
        "caixinglobal.com",
        "yicai.com",
        "jiemian.com",
        "thepaper.cn",
        "36kr.com",
        "handelsblatt.com",
        "lesechos.fr",
        "theglobeandmail.com",
        "afr.com",
        "straitstimes.com",
        "courthousenews.com",
        "law360.com",
        # technology and industry press
        "techcrunch.com",
        "theverge.com",
        "wired.com",
        "arstechnica.com",
        "venturebeat.com",
        "zdnet.com",
        "theregister.com",
        "siliconangle.com",
        "thenextweb.com",
        "datacenterdynamics.com",
        "lightreading.com",
        "fiercewireless.com",
        "eetimes.com",
        "digitimes.com",
    }
)

# Self-publishing and social hosts: C even when a subdomain looks official.
_TIER_C_PLATFORMS = frozenset(
    {
        "medium.com",
        "substack.com",
        "blogspot.com",
        "wordpress.com",
        "wixsite.com",
        "github.io",
        "linkedin.com",
        "reddit.com",
        "quora.com",
        "x.com",
        "twitter.com",
        "facebook.com",
        "youtube.com",
        "tiktok.com",
        "seekingalpha.com",
    }
)


def normalize_domain(value: Any) -> str:
    """The lowercase host of a URL or bare domain, without ``www.``/port.

    ``"https://www.CNBC.com/2026/08/17/x.html"`` -> ``"cnbc.com"``;
    ``"anthropic.com"`` -> ``"anthropic.com"``; junk -> ``""``.
    """
    text = str(value or "").strip()
    if not text:
        return ""
    if "://" not in text:
        text = "http://" + text.lstrip("/")
    try:
        host = urlsplit(text).hostname or ""
    except ValueError:
        return ""
    host = host.strip(".").lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def display_domain(url: Any) -> str:
    """The host to print under a linked source title (``cnbc.com``)."""
    host = normalize_domain(url)
    return host if "." in host else ""


def _host_in(host: str, domains: Iterable[str]) -> bool:
    return any(host == domain or host.endswith("." + domain) for domain in domains)


def tier_for_url(url: Any, company_domain: Any = None) -> str:
    """Reliability tier of a source URL: ``"A"``, ``"A-"``, ``"B"`` or ``"C"``.

    ``company_domain`` (a URL or bare domain) promotes the company's own
    pages to A-. Anything unrecognised is C.
    """
    host = normalize_domain(url)
    if not host or "." not in host:
        return TIER_C
    company = normalize_domain(company_domain)
    if company and "." in company and _host_in(host, (company,)):
        return TIER_A_MINUS
    if _host_in(host, _TIER_C_PLATFORMS):
        return TIER_C
    if _host_in(host, _TIER_A_DOMAINS) or _TIER_A_HOST_RE.search(host):
        return TIER_A
    if _host_in(host, _TIER_B_DOMAINS):
        return TIER_B
    return TIER_C


# ---- dates -------------------------------------------------------------------

# The date forms a source can carry, plus an ISO time tail
# ("2026-08-17T10:05:00Z"). Anything else — a range, a quarter, prose — is
# not a date this module will guess at.
_ISO_PARTIAL_RE = re.compile(
    r"^\s*(\d{4})(?:[-/.](\d{1,2})(?:[-/.](\d{1,2}))?)?"
    r"(?:[T ]\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?\s*$"
)
_LEADING_DATE_RE = re.compile(r"^\s*(\d{4}-\d{2}-\d{2})(?!\d)")
_MIN_YEAR = 1990
_MAX_YEAR = 2100


def parse_partial_date(value: Any) -> str | None:
    """Normalize ``YYYY`` / ``YYYY-MM`` / ``YYYY-MM-DD`` (also ``/`` or ``.``
    separators and an ISO datetime tail) to ``YYYY[-MM[-DD]]``; ``None``
    when the value is not one of those forms or is not a real date."""
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip()
    if not text:
        return None
    match = _ISO_PARTIAL_RE.match(text)
    if not match:
        return None
    year = int(match.group(1))
    if not _MIN_YEAR <= year <= _MAX_YEAR:
        return None
    if match.group(2) is None:
        return f"{year:04d}"
    month = int(match.group(2))
    if not 1 <= month <= 12:
        return None
    if match.group(3) is None:
        return f"{year:04d}-{month:02d}"
    day = int(match.group(3))
    try:
        _dt.date(year, month, day)
    except ValueError:
        return None
    return f"{year:04d}-{month:02d}-{day:02d}"


def _run_date(value: Any) -> str | None:
    """The date a run was written, from ``2026-09-01`` or a run id such as
    ``2026-09-01__185114``."""
    text = str(value or "").strip()
    match = _LEADING_DATE_RE.match(text)
    if match:
        return parse_partial_date(match.group(1))
    return parse_partial_date(text)


def _date_value(value: Any) -> str | None:
    """A date field as stored: normalized date, ``"undated"``, the raw text
    when it is some other non-empty form, or ``None`` when absent."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.lower() == UNDATED:
        return UNDATED
    return parse_partial_date(text) or text


def date_sort_key(value: str) -> tuple[int, int, int]:
    """Sort key for a normalized partial date; a bare year sorts before any
    month of that year (it says less, so it never wins "latest")."""
    parts = [int(part) for part in value.split("-")]
    while len(parts) < 3:
        parts.append(0)
    return parts[0], parts[1], parts[2]


# Slug dates: /2026/08/17/, /2026/08/, 2026-08-17, 20260817 and the
# -MMDDYY suffix some publishers use (-081326 = 13 Aug 2026).
_SLUG_YMD_PATH_RE = re.compile(r"/((?:19|20)\d{2})/(\d{1,2})/(\d{1,2})(?=/|$|[-_.])")
_SLUG_YM_PATH_RE = re.compile(r"/((?:19|20)\d{2})/(\d{1,2})(?=/)")
_SLUG_ISO_RE = re.compile(r"(?<!\d)((?:19|20)\d{2})-(\d{2})-(\d{2})(?!\d)")
_SLUG_COMPACT_RE = re.compile(r"(?<!\d)((?:19|20)\d{2})(\d{2})(\d{2})(?!\d)")
_SLUG_MDY_RE = re.compile(r"-(\d{2})(\d{2})(\d{2})(?=\.html?$|\.php$|/?$)")


def date_from_url(url: Any, *, not_after: Any = None) -> str | None:
    """The publication date a URL's path carries, if any.

    Only the path is read (never the host or query). A date must be real,
    fall in a plausible year range and not lie after ``not_after`` (the
    run date): a slug ID that happens to look like a date is rejected
    rather than trusted.
    """
    text = str(url or "").strip()
    if not text:
        return None
    try:
        path = urlsplit(text if "://" in text else "http://" + text).path or ""
    except ValueError:
        return None
    ceiling = _run_date(not_after)
    ceiling_year = int(ceiling[:4]) if ceiling else _MAX_YEAR
    lowest_year = 2000

    def _accept(year: int, month: int, day: int | None) -> str | None:
        if not lowest_year <= year <= ceiling_year:
            return None
        candidate = parse_partial_date(
            f"{year:04d}-{month:02d}" + (f"-{day:02d}" if day is not None else "")
        )
        if candidate is None:
            return None
        if ceiling and date_sort_key(candidate) > date_sort_key(ceiling):
            return None
        return candidate

    for pattern in (_SLUG_YMD_PATH_RE, _SLUG_ISO_RE, _SLUG_COMPACT_RE):
        for match in pattern.finditer(path):
            found = _accept(int(match.group(1)), int(match.group(2)), int(match.group(3)))
            if found:
                return found
    for match in _SLUG_YM_PATH_RE.finditer(path):
        found = _accept(int(match.group(1)), int(match.group(2)), None)
        if found:
            return found
    match = _SLUG_MDY_RE.search(path)
    if match:
        found = _accept(2000 + int(match.group(3)), int(match.group(1)), int(match.group(2)))
        if found:
            return found
    return None


# A source the firm holds itself — its registry, models, diligence, calls —
# whose date is the day the run read it, not a publication date.
_INTERNAL_SOURCE_RE = re.compile(
    r"\b(?:bsh|internal|registry|diligence|data ?room|memo studio|interviews?|"
    r"call notes?|reference calls?|proprietary|confidential|uploads?|"
    r"founder updates?|kpis?)\b",
    re.IGNORECASE,
)


def _text_of(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(str(item or "") for item in value.values())
    return str(value or "")


def is_internal_source(source: Any) -> bool:
    """Whether a package source is the firm's own material (registry entry,
    model, diligence file, call notes) rather than a published page."""
    if not isinstance(source, dict):
        return False
    haystack = " ".join(
        _text_of(source.get(key)) for key in ("class", "title", "type")
    )
    return bool(_INTERNAL_SOURCE_RE.search(haystack))


def normalize_source_dates(
    source: dict,
    run_date: Any,
    *,
    fetched_at: Any = None,
) -> dict:
    """A copy of ``source`` with honest optional date fields.

    Adds (only when known) ``published_at`` (``YYYY[-MM[-DD]]`` or
    ``"undated"``), ``data_period`` and ``retrieved_at``. ``as_of`` is a
    legacy alias of ``published_at`` and is left in place untouched.

    A web source dated the very day the run was written almost always
    means "dated when we read it", not "published that day": such a
    ``published_at`` becomes ``"undated"`` unless the URL's path carries a
    date, which then fills it. BSH's own material keeps its date. A date
    the path carries also fills a missing or undated ``published_at``.
    ``retrieved_at`` comes from ``fetched_at`` (the source cache) or the
    source's own field — never inferred.
    """
    out = dict(source) if isinstance(source, dict) else {}
    run = _run_date(run_date)
    published = _date_value(out.get("published_at"))
    if published is None:
        published = _date_value(out.get("as_of"))
    slug = date_from_url(out.get("url"), not_after=run)
    if published is None or published == UNDATED:
        if slug:
            published = slug
    elif run and published == run and not is_internal_source(out):
        published = slug or UNDATED
    if published is not None:
        out["published_at"] = published
    data_period = _date_value(out.get("data_period"))
    if data_period is not None:
        out["data_period"] = data_period
    retrieved = parse_partial_date(fetched_at) or parse_partial_date(
        out.get("retrieved_at")
    )
    if retrieved is not None:
        out["retrieved_at"] = retrieved
    else:
        out.pop("retrieved_at", None)
    return out


def evidence_cutoff(sources: Any, run_date: Any = None) -> str | None:
    """The latest publication or data-period date among the package's
    non-internal sources, never later than the run date — the evidence
    ceiling a memo can honestly claim when the model stated none."""
    run = _run_date(run_date)
    best: str | None = None
    for source in sources if isinstance(sources, list) else []:
        if not isinstance(source, dict) or is_internal_source(source):
            continue
        normalized = normalize_source_dates(source, run)
        for key in ("published_at", "data_period"):
            value = normalized.get(key)
            if not value or value == UNDATED or parse_partial_date(value) != value:
                continue
            if run and date_sort_key(value) > date_sort_key(run):
                continue
            if best is None or date_sort_key(value) > date_sort_key(best):
                best = value
    return best
