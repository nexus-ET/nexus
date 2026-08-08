"""Real HTTP fetch + HTML text extraction + change detection for Nexus Intel."""

from __future__ import annotations

import hashlib
import logging
import re
from difflib import unified_diff
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
BROWSER_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}
FETCH_TIMEOUT_SECONDS = 45.0
BROWSER_TIMEOUT_MS = 45_000
BROWSER_SETTLE_MS = 2_500
MAX_STORE_CHARS = 40_000
MAX_DIFF_LINES = 80
MIN_CONTENT_CHARS = 100
BLOCK_MARKERS = (
    "just a moment",
    "attention required",
    "access denied",
    "cf-browser-verification",
    "enable javascript and cookies",
    "checking your browser",
    "sorry, you have been blocked",
    "request blocked",
)
SKIP_TAGS = {
    "script",
    "style",
    "noscript",
    "svg",
    "iframe",
    "canvas",
    "template",
    "head",
    "nav",
    "footer",
    "aside",
}


class _VisibleTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:  # noqa: ANN001
        if tag.lower() in SKIP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = data.strip()
        if text:
            self._chunks.append(text)

    def get_text(self) -> str:
        joined = " ".join(self._chunks)
        joined = re.sub(r"\s+", " ", joined).strip()
        return joined


def html_to_visible_text(html: str) -> str:
    parser = _VisibleTextExtractor()
    try:
        parser.feed(html or "")
        parser.close()
    except Exception:  # noqa: BLE001
        # Fall back to crude tag strip if the document is badly formed.
        rough = re.sub(r"(?is)<(script|style|noscript).*?>.*?</\1>", " ", html or "")
        rough = re.sub(r"(?s)<[^>]+>", " ", rough)
        return re.sub(r"\s+", " ", rough).strip()
    return parser.get_text()


