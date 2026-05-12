"""Durable local archives for submitted news HTML.

The first pass is intentionally static: save the fetched HTML, discover image
URLs embedded in tags and common SSR payload shapes, download those assets, and
rewrite the archive to local files. Diagnostics from that pass decide whether a
browser-rendered fallback is worth trying.
"""
from __future__ import annotations

import hashlib
import html as html_lib
import json
import logging
import mimetypes
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from . import external_store
from .link_preview import HEADERS, extract_text_from_html

logger = logging.getLogger(__name__)

URL_RE = re.compile(r"https?://[^\s\"'<>`\\)]+")
CSS_URL_RE = re.compile(r"url\(\s*(['\"]?)([^'\"\)]+)\1\s*\)", re.IGNORECASE)

IMAGE_EXTS = {
    ".apng",
    ".avif",
    ".gif",
    ".ico",
    ".jpeg",
    ".jpg",
    ".png",
    ".svg",
    ".webp",
}
IMAGE_URL_MARKERS = (
    "avatar",
    "imageview",
    "imageview2",
    "image",
    "picasso",
    "webp",
    "webpic",
)
URL_ATTRS = (
    "src",
    "href",
    "poster",
    "data-src",
    "data-original",
    "data-original-src",
    "data-lazy",
    "data-lazy-src",
    "data-bg",
    "data-background",
)
SRCSET_ATTRS = ("srcset", "data-srcset")

MAX_ARCHIVE_ASSETS = 180
MAX_ASSET_BYTES = 20 * 1024 * 1024
ASSET_TIMEOUT = httpx.Timeout(20.0, connect=10.0, read=20.0)


@dataclass
class NewsArchiveResult:
    path: Path
    asset_dir: Path
    url_map: dict[str, str] = field(default_factory=dict)
    diagnostics: dict = field(default_factory=dict)

    def public_url(self, original_url: str | None, item_id: str) -> str | None:
        if not original_url:
            return None
        local = self.url_map.get(_clean_url(original_url))
        if not local:
            return None
        return f"/api/external/news/{item_id}/{local}"


def archive_static_html(
    *,
    kind: str,
    item_id: str,
    html: str,
    page_url: str,
    source_url: str | None = None,
    strategy: str = "static_asset_archive",
) -> NewsArchiveResult:
    """Write archived HTML plus local image assets for one news item."""
    asset_dir = external_store.archive_asset_dir(kind, item_id)
    shutil.rmtree(asset_dir, ignore_errors=True)
    asset_dir.mkdir(parents=True, exist_ok=True)

    discovery = _discover_asset_urls(html, page_url)
    limited_urls = discovery["image_urls"][:MAX_ARCHIVE_ASSETS]
    downloaded, failures = _download_assets(
        limited_urls,
        asset_dir=asset_dir,
        page_url=page_url,
    )
    rewritten = _rewrite_urls(html, downloaded)
    rewritten = _disable_scripts(rewritten)
    archive_path = external_store.write_archive(kind, item_id, rewritten)

    text_chars = len(extract_text_from_html(rewritten))
    diagnostics = _diagnostics(
        html=html,
        rewritten=rewritten,
        strategy=strategy,
        page_url=page_url,
        source_url=source_url,
        discovery=discovery,
        downloaded=downloaded,
        failures=failures,
        text_chars=text_chars,
    )
    _write_manifest(asset_dir, diagnostics, downloaded, failures)
    return NewsArchiveResult(
        path=archive_path,
        asset_dir=asset_dir,
        url_map={url: f"assets/{filename}" for url, filename in downloaded.items()},
        diagnostics=diagnostics,
    )


def browser_fallback_reasons(diagnostics: dict) -> list[str]:
    """Return reasons that justify trying browser-rendered capture."""
    reasons: list[str] = []
    image_candidates = int(diagnostics.get("image_candidate_count") or 0)
    downloaded_images = int(diagnostics.get("downloaded_image_count") or 0)
    text_chars = int(diagnostics.get("archive_text_chars") or 0)
    script_count = int(diagnostics.get("script_tag_count") or 0)
    img_tag_count = int(diagnostics.get("img_tag_count") or 0)

    if image_candidates >= 3 and downloaded_images == 0:
        reasons.append("static_archive_downloaded_no_candidate_images")
    elif image_candidates >= 10 and downloaded_images / max(image_candidates, 1) < 0.5:
        reasons.append("static_archive_downloaded_less_than_half_candidate_images")

    if text_chars < 400 and script_count >= 5:
        reasons.append("static_archive_has_little_text_and_many_scripts")
    if img_tag_count == 0 and image_candidates == 0 and script_count >= 8:
        reasons.append("static_archive_looks_like_js_shell")
    return reasons


