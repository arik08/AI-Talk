"""P-GPT 점검 스크립트. 회사 OA망에서 한 번 돌려, AI-Talk가 쓰는 기능이 실제로 되는지 확인한다.

    python scripts/check_pgpt.py            # 기본 모델(gpt-6-luna)로 점검
    python scripts/check_pgpt.py gpt-6.1-sol

.env의 PGPT_API_KEY, PGPT_EMPNO(또는 PGPT_SYSTEM_CODE)를 쓴다. 키 값은 출력하지 않는다.
결과 표에서 '안 됨'으로 나온 항목은 설계 문서 14번의 대안으로 넘어가야 한다.
"""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "server"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from aitalk.config import settings  # noqa: E402
from aitalk.providers.pgpt import DEFAULT_BASE_URL, MODELS, build_token, normalize_base_url  # noqa: E402

MODEL = sys.argv[1] if len(sys.argv) > 1 else "gpt-6-luna"
RESULTS: list[tuple[str, str, str]] = []


def record(name: str, ok: bool | None, detail: str = "") -> None:
    mark = "됨" if ok else ("확인 필요" if ok is None else "안 됨")
    RESULTS.append((name, mark, detail[:110]))
    print(f"[{mark}] {name} {('- ' + detail[:200]) if detail else ''}")


async def text_of(stream) -> tuple[str, object, list[str]]:
    text, final, items = "", None, []
    async for event in stream:
        kind = getattr(event, "type", "")
        if kind == "response.output_text.delta":
            text += event.delta
        elif kind == "response.output_item.done":
            items.append(getattr(event.item, "type", ""))
        elif kind == "response.completed":
            final = event.response
    return text, final, items


