"""P-GPT 문맥 관리의 회귀 시험. 실제 API 대신 가상 API로 본다.

응답 만료, 문맥 초과, 압축 거절, 요약 실패, 끊긴 발언, 검색 중복 수집, 끝나지 않은 스트림.
"""
import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from aitalk.providers import pgpt  # noqa: E402
from aitalk.providers.base import ProviderError  # noqa: E402

SHARED = "# 토론 규칙\n규칙과 인물 설정"


class ApiError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status


def reply(text: str, rid: str, items=(), output=(), complete: bool = True, usage_in: int = 100):
    """스트림 하나를 이루는 이벤트 목록."""
    events = [NS(type="response.output_text.delta", delta=ch) for ch in ([text] if text else [])]
    events += [NS(type="response.output_item.done", item=item) for item in items]
    if complete:
        usage = NS(input_tokens=usage_in, output_tokens=10, input_tokens_details=NS(cached_tokens=0, cache_write_tokens=0))
        events.append(NS(type="response.completed", response=NS(id=rid, usage=usage, output=list(output))))
    return events


class FakeResponses:
    def __init__(self, script: list) -> None:
        self.script = script
        self.calls: list[dict] = []

    async def create(self, **kw):
        self.calls.append(kw)
        step = self.script.pop(0)
        if callable(step):
            step = step(kw)
        if isinstance(step, Exception):
            raise step

        async def stream():
            for event in step:
                if isinstance(event, Exception):
                    raise event
                yield event
        return stream()


class FakeClient:
    def __init__(self, script: list, compact=None) -> None:
        self.responses = FakeResponses(script)
        self.compact = compact
        self.posts: list[dict] = []

    async def post(self, path, *, cast_to=None, body=None):
        self.posts.append({"path": path, "body": body})
        result = self.compact(body) if callable(self.compact) else self.compact
        if isinstance(result, Exception):
            raise result
        return result


def make(script: list, compact=None, **ctx_kw):
    provider = pgpt.PgptProvider()
    provider.configured = True
    provider.client = FakeClient(script, compact)
    provider._secrets = ("sk-very-secret-key", "dG9rZW4tc2VjcmV0")
    ctx = provider.open_context(SHARED, search=ctx_kw.pop("search", False), max_searches=ctx_kw.pop("max_searches", 0),
                                compact_threshold=ctx_kw.pop("compact_threshold", 200_000))
    return provider, ctx, provider.client


def run(coro):
    return asyncio.run(coro)


async def say(ctx, who: str, events=None):
    seen = events if events is not None else []
    speech = await ctx.speak(speaker=who, directive="말하세요", private="", model="gpt-6-luna", effort="low",
                             on_event=lambda kind, payload: seen.append((kind, payload)))
    ctx.commit(who, speech)
    return speech


def texts(kw: dict) -> str:
    return "\n".join(str(item.get("content", "")) if isinstance(item, dict) else str(item) for item in kw["input"])


SCHEMA = {"type": "object", "properties": {"next": {"type": "string"}}, "required": ["next"]}


def test_speeches_chain_and_judge_branches_without_storing():
    provider, ctx, client = make([reply("첫 발언", "r1"), reply('{"next": "나래"}', "j1"), reply("둘째 발언", "r2")], search=True)

    async def go():
        await say(ctx, "가온")
        data, _ = await ctx.judge(question="다음은 누구?", schema=SCHEMA, model="gpt-6-luna", effort="low")
        await say(ctx, "나래")
        return data

    assert run(go()) == {"next": "나래"}
    first, judge, second = client.responses.calls
    assert first["store"] is True and "previous_response_id" not in first and SHARED in texts(first)
    assert first["tools"] == [{"type": "web_search"}]
    assert judge["store"] is False and judge["previous_response_id"] == "r1"
    assert "tools" not in judge                        # 판단에는 검색 도구를 넣지 않는다
    assert second["store"] is True and second["previous_response_id"] == "r1"   # 판단은 줄기에 남지 않는다
    assert ctx.head == "r2" and SHARED not in texts(second)


def test_lost_previous_response_rebuilds_from_the_apps_record():
    lost = ApiError(404, "Previous response with id 'r1' not found.")
    provider, ctx, client = make([reply("첫 발언", "r1"), lost, reply("둘째 발언", "r2")])

    async def go():
        await say(ctx, "가온")
        ctx.add_note("청중", "(청중 질문) 근거가 있나요?")
        return await say(ctx, "나래")

    assert run(go()).text == "둘째 발언"
    retry = client.responses.calls[2]
    assert "previous_response_id" not in retry
    body = texts(retry)
    assert SHARED in body and "【가온】 첫 발언" in body and "【청중】 (청중 질문) 근거가 있나요?" in body
    assert ctx.head == "r2" and ctx.entries[-1] == ("나래", "둘째 발언")


