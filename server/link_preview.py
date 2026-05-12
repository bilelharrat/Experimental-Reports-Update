"""Fetch a URL and produce a quick preview (title, description, image,
favicon) plus extract the readable text for downstream AI analysis.

This is intentionally simple: a single httpx GET with a real-browser UA, then
BeautifulSoup to pull metadata and reading text. JS-heavy SPAs won't render
fully, but blog posts, news articles, press releases, and most static
content come through cleanly.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}
FETCH_TIMEOUT = 15.0
MAX_BYTES = 8 * 1024 * 1024  # 8MB cap so we don't pull huge pages
MAX_TEXT_CHARS = 60_000  # cap text we send to the model


@dataclass
class LinkPreview:
    url: str
    final_url: str
    title: str | None = None
    description: str | None = None
    site_name: str | None = None
    image: str | None = None
    favicon: str | None = None
    domain: str | None = None
    html: str = ""
    text: str = ""
    error: str | None = None
    fields_visible: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "final_url": self.final_url,
            "title": self.title,
            "description": self.description,
            "site_name": self.site_name,
            "image": self.image,
            "favicon": self.favicon,
            "domain": self.domain,
            "error": self.error,
        }


def _meta(soup: BeautifulSoup, name: str) -> str | None:
    """Get a meta tag value by name or property."""
    el = soup.find("meta", attrs={"property": name}) or soup.find(
        "meta", attrs={"name": name}
    )
    if el and el.get("content"):
        return el["content"].strip() or None
    return None


def _extract_text(soup: BeautifulSoup) -> str:
    """Best-effort readable text. Drops scripts/styles/nav/footer."""
    for tag in soup(["script", "style", "noscript", "template"]):
        tag.decompose()
    # Prefer article > main > body
    candidate = soup.find("article") or soup.find("main") or soup.body or soup
    text = candidate.get_text(separator="\n", strip=True)
    # Collapse runs of blank lines
    lines = [ln for ln in (l.strip() for l in text.splitlines()) if ln]
    return "\n".join(lines)[:MAX_TEXT_CHARS]


def extract_text_from_html(html: str) -> str:
    """Extract readable text from an HTML string."""
    return _extract_text(BeautifulSoup(html or "", "html.parser"))


def fetch(url: str) -> LinkPreview:
    """Fetch a URL and return a populated LinkPreview. Never raises."""
    preview = LinkPreview(url=url, final_url=url)
    try:
        with httpx.Client(
            timeout=FETCH_TIMEOUT,
            headers=HEADERS,
            follow_redirects=True,
            max_redirects=5,
        ) as client:
            r = client.get(url)
            r.raise_for_status()
            preview.final_url = str(r.url)
            preview.domain = urlparse(preview.final_url).hostname or None
            ctype = r.headers.get("content-type", "")
            if "html" not in ctype.lower():
                preview.error = f"Unsupported content type: {ctype}"
                return preview
            content = r.content[:MAX_BYTES]
            try:
                html = content.decode(r.encoding or "utf-8", errors="replace")
            except Exception:
                html = content.decode("utf-8", errors="replace")
            preview.html = html
    except httpx.HTTPStatusError as exc:
        preview.error = f"HTTP {exc.response.status_code}"
        return preview
    except Exception as exc:  # noqa: BLE001 — surface anything network-y
        preview.error = f"Fetch failed: {exc}"
        return preview

    soup = BeautifulSoup(preview.html, "html.parser")
    preview.title = (
        _meta(soup, "og:title")
        or _meta(soup, "twitter:title")
        or (soup.title.string.strip() if soup.title and soup.title.string else None)
    )
    preview.description = (
        _meta(soup, "og:description")
        or _meta(soup, "twitter:description")
        or _meta(soup, "description")
    )
    preview.site_name = _meta(soup, "og:site_name")
    img = _meta(soup, "og:image") or _meta(soup, "twitter:image")
    if img:
        preview.image = urljoin(preview.final_url, img)

    icon = soup.find("link", rel=lambda v: v and "icon" in v.lower())
    if icon and icon.get("href"):
        preview.favicon = urljoin(preview.final_url, icon["href"])
    elif preview.domain:
        preview.favicon = f"https://www.google.com/s2/favicons?domain={preview.domain}&sz=128"

    preview.text = _extract_text(soup)
    return preview
