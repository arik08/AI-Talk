"""출처 페이지의 탭 제목 조회: 제목 추출, 인코딩, 캐시, 제한, 실패 처리, API."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from aitalk import app as app_module  # noqa: E402
from aitalk import source_titles as st  # noqa: E402
from aitalk.config import settings  # noqa: E402

PUBLIC = "93.184.216.34"


def _html(title: str, charset: str = "utf-8") -> bytes:
    return f"<html><head><meta charset='{charset}'><title>{title}</title></head><body>본문</body></html>".encode(charset)


@pytest.fixture
def web(monkeypatch):
    """가짜 웹. pages[주소] = httpx.Response 또는 (요청) -> 응답. calls에 받은 주소가 쌓인다."""
    st.clear_cache()
    pages: dict = {}
    calls: list[str] = []
    hosts: dict[str, list[str]] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        calls.append(url)
        page = pages.get(url)
        if page is None:
            return httpx.Response(404)
        if callable(page):
            page = page(request)
            if asyncio.iscoroutine(page):
                page = await page
        return page

    monkeypatch.setattr(st, "_client", lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=False))
    monkeypatch.setattr(st, "_resolve", lambda host: hosts.get(host, [PUBLIC]))
    yield type("Web", (), {"pages": pages, "calls": calls, "hosts": hosts})
    st.clear_cache()


def _run(coro):
    return asyncio.run(coro)


def test_extracts_title_with_entities_and_whitespace():
    html = b"<html><head><title>\n  AT&amp;T &#8211; \xec\xb2\xa0\xea\xb0\x95   \xec\x88\x98\xec\xb6\x9c | Newsroom\n</title></head></html>"
    assert st.extract_title(html) == "AT&T – 철강 수출 | Newsroom"
    assert st.extract_title(b"<html><body>no title</body></html>") == ""


def test_decodes_korean_pages_by_header_meta_or_guess():
    text = "포스코 뉴스룸 - 똠방각하"
    assert st.extract_title(_html(text, "cp949").replace(b"cp949", b"euc-kr")) == text      # meta가 euc-kr
    assert st.extract_title(f"<title>{text}</title>".encode("cp949"), "EUC-KR") == text       # 응답 헤더
    assert st.extract_title(f"<title>{text}</title>".encode("cp949")) == text                 # 표시가 없어도
    assert st.extract_title(f"<title>{text}</title>".encode("utf-8")) == text


def test_fetches_title_and_reuses_cache(web):
    url = "https://news.example/a"
    web.pages[url] = httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"}, content=_html("철강 수출 급증 | 뉴스"))
    assert _run(st.fetch_titles([url, url])) == {url: "철강 수출 급증 | 뉴스"}
    assert _run(st.fetch_titles([url])) == {url: "철강 수출 급증 | 뉴스"}
    assert web.calls == [url]   # 다시 물어도 페이지는 한 번만 받는다


def test_concurrent_requests_for_one_url_share_a_single_fetch(web):
    url = "https://news.example/slow"

    async def slow(_request):
        await asyncio.sleep(0.05)
        return httpx.Response(200, headers={"content-type": "text/html"}, content=_html("느린 페이지"))

    web.pages[url] = slow

    async def both():
        return await asyncio.gather(st.fetch_titles([url]), st.fetch_titles([url]))

    assert _run(both()) == [{url: "느린 페이지"}, {url: "느린 페이지"}]
    assert web.calls == [url]


def test_failures_keep_empty_title_and_are_cached_briefly(web, monkeypatch):
    urls = ["https://news.example/missing", "https://news.example/file.pdf", "https://news.example/untitled"]
    web.pages[urls[1]] = httpx.Response(200, headers={"content-type": "application/pdf"}, content=b"%PDF-1.7")
    web.pages[urls[2]] = httpx.Response(200, headers={"content-type": "text/html"}, content=b"<html><body>x</body></html>")
    assert _run(st.fetch_titles(urls)) == dict.fromkeys(urls, "")
    assert len(web.calls) == 3
    _run(st.fetch_titles(urls))
    assert len(web.calls) == 3                        # 실패도 잠시 기억한다
    now = st.time.monotonic()
    monkeypatch.setattr(st.time, "monotonic", lambda: now + st.FAIL_TTL + 1)
    _run(st.fetch_titles(urls[:1]))
    assert len(web.calls) == 4                        # 5분이 지나면 다시 조회한다


def test_timeout_is_a_failure_not_an_error(web, monkeypatch):
    url = "https://news.example/hang"

    async def hang(_request):
        await asyncio.sleep(5)
        return httpx.Response(200, content=_html("늦음"))

    web.pages[url] = hang
    monkeypatch.setattr(st, "TOTAL_SECONDS", 0.05)
    assert _run(st.fetch_titles([url])) == {url: ""}


def test_private_addresses_are_never_fetched(web):
    web.hosts["intranet.example"] = ["10.0.0.5"]
    web.hosts["mixed.example"] = [PUBLIC, "127.0.0.1"]
    urls = ["http://127.0.0.1:8765/api/status", "http://localhost/", "http://192.168.0.10/", "http://[::1]/",
            "https://intranet.example/", "https://mixed.example/", "ftp://news.example/a", "https://user:pw@news.example/"]
    web.hosts["localhost"] = ["127.0.0.1"]
    assert _run(st.fetch_titles(urls)) == dict.fromkeys(urls, "")
    assert web.calls == []


def test_redirects_are_followed_only_to_public_addresses(web):
    web.hosts["inside.example"] = ["192.168.1.1"]
    web.pages["https://short.example/x"] = httpx.Response(302, headers={"location": "https://news.example/final"})
    web.pages["https://news.example/final"] = httpx.Response(200, headers={"content-type": "text/html"}, content=_html("도착한 기사"))
    web.pages["https://short.example/bad"] = httpx.Response(301, headers={"location": "http://inside.example/admin"})
    web.pages["http://inside.example/admin"] = httpx.Response(200, headers={"content-type": "text/html"}, content=_html("내부 관리"))
    out = _run(st.fetch_titles(["https://short.example/x", "https://short.example/bad"]))
    assert out == {"https://short.example/x": "도착한 기사", "https://short.example/bad": ""}
    assert "http://inside.example/admin" not in web.calls


def test_download_stops_at_the_size_limit(web):
    url = "https://news.example/huge"
    body = b"<html><head>" + b"<!-- pad -->" * 60000 + b"<title>too late</title>"
    assert len(body) > st.MAX_BYTES
    web.pages[url] = httpx.Response(200, headers={"content-type": "text/html"}, content=body)
    assert _run(st.fetch_titles([url])) == {url: ""}


def test_cache_keeps_at_most_the_limit(web, monkeypatch):
    monkeypatch.setattr(st, "CACHE_SIZE", 3)
    urls = [f"https://news.example/{i}" for i in range(5)]
    for u in urls:
        web.pages[u] = httpx.Response(200, headers={"content-type": "text/html"}, content=_html(u[-1]))
    _run(st.fetch_titles(urls))
    assert len(st._cache) == 3 and urls[0] not in st._cache and urls[4] in st._cache


def test_api_returns_titles_and_limits_batch_size(web, monkeypatch):
    monkeypatch.setitem(settings._file, "AITALK_ACCESS_CODE", "")
    url = "https://news.example/a"
    web.pages[url] = httpx.Response(200, headers={"content-type": "text/html"}, content=_html("API로 받은 제목"))
    client = TestClient(app_module.app)
    res = client.post("/api/source-titles", json={"urls": [url, "http://127.0.0.1/"]})
    assert res.status_code == 200
    assert res.json() == {"titles": {url: "API로 받은 제목", "http://127.0.0.1/": ""}}
    too_many = [f"https://news.example/{i}" for i in range(st.MAX_URLS + 1)]
    assert client.post("/api/source-titles", json={"urls": too_many}).status_code == 400
    assert client.post("/api/source-titles", json={"urls": []}).json() == {"titles": {}}
