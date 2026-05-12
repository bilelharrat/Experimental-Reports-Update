"""Optional browser-rendered HTML capture for difficult news pages."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .link_preview import USER_AGENT, extract_text_from_html

DEFAULT_CHROME_CANDIDATES = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "google-chrome",
    "chrome",
    "chromium",
    "chromium-browser",
)


@dataclass
class BrowserRenderResult:
    html: str = ""
    text: str = ""
    renderer: str | None = None
    error: str | None = None
    stderr: str = ""


def render_html(url: str, *, timeout: float = 45.0) -> BrowserRenderResult:
    """Render a URL with a local headless Chrome binary, if available."""
    chrome = _find_chrome()
    if not chrome:
        return BrowserRenderResult(error="No local Chrome/Chromium renderer found")

    with tempfile.TemporaryDirectory(prefix="bsh-news-browser-") as tmp:
        profile = Path(tmp) / "profile"
        chrome_timeout_ms = min(12_000, max(3_000, int(timeout * 1000 * 0.65)))
        wait_timeout = min(timeout, chrome_timeout_ms / 1000 + 5)
        cmd = [
            chrome,
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--disable-extensions",
            "--disable-background-networking",
            "--no-first-run",
            "--no-default-browser-check",
            f"--user-agent={USER_AGENT}",
            f"--user-data-dir={profile}",
            "--window-size=1440,2200",
            f"--timeout={chrome_timeout_ms}",
            "--dump-dom",
            url,
        ]
        timed_out_with_html = False
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            html, stderr = proc.communicate(timeout=wait_timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            html, stderr = proc.communicate()
            if len((html or "").strip()) < 100:
                return BrowserRenderResult(
                    renderer=chrome,
                    error="Browser render timed out",
                    stderr=(stderr or "")[-4000:],
                )
            timed_out_with_html = True
        except Exception as exc:  # noqa: BLE001
            return BrowserRenderResult(
                renderer=chrome,
                error=f"{type(exc).__name__}: {exc}",
            )

    html = html or ""
    stderr = (stderr or "")[-4000:]
    if proc.returncode not in (0, None) and not timed_out_with_html:
        return BrowserRenderResult(
            renderer=chrome,
            error=f"Browser exited with code {proc.returncode}",
            stderr=stderr,
        )
    if len(html.strip()) < 100:
        return BrowserRenderResult(
            renderer=chrome,
            error="Browser returned too little HTML",
            stderr=stderr,
        )
    return BrowserRenderResult(
        html=html,
        text=extract_text_from_html(html),
        renderer=chrome,
        stderr=stderr,
    )


def _find_chrome() -> str | None:
    configured = os.environ.get("BSH_BROWSER_RENDERER")
    candidates = (configured,) if configured else DEFAULT_CHROME_CANDIDATES
    for candidate in candidates:
        if not candidate:
            continue
        if "/" in candidate:
            path = Path(candidate)
            if path.exists() and os.access(path, os.X_OK):
                return str(path)
        else:
            found = shutil.which(candidate)
            if found:
                return found
    return None
