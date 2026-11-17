"""올린 문서와 웹 페이지에서 글자를 뽑는다. 내 PC에서 처리하므로 프로바이더와 무관하다."""
from __future__ import annotations

import io
import re

SUPPORTED = (".pdf", ".docx", ".txt", ".md", ".markdown")


class MaterialError(Exception):
    pass


def extract_text(filename: str, data: bytes) -> str:
    lower = filename.lower()
    if lower.endswith(".pdf"):
        from pypdf import PdfReader
        try:
            reader = PdfReader(io.BytesIO(data))
            text = "\n\n".join((page.extract_text() or "") for page in reader.pages)
        except Exception as exc:  # noqa: BLE001
            raise MaterialError(f"PDF를 읽지 못했습니다: {exc}") from exc
    elif lower.endswith(".docx"):
        try:
            import docx
        except ImportError as exc:
            raise MaterialError("Word 문서를 읽으려면 python-docx를 설치해야 합니다.") from exc
        try:
            document = docx.Document(io.BytesIO(data))
            rows = [p.text for p in document.paragraphs]
            for table in document.tables:
                for row in table.rows:
                    rows.append(" | ".join(cell.text.strip() for cell in row.cells))
            text = "\n".join(rows)
        except Exception as exc:  # noqa: BLE001
            raise MaterialError(f"Word 문서를 읽지 못했습니다: {exc}") from exc
    elif lower.endswith((".txt", ".md", ".markdown")):
        for encoding in ("utf-8-sig", "cp949", "utf-16"):
            try:
                text = data.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        else:
            raise MaterialError("글자 인코딩을 알 수 없는 파일입니다.")
    else:
        raise MaterialError("PDF, Word(.docx), 텍스트, 마크다운 파일만 올릴 수 있습니다.")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not text:
        raise MaterialError("문서에서 글자를 찾지 못했습니다. 그림으로만 된 문서일 수 있습니다.")
    return text


def estimate_tokens(text: str) -> int:
    """한글은 글자당 약 1토큰, 영문은 4글자당 1토큰으로 어림한다."""
    hangul = len(re.findall(r"[가-힣]", text))
    return hangul + (len(text) - hangul) // 4


async def fetch_page(url: str) -> str:
    """웹 페이지를 직접 받아 본문 글자만 남긴다. 프로바이더의 웹 도구가 안 될 때 쓴다."""
    import httpx
    from bs4 import BeautifulSoup
    headers = {"User-Agent": "Mozilla/5.0 (compatible; debate-reader)"}
    async with httpx.AsyncClient(follow_redirects=True, timeout=20, headers=headers) as client:
        resp = await client.get(url)
        resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form", "noscript"]):
        tag.decompose()
    body = soup.find("article") or soup.find("main") or soup.body or soup
    text = re.sub(r"\n{3,}", "\n\n", body.get_text("\n", strip=True))
    return text[:30000]