def normalize_content_text(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    return cleaned[:MAX_STORE_CHARS]


def content_hash(text: str) -> str:
    return hashlib.sha256(normalize_content_text(text).encode("utf-8")).hexdigest()


def build_diff_summary(old_text: str | None, new_text: str, *, source_name: str) -> str:
    old_lines = (old_text or "").splitlines() or [""]
    new_lines = (new_text or "").splitlines() or [""]
    # Prefer sentence-ish chunks for readable diffs when content is one long line.
    if len(old_lines) == 1 and len(old_lines[0]) > 200:
        old_lines = re.split(r"(?<=[.!?])\s+", old_lines[0])
    if len(new_lines) == 1 and len(new_lines[0]) > 200:
        new_lines = re.split(r"(?<=[.!?])\s+", new_lines[0])

    diff_lines = list(
        unified_diff(
            old_lines,
            new_lines,
            fromfile=f"{source_name}:previous",
            tofile=f"{source_name}:current",
            lineterm="",
            n=1,
        )
    )
    if not diff_lines:
        return f"Content changed on {source_name} (no line-level diff available)."
    clipped = diff_lines[:MAX_DIFF_LINES]
    if len(diff_lines) > MAX_DIFF_LINES:
        clipped.append(f"... ({len(diff_lines) - MAX_DIFF_LINES} more diff lines omitted)")
    return "\n".join(clipped)


def _extract_text_from_response_body(raw: str, content_type: str) -> str:
    ctype = (content_type or "").lower()
    body = raw or ""
    if "html" in ctype or "<html" in body[:500].lower() or "<!doctype" in body[:200].lower():
        return normalize_content_text(html_to_visible_text(body))
    return normalize_content_text(re.sub(r"\s+", " ", body).strip())


def _looks_blocked(*, status: int | None, text: str, raw_html: str = "") -> bool:
    if status is not None and status >= 400:
        return True
    sample = f"{text} {raw_html[:2000]}".lower()
    if any(marker in sample for marker in BLOCK_MARKERS):
        # Challenge pages are usually short; allow long pages that merely mention the phrase.
        if len(text) < 800:
            return True
    if len(text) < MIN_CONTENT_CHARS:
        return True
    return False


def _browser_fallback_enabled() -> bool:
    try:
        from app.config import settings

        return bool(getattr(settings, "INTEL_SCRAPER_BROWSER_FALLBACK", True))
    except Exception:  # noqa: BLE001
        return True


def _insecure_ssl_allowed() -> bool:
    try:
        from app.config import settings

        return bool(getattr(settings, "INTEL_SCRAPER_ALLOW_INSECURE_SSL", True))
    except Exception:  # noqa: BLE001
        return True


def _fetch_httpx_once(url: str, *, verify: bool, http2: bool) -> dict[str, Any]:
    with httpx.Client(
        timeout=FETCH_TIMEOUT_SECONDS,
        follow_redirects=True,
        headers=BROWSER_HEADERS,
        verify=verify,
        http2=http2,
    ) as client:
        response = client.get(url)

    status = response.status_code
    content_type = response.headers.get("content-type") or ""
    raw = response.text or ""
    text = _extract_text_from_response_body(raw, content_type)

    if _looks_blocked(status=status, text=text, raw_html=raw):
        raise RuntimeError(
            f"HTTP fetch blocked or empty (status={status}, chars={len(text)}, http2={http2}) for {url}"
        )

    mode = "httpx" if verify else "httpx_insecure_ssl"
    if not http2:
        mode = f"{mode}_http1"
    return {
        "text": text,
        "hash": content_hash(text),
        "http_status": status,
        "final_url": str(response.url),
        "content_type": content_type,
        "fetch_mode": mode,
    }


def _fetch_httpx(url: str, *, verify: bool) -> dict[str, Any]:
    """Prefer HTTP/2, then fall back to HTTP/1.1 on protocol resets (common on canada.ca)."""
    try:
        return _fetch_httpx_once(url, verify=verify, http2=True)
    except Exception as http2_exc:  # noqa: BLE001
        message = str(http2_exc)
        should_retry_http1 = any(
            token in message
            for token in (
                "StreamReset",
                "ConnectionTerminated",
                "Server disconnected",
                "ReadTimeout",
                "ConnectTimeout",
                "RemoteProtocolError",
            )
        ) or isinstance(
            http2_exc,
            (
                httpx.RemoteProtocolError,
                httpx.ReadTimeout,
                httpx.ConnectTimeout,
                httpx.ReadError,
            ),
        )
        if not should_retry_http1:
            raise
        logger.info("Retrying %s over HTTP/1.1 after: %s", url, http2_exc)
        try:
            return _fetch_httpx_once(url, verify=verify, http2=False)
        except Exception as http1_exc:  # noqa: BLE001
            raise RuntimeError(f"http2: {http2_exc} | http1: {http1_exc}") from http1_exc


# Chromium / chrome-headless-shell launch flags: keep DevTools on loopback and
# suppress MediaRouter/WebRTC so Windows Firewall does not prompt for Public access
# on chrome-headless-shell.exe (Playwright's headless binary on Windows).
_PLAYWRIGHT_CHROMIUM_ARGS = (
    "--remote-debugging-address=127.0.0.1",
    "--disable-background-networking",
    "--disable-client-side-phishing-detection",
    "--disable-component-extensions-with-background-pages",
    "--disable-default-apps",
    "--disable-extensions",
    "--disable-features=MediaRouter,DialMediaRouteProvider,CastMediaRouteProvider,Translate,OptimizationHints",
    "--disable-hang-monitor",
    "--disable-popup-blocking",
    "--disable-prompt-on-repost",
    "--disable-sync",
    "--metrics-recording-only",
    "--mute-audio",
    "--no-default-browser-check",
    "--no-first-run",
    "--no-proxy-server",
    "--password-store=basic",
    "--use-mock-keychain",
    # Avoid WebRTC probing interfaces that Windows treats as inbound network use.
    "--force-webrtc-ip-permission-check",
    "--webrtc-ip-handling-policy=disable_non_proxied_udp",
)


def _fetch_playwright(url: str) -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright is not installed in this Python environment. "
            "From backend/.venv run: pip install playwright && python -m playwright install chromium"
        ) from exc

    with sync_playwright() as playwright:
        # Playwright 1.4x+ uses chrome-headless-shell for headless=True (Windows: chrome-headless-shell.exe).
        browser = playwright.chromium.launch(
            headless=True,
            chromium_sandbox=False,
            args=list(_PLAYWRIGHT_CHROMIUM_ARGS),
        )
        try:
            context = browser.new_context(
                user_agent=USER_AGENT,
                locale="en-US",
                viewport={"width": 1365, "height": 900},
                java_script_enabled=True,
                ignore_https_errors=_insecure_ssl_allowed(),
            )
            page = context.new_page()
            response = page.goto(url, wait_until="domcontentloaded", timeout=BROWSER_TIMEOUT_MS)
            page.wait_for_timeout(BROWSER_SETTLE_MS)

            text = ""
            html = ""
            title = ""
            for _ in range(5):
                title = page.title() or ""
                html = page.content()
                text = normalize_content_text(html_to_visible_text(html))
                title_l = title.lower()
                if (
                    len(text) >= MIN_CONTENT_CHARS
                    and "just a moment" not in title_l
                    and not any(marker in text.lower() for marker in BLOCK_MARKERS if len(text) < 800)
                ):
                    break
                page.wait_for_timeout(1500)

            status = response.status if response else 200
            final_url = page.url
        finally:
            browser.close()

    # Prefer rendered content over the initial navigation status (bot walls often report 403
    # on the challenge response even after JS clears, or vice versa).
    if len(text) < MIN_CONTENT_CHARS or "just a moment" in (title or "").lower():
        raise RuntimeError(
            f"Browser fetch blocked or empty (status={status}, title={title!r}, chars={len(text)}) for {url}"
        )
    if len(text) < 800 and any(marker in text.lower() for marker in BLOCK_MARKERS):
        raise RuntimeError(
            f"Browser fetch blocked or empty (status={status}, title={title!r}, chars={len(text)}) for {url}"
        )

    return {
        "text": text,
        "hash": content_hash(text),
        "http_status": int(status or 200),
        "final_url": final_url,
        "content_type": "text/html",
        "fetch_mode": "playwright",
    }