async def main() -> None:
    key = settings.get("PGPT_API_KEY")
    code = settings.get("PGPT_SYSTEM_CODE") or settings.get("PGPT_EMPNO")
    if not key or not code:
        print(".env에 PGPT_API_KEY와 PGPT_EMPNO(또는 PGPT_SYSTEM_CODE)를 먼저 채워 주세요.")
        return
    from openai import AsyncOpenAI
    base = normalize_base_url(settings.get("PGPT_BASE_URL") or DEFAULT_BASE_URL)
    client = AsyncOpenAI(api_key=build_token(key, code), base_url=base, timeout=120)
    print(f"주소: {base}\n모델: {MODEL}\n")

    # 1. 모델 목록
    try:
        page = await client.models.list()
        seen = sorted(m.id for m in page.data)
        wanted = [m.id for m in MODELS]
        have = [m for m in wanted if m in seen]
        record("모델 목록", bool(have), f"AI-Talk가 쓰는 모델 {wanted} 가운데 있는 것: {have}")
        print("   전체:", ", ".join(seen))
    except Exception as exc:  # noqa: BLE001
        record("모델 목록", False, str(exc))

    base_kw = {"model": MODEL, "reasoning": {"effort": "low"}}

    # 2. 스트리밍 + 상태 유지
    first_id = None
    try:
        t0 = time.time()
        stream = await client.responses.create(
            stream=True, store=True, **base_kw,
            input=[{"role": "developer", "content": "당신은 토론 참가자 '가온'입니다. 한 문장으로만 답합니다."},
                   {"role": "user", "content": "【다음 발언: 가온】 좋아하는 숫자를 하나 정해 '제 숫자는 N입니다'라고 말하세요."}])
        text, final, _ = await text_of(stream)
        first_id = final.id
        usage = final.usage
        record("Responses 스트리밍", bool(text), f"{time.time() - t0:.1f}초, \"{text.strip()[:40]}\"")
        record("추론 노력 (reasoning.effort)", True, "low로 요청해 받아짐")
    except Exception as exc:  # noqa: BLE001
        record("Responses 스트리밍", False, str(exc))
    if not first_id:
        return summary()

    second_id = None
    try:
        stream = await client.responses.create(
            stream=True, store=True, previous_response_id=first_id, **base_kw,
            input=[{"role": "user", "content": "【다음 발언: 가온】 방금 말한 숫자를 다시 한 번 말하세요."}])
        text, final, _ = await text_of(stream)
        second_id = final.id
        record("상태 유지 (store + previous_response_id)", bool(text), f"\"{text.strip()[:40]}\" ← 앞의 숫자와 같아야 함")
        details = getattr(final.usage, "input_tokens_details", None)
        record("캐시 사용량 필드", getattr(details, "cached_tokens", None) is not None,
               f"cached_tokens={getattr(details, 'cached_tokens', None)}, cache_write_tokens={getattr(details, 'cache_write_tokens', None)}")
    except Exception as exc:  # noqa: BLE001
        record("상태 유지 (store + previous_response_id)", False, str(exc))

    # 3. 곁가지: 같은 응답에서 두 번, store=False로
    try:
        for n in (1, 2):
            stream = await client.responses.create(
                stream=True, store=False, previous_response_id=first_id, **base_kw,
                input=[{"role": "user", "content": f"(곁가지 {n}) 방금 말한 숫자에 {n}을 더한 값만 말하세요."}])
            text, _, _ = await text_of(stream)
        record("곁가지 (한 응답에서 두 갈래, store=False)", bool(text), f"두 번째 답: \"{text.strip()[:30]}\"")
    except Exception as exc:  # noqa: BLE001
        record("곁가지 (한 응답에서 두 갈래, store=False)", False, str(exc))

    # 4. 끊긴 발언 넣기: 앞 응답을 가리키며 assistant 항목을 입력으로
    try:
        stream = await client.responses.create(
            stream=True, store=True, previous_response_id=first_id, **base_kw,
            input=[{"role": "user", "content": "【다음 발언: 가온】 이어서 말하세요."},
                   {"role": "assistant", "content": "그런데 제가 정말 하고 싶은 말은 —"},
                   {"role": "user", "content": "【다음 발언: 나래】 가온의 말이 어디서 끊겼는지 한 문장으로 말하세요."}])
        text, _, _ = await text_of(stream)
        record("끊긴 발언 넣기 (assistant 입력 항목)", bool(text), f"\"{text.strip()[:50]}\"")
    except Exception as exc:  # noqa: BLE001
        record("끊긴 발언 넣기 (assistant 입력 항목)", False, str(exc))

    # 5. JSON 틀
    try:
        schema = {"type": "object", "properties": {"n": {"type": "integer"}}, "required": ["n"], "additionalProperties": False}
        stream = await client.responses.create(
            stream=True, store=False, previous_response_id=first_id, **base_kw,
            text={"format": {"type": "json_schema", "name": "result", "schema": schema, "strict": True}},
            input=[{"role": "user", "content": "방금 말한 숫자를 n에 넣어 JSON으로 답하세요."}])
        text, _, _ = await text_of(stream)
        record("JSON 틀 (text.format json_schema)", text.strip().startswith("{"), text.strip()[:60])
    except Exception as exc:  # noqa: BLE001
        record("JSON 틀 (text.format json_schema)", False, str(exc))

    # 6. 자동 압축
    try:
        stream = await client.responses.create(
            stream=True, store=True, previous_response_id=second_id or first_id, **base_kw,
            extra_body={"context_management": [{"type": "compaction", "compact_threshold": 200000}]},
            input=[{"role": "user", "content": "【다음 발언: 가온】 '확인'이라고만 말하세요."}])
        text, _, _ = await text_of(stream)
        record("자동 압축 설정 (context_management)", True, "요청이 받아짐. 실제 압축은 문맥이 기준을 넘어야 일어남")
    except Exception as exc:  # noqa: BLE001
        record("자동 압축 설정 (context_management)", False, str(exc))

    # 7. 줄기 중 모델 변경
    other = next((m.id for m in MODELS if m.id != MODEL), None)
    if other:
        try:
            stream = await client.responses.create(
                stream=True, store=True, previous_response_id=first_id, model=other, reasoning={"effort": "low"},
                input=[{"role": "user", "content": "【다음 발언: 나래】 가온이 말한 숫자를 말하세요."}])
            text, _, _ = await text_of(stream)
            record(f"줄기 중 모델 변경 ({MODEL} → {other})", bool(text), f"\"{text.strip()[:40]}\"")
        except Exception as exc:  # noqa: BLE001
            record(f"줄기 중 모델 변경 ({MODEL} → {other})", False, str(exc))

    # 8. 웹 검색
    for tool in ("web_search", "web_search_preview"):
        try:
            stream = await client.responses.create(
                stream=True, store=False, **base_kw, tools=[{"type": tool}],
                input="오늘 날짜의 주요 뉴스 제목 하나를 검색해서 한 문장으로 알려 주세요.")
            text, _, items = await text_of(stream)
            record(f"웹 검색 도구 ({tool})", "web_search_call" in items, f"검색 호출 {'있음' if 'web_search_call' in items else '없음'}: \"{text.strip()[:40]}\"")
        except Exception as exc:  # noqa: BLE001
            record(f"웹 검색 도구 ({tool})", False, str(exc))

    # 9. 사내 인터넷
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as http:
            resp = await http.get("https://example.com")
        record("서버 PC에서 외부 웹 페이지 받기", resp.status_code == 200, f"HTTP {resp.status_code}")
    except Exception as exc:  # noqa: BLE001
        record("서버 PC에서 외부 웹 페이지 받기", False, str(exc))
    summary()


def summary() -> None:
    print("\n" + "=" * 78)
    print(f"{'항목':<44}{'결과':<10}비고")
    print("-" * 78)
    for name, mark, detail in RESULTS:
        print(f"{name:<44}{mark:<10}{detail}")
    print("=" * 78)
    print("이 표를 그대로 복사해 전달해 주시면 안 되는 항목을 대안으로 바꿉니다.")


if __name__ == "__main__":
    asyncio.run(main())