def _discover_asset_urls(html: str, page_url: str) -> dict:
    soup = BeautifulSoup(html or "", "html.parser")
    ordered: list[str] = []

    def add(raw: str | None, *, base: str = page_url) -> None:
        clean = _clean_url(raw, base=base)
        if clean and _is_imageish_url(clean) and clean not in ordered:
            ordered.append(clean)

    for tag in soup.find_all(True):
        for attr in URL_ATTRS:
            value = tag.get(attr)
            if isinstance(value, str):
                add(value)
        for attr in SRCSET_ATTRS:
            value = tag.get(attr)
            if isinstance(value, str):
                for url in _srcset_urls(value):
                    add(url)
        style = tag.get("style")
        if isinstance(style, str):
            for _, url in CSS_URL_RE.findall(style):
                add(url)

    for meta in soup.find_all("meta"):
        key = " ".join(
            str(meta.get(attr) or "").lower()
            for attr in ("name", "property", "itemprop")
        )
        if "image" in key or "thumbnail" in key:
            add(meta.get("content"))

    decoded = _decode_escaped_urls(html or "")
    for match in URL_RE.finditer(decoded):
        add(match.group(0))

    return {
        "image_urls": ordered,
        "image_candidate_count": len(ordered),
        "img_tag_count": len(soup.find_all("img")),
        "script_tag_count": len(soup.find_all("script")),
        "link_tag_count": len(soup.find_all("link")),
    }


def _download_assets(
    urls: list[str],
    *,
    asset_dir: Path,
    page_url: str,
) -> tuple[dict[str, str], dict[str, str]]:
    downloaded: dict[str, str] = {}
    failures: dict[str, str] = {}
    headers = {
        **HEADERS,
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        "Referer": page_url,
    }
    with httpx.Client(
        timeout=ASSET_TIMEOUT,
        headers=headers,
        follow_redirects=True,
        max_redirects=5,
    ) as client:
        for url in urls:
            try:
                response = client.get(url)
                response.raise_for_status()
                content = response.content[: MAX_ASSET_BYTES + 1]
                if len(content) > MAX_ASSET_BYTES:
                    failures[url] = "asset_too_large"
                    continue
                ctype = response.headers.get("content-type", "").split(";")[0].strip()
                if ctype and not (ctype.startswith("image/") or ctype in {"binary/octet-stream", "application/octet-stream"}):
                    failures[url] = f"not_image_content_type:{ctype}"
                    continue
                filename = _asset_filename(url, ctype, content)
                (asset_dir / filename).write_bytes(content)
                downloaded[url] = filename
            except Exception as exc:  # noqa: BLE001
                failures[url] = f"{type(exc).__name__}: {exc}"
    return downloaded, failures


def _rewrite_urls(html: str, downloaded: dict[str, str]) -> str:
    rewritten = html or ""
    for original, filename in sorted(downloaded.items(), key=lambda it: len(it[0]), reverse=True):
        local = f"assets/{filename}"
        for variant in _url_variants(original):
            rewritten = rewritten.replace(variant, local)
    return rewritten