def test_overflow_uses_explicit_compact_then_continues():
    overflow = ApiError(400, "context_length_exceeded: input exceeds the context window")
    seed = [{"type": "compaction", "encrypted_content": "abc"}]
    provider, ctx, client = make([reply("첫 발언", "r1"), overflow, reply("둘째 발언", "r2"), reply("셋째 발언", "r3")],
                                 compact={"output": seed})

    async def go():
        await say(ctx, "가온")
        ctx.add_note("주최자 지시", "숫자로 말하세요")
        await say(ctx, "나래")
        await say(ctx, "가온")

    run(go())
    assert client.posts == [{"path": "/responses/compact", "body": {"model": "gpt-6-luna", "previous_response_id": "r1"}}]
    retry = client.responses.calls[2]
    assert "previous_response_id" not in retry and retry["input"][0] == seed[0]
    assert SHARED in texts(retry) and "숫자로 말하세요" in texts(retry)   # 규칙을 다시 알리고, 줄기에 못 들어간 지시도 잇는다
    assert ctx.compactions == 1
    after = client.responses.calls[3]
    assert after["previous_response_id"] == "r2" and seed[0] not in after["input"]


def test_compact_refusal_falls_back_to_summary_and_is_not_retried(monkeypatch):
    monkeypatch.setattr(pgpt, "KEEP_RECENT", 2)
    overflow = ApiError(400, "context_length_exceeded")
    script = [reply(f"발언 {i}", f"r{i}") for i in range(1, 6)]
    script += [overflow, reply("앞부분 요약입니다", "s1"), reply("여섯째", "r6"),
               reply("일곱째", "r7"), overflow, reply("더 긴 요약입니다", "s2"), reply("여덟째", "r8")]
    provider, ctx, client = make(script, compact=ApiError(403, "Forbidden"))

    async def go():
        for i in range(5):
            await say(ctx, "가온" if i % 2 == 0 else "나래")
        await say(ctx, "나래")
        await say(ctx, "가온")
        await say(ctx, "나래")

    run(go())
    assert len(client.posts) == 1 and provider.use_explicit_compact is False   # 거절당한 뒤로는 다시 부르지 않는다
    rebuilt = texts(client.responses.calls[7])
    assert "【앞부분 요약】 앞부분 요약입니다" in rebuilt and "발언 1" not in rebuilt
    assert "【가온】 발언 5" in rebuilt and SHARED in rebuilt                  # 최근 발언은 원문으로 남는다
    assert [text for _, text in ctx.entries][:2] == ["발언 1", "발언 2"]        # 앱의 원문 기록은 그대로다
    second_summary = texts(client.responses.calls[10])
    assert "앞부분 요약입니다" in second_summary and "발언 5" in second_summary   # 앞 요약에 이어서 쌓는다
    assert ctx.summary == "더 긴 요약입니다" and ctx.compactions == 2


def test_summary_runs_in_cumulative_batches(monkeypatch):
    monkeypatch.setattr(pgpt, "KEEP_RECENT", 1)
    monkeypatch.setattr(pgpt, "SUMMARY_BATCH", 2)
    script = [reply(f"발언 {i}", f"r{i}", usage_in=900) for i in range(1, 6)]
    script += [reply("요약 A", "s1"), reply("요약 B", "s2")]
    provider, ctx, client = make(script, compact_threshold=500)
    provider.use_compaction = False        # 자동 압축을 쓸 수 없는 서버
    provider.use_explicit_compact = False

    async def go():
        for _ in range(5):
            await say(ctx, "가온")
        return await ctx.maybe_compact("gpt-6-luna")

    assert run(go()) is True
    first, second = client.responses.calls[5], client.responses.calls[6]
    assert "발언 1" in texts(first) and "발언 2" in texts(first) and "발언 3" not in texts(first)
    assert "【앞부분 요약】 요약 A" in texts(second) and "발언 3" in texts(second) and "발언 4" in texts(second)
    assert ctx.summary == "요약 B" and ctx.folded == 4 and ctx.head is None and ctx.compactions == 1


@pytest.mark.parametrize("summary", [ApiError(500, "server error"), reply("   ", "s1")])
def test_failed_or_empty_summary_keeps_everything(monkeypatch, summary):
    monkeypatch.setattr(pgpt, "KEEP_RECENT", 1)
    overflow = ApiError(400, "context_length_exceeded")
    script = [reply(f"발언 {i}", f"r{i}") for i in range(1, 5)] + [overflow, summary]
    provider, ctx, client = make(script)
    provider.use_explicit_compact = False

    async def go():
        for _ in range(4):
            await say(ctx, "가온")
        await say(ctx, "나래")

    with pytest.raises(ProviderError):
        run(go())
    assert ctx.head == "r4" and ctx.summary == "" and ctx.folded == 0 and ctx.compactions == 0
    assert [text for _, text in ctx.entries] == ["발언 1", "발언 2", "발언 3", "발언 4"]