def fetch_url_text(url: str) -> dict[str, Any]:
    """Fetch a URL and return normalized visible text + metadata.

    Strategy:
    1. httpx with browser-like headers (fast path)
    2. retry once with verify=False on TLS chain failures (e.g. KHDA)
    3. Playwright Chromium fallback for Cloudflare/Akamai/JS shells
    """
    errors: list[str] = []

    try:
        return _fetch_httpx(url, verify=True)
    except httpx.ConnectError as exc:
        message = str(exc)
        if "CERTIFICATE_VERIFY_FAILED" in message or "SSL" in message.upper():
            if _insecure_ssl_allowed():
                logger.warning("TLS verify failed for %s; retrying with verify=False", url)
                try:
                    return _fetch_httpx(url, verify=False)
                except Exception as insecure_exc:  # noqa: BLE001
                    errors.append(f"httpx_insecure_ssl: {insecure_exc}")
            else:
                errors.append(f"httpx_tls: {exc}")
        else:
            errors.append(f"httpx_connect: {exc}")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"httpx: {exc}")

    if _browser_fallback_enabled():
        try:
            result = _fetch_playwright(url)
            logger.info("Playwright fallback succeeded for %s (%s chars)", url, len(result["text"]))
            return result
        except Exception as exc:  # noqa: BLE001
            errors.append(f"playwright: {exc}")
            logger.warning("Playwright fallback failed for %s: %s", url, exc)

    raise RuntimeError(" | ".join(errors) if errors else f"Failed to fetch {url}")


def same_source_host(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return False
    try:
        host_a = (urlparse(a).hostname or "").lower().removeprefix("www.")
        host_b = (urlparse(b).hostname or "").lower().removeprefix("www.")
        return bool(host_a and host_a == host_b)
    except Exception:  # noqa: BLE001
        return False