def _disable_scripts(html: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    for script in soup.find_all("script"):
        if script.get("type"):
            script["data-original-type"] = script.get("type")
        script["type"] = "application/x-archived-script"
        script["data-archived-disabled"] = "true"
    for tag in soup.find_all(True):
        for attr in list(tag.attrs):
            if attr.lower().startswith("on"):
                del tag.attrs[attr]
    return str(soup)


def _diagnostics(
    *,
    html: str,
    rewritten: str,
    strategy: str,
    page_url: str,
    source_url: str | None,
    discovery: dict,
    downloaded: dict[str, str],
    failures: dict[str, str],
    text_chars: int,
) -> dict:
    diagnostics = {
        "archive_strategy": strategy,
        "source_url": source_url,
        "final_url": page_url,
        "html_bytes": len((html or "").encode("utf-8", errors="replace")),
        "archive_html_bytes": len((rewritten or "").encode("utf-8", errors="replace")),
        "archive_text_chars": text_chars,
        "image_candidate_count": discovery["image_candidate_count"],
        "downloaded_image_count": len(downloaded),
        "failed_image_count": len(failures),
        "img_tag_count": discovery["img_tag_count"],
        "script_tag_count": discovery["script_tag_count"],
        "link_tag_count": discovery["link_tag_count"],
        "asset_limit": MAX_ARCHIVE_ASSETS,
        "asset_limit_reached": discovery["image_candidate_count"] > MAX_ARCHIVE_ASSETS,
    }
    reasons = browser_fallback_reasons(diagnostics)
    diagnostics["browser_fallback_recommended"] = bool(reasons)
    diagnostics["browser_fallback_reasons"] = reasons
    return diagnostics


def _write_manifest(
    asset_dir: Path,
    diagnostics: dict,
    downloaded: dict[str, str],
    failures: dict[str, str],
) -> None:
    manifest = {
        "diagnostics": diagnostics,
        "downloaded": downloaded,
        "failures": failures,
    }
    (asset_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _srcset_urls(value: str) -> list[str]:
    urls: list[str] = []
    for part in value.split(","):
        token = part.strip().split()
        if token:
            urls.append(token[0])
    return urls


def _decode_escaped_urls(html: str) -> str:
    return (
        html.replace("\\u002F", "/")
        .replace("\\u002f", "/")
        .replace("\\/", "/")
        .replace("\\u0026", "&")
        .replace("\\u003D", "=")
        .replace("\\u003d", "=")
    )


def _clean_url(raw: str | None, *, base: str | None = None) -> str | None:
    if not raw:
        return None
    value = html_lib.unescape(str(raw)).strip().strip("\"'")
    if not value or value.startswith(("data:", "blob:", "javascript:", "mailto:", "tel:")):
        return None
    if base:
        value = urljoin(base, value)
    value = _decode_escaped_urls(value)
    value = value.rstrip(".,;")
    if value.endswith("*/"):
        value = value[:-2]
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    if parsed.netloc == "www.w3.org":
        return None
    if not parsed.path or parsed.path == "/":
        return None
    return value


def _is_imageish_url(url: str) -> bool:
    parsed = urlparse(url)
    path_lower = parsed.path.lower()
    suffix = Path(path_lower).suffix
    if suffix == ".map":
        return False
    if suffix in IMAGE_EXTS:
        return True
    lowered = url.lower()
    return any(marker in lowered for marker in IMAGE_URL_MARKERS)


def _asset_filename(url: str, content_type: str, content: bytes) -> str:
    ext = _extension_for(url, content_type)
    digest = hashlib.sha256(url.encode("utf-8") + b"\0" + content[:4096]).hexdigest()[:20]
    return f"{digest}{ext}"


def _extension_for(url: str, content_type: str) -> str:
    ctype_map = {
        "image/avif": ".avif",
        "image/gif": ".gif",
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/svg+xml": ".svg",
        "image/webp": ".webp",
        "image/x-icon": ".ico",
        "image/vnd.microsoft.icon": ".ico",
    }
    if content_type in ctype_map:
        return ctype_map[content_type]
    guessed = mimetypes.guess_extension(content_type or "")
    if guessed:
        return guessed
    suffix = Path(urlparse(url).path.lower()).suffix
    if suffix in IMAGE_EXTS:
        return suffix
    if "webp" in url.lower():
        return ".webp"
    return ".img"


def _url_variants(url: str) -> set[str]:
    escaped_slashes = url.replace("/", "\\/")
    escaped_unicode = url.replace("/", "\\u002F").replace("&", "\\u0026").replace("=", "\\u003D")
    return {
        url,
        html_lib.escape(url, quote=False),
        escaped_slashes,
        html_lib.escape(escaped_slashes, quote=False),
        escaped_unicode,
        html_lib.escape(escaped_unicode, quote=False),
    }