def test_cut_speech_keeps_only_the_confirmed_part():
    provider, ctx, client = make([reply("첫 발언", "r1"), reply("길게 이어지는 둘째 발언입니다", "r2"), reply("셋째", "r3")])

    async def go():
        await say(ctx, "가온")
        await say(ctx, "나래")
        ctx.amend_last("길게 이어지는 —")
        await say(ctx, "가온")

    run(go())
    third = client.responses.calls[2]
    assert third["previous_response_id"] == "r1"          # 끊긴 응답은 줄기에서 뺀다
    assert {"role": "assistant", "content": "길게 이어지는 —"} in third["input"]
    assert "둘째 발언입니다" not in texts(third)
    assert ctx.entries[1] == ("나래", "길게 이어지는 —")


def test_search_items_are_collected_once_from_stream_and_final_output():
    call = NS(type="web_search_call", id="ws_1", action=NS(type="search", queries=["철강 수출", "steel export"], query="철강 수출",
                                                          sources=[NS(url="https://news.example/a", title="")]))
    opened = NS(type="web_search_call", id="ws_2", action=NS(type="open_page", url="https://news.example/a"))
    message = NS(type="message", id="msg_1", content=[NS(annotations=[
        NS(type="url_citation", url="https://news.example/a", title="철강 수출 급증"),
        NS(type="url_citation", url="https://news.example/b", title="둘째 기사")])])
    provider, ctx, client = make([reply("검색한 발언", "r1", items=[call, opened, message], output=[call, opened, message])],
                                 search=True, max_searches=3)
    events: list = []
    speech = run(say(ctx, "가온", events))
    assert speech.usage.searches == 2                       # 스트림과 마지막 응답에 같은 항목이 와도 한 번만 센다
    assert [p for k, p in events if k == "search"] == ["철강 수출", "steel export", "https://news.example/a"]
    assert speech.sources == [{"title": "철강 수출 급증", "url": "https://news.example/a"},
                              {"title": "둘째 기사", "url": "https://news.example/b"}]
    assert client.responses.calls[0]["max_tool_calls"] == 3


def test_search_tool_name_falls_back_only_when_the_name_is_rejected():
    rejected = ApiError(400, "Invalid value: 'web_search'. Supported values are: 'web_search_preview'.")
    provider, ctx, client = make([rejected, reply("발언", "r1")], search=True)
    run(say(ctx, "가온"))
    assert client.responses.calls[1]["tools"] == [{"type": "web_search_preview"}]
    assert provider.search_tool == "web_search_preview"

    provider, ctx, client = make([ApiError(400, "Unsupported parameter: max_tool_calls"), reply("발언", "r1")],
                                 search=True, max_searches=2)
    run(say(ctx, "가온"))
    assert "max_tool_calls" not in client.responses.calls[1] and provider.search_tool == "web_search"


def test_auto_compaction_item_is_noticed_and_rules_are_restated():
    compaction = NS(type="compaction", id="cmp_1")
    provider, ctx, client = make([reply("첫 발언", "r1", output=[compaction]), reply("둘째", "r2")])

    async def go():
        await say(ctx, "가온")
        await say(ctx, "나래")

    run(go())
    assert client.responses.calls[0]["extra_body"] == {"context_management": [{"type": "compaction", "compact_threshold": 200_000}]}
    assert ctx.compactions == 1
    assert SHARED in texts(client.responses.calls[1])       # 압축 뒤 공통 규칙을 다시 전달한다


def test_unfinished_stream_is_not_a_confirmed_speech():
    provider, ctx, client = make([reply("말하다가", "r1", complete=False)])
    with pytest.raises(ProviderError, match="끝나기 전에"):
        run(say(ctx, "가온"))
    assert ctx.entries == [] and ctx.head is None


def test_request_that_already_emitted_text_is_not_resent():
    broken = [NS(type="response.output_text.delta", delta="이미 나간 글"), ApiError(400, "context_length_exceeded")]
    provider, ctx, client = make([broken, reply("다시", "r1")])
    with pytest.raises(ProviderError):
        run(say(ctx, "가온"))
    assert len(client.responses.calls) == 1                 # 같은 말을 두 번 내보내지 않는다


def test_error_messages_do_not_leak_secrets():
    leak = ApiError(500, 'upstream said: Authorization: Bearer dG9rZW4tc2VjcmV0 {"apiKey":"sk-very-secret-key"}')
    provider, ctx, client = make([leak])
    with pytest.raises(ProviderError) as caught:
        run(say(ctx, "가온"))
    message = str(caught.value)
    assert "sk-very-secret-key" not in message and "dG9rZW4tc2VjcmV0" not in message and "P-GPT 호출 실패" in message
