import asyncio, ipaddress, socket, time
from urllib.parse import urlparse, urljoin
import httpx
from fastapi import HTTPException

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
      "Accept-Language": "vi,en;q=0.8"}
MAX_BYTES = 5_000_000

async def assert_public(url: str):
    """Chặn SSRF: chỉ http(s) và host phân giải ra IP công khai."""
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

async def _playwright(url: str) -> str:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        raise HTTPException(502, "Trang cần chạy JS/chống bot. Cài playwright để bật chế độ trình duyệt.")
    async with async_playwright() as p:
        b = await p.chromium.launch()
        page = await b.new_page(user_agent=UA["User-Agent"])
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2500)
        html = await page.content(); await b.close()
        return html

_CACHE: dict[str, tuple[float, str]] = {}
TTL = 600

async def fetch(url: str, retries: int = 2) -> str:
    hit = _CACHE.get(url)
    if hit and time.time() - hit[0] < TTL: return hit[1]
    html = await _fetch(url, retries)
    if len(_CACHE) > 200: _CACHE.pop(next(iter(_CACHE)))
    _CACHE[url] = (time.time(), html)
    return html

async def _fetch(url: str, retries: int) -> str:
    cur = url
    async with httpx.AsyncClient(headers=UA, timeout=20, follow_redirects=False) as c:
        for attempt in range(retries + 1):
            try:
                for _ in range(5):                       # tự theo redirect để kiểm tra từng bước
                    await assert_public(cur)
                    r = await c.get(cur)
                    if r.is_redirect: cur = urljoin(cur, r.headers["location"]); continue
                    break
                if r.status_code in (403, 429, 503):     # nghi Cloudflare → thử bằng trình duyệt
                    return await _playwright(cur)
                r.raise_for_status()
                if len(r.content) > MAX_BYTES: raise HTTPException(413, "Trang quá lớn")
                return r.text
            except (httpx.TransportError, httpx.HTTPStatusError) as e:
                if attempt == retries: raise HTTPException(502, f"Không tải được trang: {e.__class__.__name__}")
                await asyncio.sleep(1.5 * (attempt + 1))
