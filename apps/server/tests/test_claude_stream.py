"""검색 도구가 있을 때 글을 붙들었다가 흘려보내는 규칙."""
import asyncio
from types import SimpleNamespace as NS

from aitalk.providers.base import Speech
from aitalk.providers.claude import HOLD_CHARS, ClaudeProvider


def start(index, btype):
    return NS(type="content_block_start", index=index, content_block=NS(type=btype))


def text(index, piece):
    return NS(type="content_block_delta", index=index, delta=NS(type="text_delta", text=piece))


class FakeStream:
    def __init__(self, events):
        self.events = events

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def __aiter__(self):
        async def walk():
            for event in self.events:
                yield event
        return walk()

    async def get_final_message(self):
        return NS()


def run(events, tools=True):
    fake = NS(client=NS(beta=NS(messages=NS(stream=lambda **kw: FakeStream(events)))), _kwargs=lambda **kw: kw)
    speech, sent = Speech(model="m"), []
    asyncio.run(ClaudeProvider._stream_once(
        fake, lambda kind, payload: sent.append((kind, payload)), speech, tools=[{}] if tools else None))
    return speech, [payload for kind, payload in sent if kind == "text"]


def test_long_text_streams_before_the_block_ends():
    pieces = ["가" * 30] * 5
    speech, sent = run([start(0, "text")] + [text(0, p) for p in pieces])
    assert speech.text == "".join(pieces)
    assert len(sent) > 1                      # 한 덩어리로 몰아서 내보내지 않는다
    assert len(sent[0]) >= HOLD_CHARS         # 앞머리만 붙들었다가
    assert sent[-1] == pieces[-1]             # 그 뒤로는 받는 대로 내보낸다


def test_short_words_before_a_search_are_dropped():
    speech, sent = run([start(0, "text"), text(0, "자료를 찾아보겠습니다."), start(1, "server_tool_use"),
                        start(2, "text"), text(2, "찾아본 결과입니다.")])
    assert speech.text == "찾아본 결과입니다."
    assert sent == ["찾아본 결과입니다."]


def test_without_tools_every_piece_goes_out_at_once():
    speech, sent = run([start(0, "text"), text(0, "하나"), text(0, "둘")], tools=False)
    assert sent == ["하나", "둘"]
