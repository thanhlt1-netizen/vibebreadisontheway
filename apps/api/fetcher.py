"""Fetch HTML: httpx first, Playwright fallback when blocked / needs JS."""
from __future__ import annotations

import asyncio
import ipaddress
import socket
import time
import re
from urllib.parse import urlparse, urljoin


import httpx
from fastapi import HTTPException

UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "no-cache",
    "Upgrade-Insecure-Requests": "1",
}
MAX_BYTES = 5_000_000
_CACHE: dict[str, tuple[float, str]] = {}
TTL = 600

def normalize_url(url: str) -> str:
    """Strip tracking junk, force scheme, drop fragment."""
    url = (url or "").strip()
    if not url:
        return url
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url.lstrip("/")
    u = urlparse(url)
    # drop common tracking query keys
    from urllib.parse import parse_qsl, urlencode, urlunparse
    q = [(k, v) for k, v in parse_qsl(u.query, keep_blank_values=True)
         if k.lower() not in {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
                              "fbclid", "gclid", "ref", "spm", "from"}]
    return urlunparse((u.scheme.lower(), u.netloc.lower(), u.path or "/", "", urlencode(q), ""))



_PW_OK: bool | None = None


async def assert_public(url: str):
    """Block SSRF: only http(s) and public IPs."""
    u = urlparse(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        raise HTTPException(400, "URL không hợp lệ")
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(u.hostname, None)
    except socket.gaierror:
        raise HTTPException(400, "Không phân giải được tên miền")
    for *_, sa in infos:
        ip = ipaddress.ip_address(sa[0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise HTTPException(400, "Địa chỉ nội bộ không được phép")


def playwright_available() -> bool:
    global _PW_OK
    if _PW_OK is not None:
        return _PW_OK
    try:
        from playwright.async_api import async_playwright  # noqa: F401
        _PW_OK = True
    except ImportError:
        _PW_OK = False
    return _PW_OK


async def _playwright(url: str) -> str:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        raise HTTPException(
            502,
            "Trang cần chạy JavaScript / chống bot. "
            "Cài thêm: pip install playwright && playwright install chromium",
        )
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                context = await browser.new_context(
                    user_agent=UA["User-Agent"],
                    locale="vi-VN",
                    java_script_enabled=True,
                )
                page = await context.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=45000)
                try:
                    await page.wait_for_selector(
                        "#chapter-content, #chapter-c, .chapter-content, article, .entry-content",
                        timeout=8000,
                    )
                except Exception:
                    await page.wait_for_timeout(3000)
                html = await page.content()
                await context.close()
                return html
            finally:
                await browser.close()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"Playwright lỗi: {e.__class__.__name__}: {e}")


def _looks_blocked(status: int, text: str) -> bool:
    if status in (403, 429, 503, 520, 521, 522, 523, 524):
        return True
    low = (text or "")[:4000].lower()
    markers = (
        "cf-browser-verification",
        "just a moment",
        "checking your browser",
        "cloudflare",
        "access denied",
        "please enable javascript",
        "captcha",
        "attention required",
    )
    return any(m in low for m in markers)


async def fetch(url: str, retries: int = 2, force_browser: bool = False) -> str:
    hit = _CACHE.get(url)
    if hit and time.time() - hit[0] < TTL:
        return hit[1]
    html = await _fetch(url, retries, force_browser)
    if len(_CACHE) > 200:
        _CACHE.pop(next(iter(_CACHE)))
    _CACHE[url] = (time.time(), html)
    return html


async def _fetch(url: str, retries: int, force_browser: bool) -> str:
    if force_browser:
        return await _playwright(url)

    cur = url
    async with httpx.AsyncClient(headers=UA, timeout=25, follow_redirects=False) as c:
        for attempt in range(retries + 1):
            try:
                for _ in range(8):
                    await assert_public(cur)
                    r = await c.get(cur)
                    if r.is_redirect:
                        loc = r.headers.get("location")
                        if not loc:
                            break
                        cur = urljoin(cur, loc)
                        continue
                    break

                body = r.text if r.content else ""
                if _looks_blocked(r.status_code, body):
                    if playwright_available():
                        return await _playwright(cur)
                    raise HTTPException(
                        502,
                        "Trang bị chặn bot / cần JavaScript. "
                        "Cài: pip install playwright && playwright install chromium",
                    )

                r.raise_for_status()
                if len(r.content) > MAX_BYTES:
                    raise HTTPException(413, "Trang quá lớn")
                if len(body.strip()) < 200 and playwright_available():
                    return await _playwright(cur)
                return body
            except HTTPException:
                raise
            except (httpx.TransportError, httpx.HTTPStatusError) as e:
                if attempt == retries:
                    if playwright_available():
                        try:
                            return await _playwright(cur)
                        except HTTPException:
                            pass
                    raise HTTPException(502, f"Không tải được trang: {e.__class__.__name__}")
                await asyncio.sleep(1.2 * (attempt + 1))
    raise HTTPException(502, "Không tải được trang")
