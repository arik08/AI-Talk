"""출처 페이지의 실제 탭 제목(HTML의 <title>)을 조회한다.

화면의 출처 목록을 펼칠 때만 부른다. LLM을 쓰지 않고 페이지를 직접 받아 제목만 읽는다.

- http(s)의 공개 웹 주소만 받는다. 내부망·이 PC를 가리키는 주소는 조회하지 않고, 리디렉션 목적지도 같은 기준으로 본다.
- 페이지당 전체 8초, 받는 양 512KiB, 동시에 4개까지.
- 성공한 제목은 24시간, 실패는 5분 동안 기억한다 (최대 512개 주소). 같은 주소를 동시에 물으면 요청 하나를 같이 쓴다.
- 페이지가 열린 뒤 JavaScript가 바꾸는 제목은 알 수 없다. 조회하지 못하면 빈 문자열을 돌려주고 화면은 기존 표시를 둔다.
"""
from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
import time
from collections import OrderedDict
from typing import Optional
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup

MAX_URLS = 20
MAX_BYTES = 512 * 1024
TOTAL_SECONDS = 8.0
CONCURRENCY = 4
MAX_REDIRECTS = 5
OK_TTL = 24 * 60 * 60
FAIL_TTL = 5 * 60
CACHE_SIZE = 512
MAX_TITLE = 300

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5",
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.7",
}

_cache: "OrderedDict[str, tuple[float, str]]" = OrderedDict()   # 주소 -> (만료 시각, 제목)
_flying: dict[str, asyncio.Task] = {}
_gate: Optional[asyncio.Semaphore] = None
_gate_loop: Optional[asyncio.AbstractEventLoop] = None

_META_CHARSET = re.compile(rb"<meta[^>]+charset\s*=\s*[\"']?\s*([\w-]+)", re.IGNORECASE)


def clear_cache() -> None:
    _cache.clear()
    _flying.clear()


def _decode(data: bytes, header_charset: str = "") -> str:
    """한국어 페이지가 흔히 쓰는 인코딩까지 차례로 시도한다."""
    tried: list[str] = []
    meta = _META_CHARSET.search(data[:4096])
    for name in (header_charset, meta.group(1).decode("ascii", "ignore") if meta else "", "utf-8", "cp949"):
        name = (name or "").strip().lower()
        if not name or name in tried:
            continue
        tried.append(name)
        if name in ("euc-kr", "ks_c_5601-1987", "ksc5601"):
            name = "cp949"   # euc-kr로 적어 두고 확장 글자를 쓰는 페이지가 많다
        try:
            return data.decode(name)
        except (LookupError, UnicodeDecodeError):
            continue
    return data.decode("utf-8", errors="replace")


def extract_title(data: bytes, header_charset: str = "") -> str:
    """HTML에서 <title>을 꺼낸다. 엔티티를 풀고 빈칸을 한 칸으로 줄인다. 문구와 사이트 이름은 그대로 둔다."""
    soup = BeautifulSoup(_decode(data, header_charset), "html.parser")
    node = soup.find("title")
    if node is None:
        return ""
    return re.sub(r"\s+", " ", node.get_text()).strip()[:MAX_TITLE]


def _resolve(host: str) -> list[str]:
    return [info[4][0] for info in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)]


async def _is_public(url: str) -> bool:
    """공개 웹 주소인지. 이름이 가리키는 주소가 하나라도 내부망이면 받지 않는다."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password:
        return False
    host = parts.hostname
    try:
        addresses = [str(ipaddress.ip_address(host))]
    except ValueError:
        try:
            addresses = await asyncio.to_thread(_resolve, host)
        except OSError:
            return False
    if not addresses:
        return False
    for raw in addresses:
        try:
            if not ipaddress.ip_address(raw.split("%")[0]).is_global:
                return False
        except ValueError:
            return False
    return True


def _client() -> httpx.AsyncClient:
    """TLS 인증서 확인은 끄지 않는다. 리디렉션은 목적지를 확인해야 하므로 직접 따라간다."""
    return httpx.AsyncClient(follow_redirects=False, headers=HEADERS,
                             timeout=httpx.Timeout(TOTAL_SECONDS, connect=4.0))


async def _fetch(url: str) -> str:
    async with _client() as client:
        for _ in range(MAX_REDIRECTS + 1):
            if not await _is_public(url):
                return ""
            async with client.stream("GET", url) as res:
                if res.status_code in (301, 302, 303, 307, 308):
                    target = res.headers.get("location", "")
                    if not target:
                        return ""
                    url = urljoin(url, target)
                    continue
                if res.status_code != 200:
                    return ""
                kind = res.headers.get("content-type", "").lower()
                if kind and "html" not in kind:
                    return ""
                data = b""
                async for chunk in res.aiter_bytes():
                    data += chunk
                    if len(data) >= MAX_BYTES or b"</title>" in data.lower():   # 제목까지만 받으면 된다
                        break
                return extract_title(data[:MAX_BYTES], res.charset_encoding or "")
    return ""


def _semaphore() -> asyncio.Semaphore:
    global _gate, _gate_loop
    loop = asyncio.get_running_loop()
    if _gate is None or _gate_loop is not loop:
        _gate, _gate_loop = asyncio.Semaphore(CONCURRENCY), loop
    return _gate


async def _lookup(url: str) -> str:
    title = ""
    try:
        async with _semaphore():
            title = await asyncio.wait_for(_fetch(url), timeout=TOTAL_SECONDS)
    except Exception:  # noqa: BLE001 - 접속 실패, 시간 초과, 깨진 응답 모두 "제목 없음"으로 본다
        title = ""
    _cache[url] = (time.monotonic() + (OK_TTL if title else FAIL_TTL), title)
    _cache.move_to_end(url)
    while len(_cache) > CACHE_SIZE:
        _cache.popitem(last=False)
    return title


async def title_of(url: str) -> str:
    known = _cache.get(url)
    if known and known[0] > time.monotonic():
        _cache.move_to_end(url)
        return known[1]
    task = _flying.get(url)
    if task is None or task.done() or task.get_loop() is not asyncio.get_running_loop():
        task = asyncio.ensure_future(_lookup(url))
        _flying[url] = task
        task.add_done_callback(lambda done, key=url: _flying.pop(key, None) if _flying.get(key) is done else None)
    return await asyncio.shield(task)


async def fetch_titles(urls: list[str]) -> dict[str, str]:
    """주소마다 제목을 돌려준다. 조회하지 못한 주소는 빈 문자열."""
    unique = list(dict.fromkeys(u for u in urls if isinstance(u, str) and u.strip()))[:MAX_URLS]
    titles = await asyncio.gather(*(title_of(u) for u in unique))
    return dict(zip(unique, titles))
