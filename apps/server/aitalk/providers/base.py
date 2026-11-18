"""프로바이더 공통 틀.

엔진은 "토론 문맥(Context)"에 일을 시킨다. 문맥을 앱이 들고 있는지(Claude),
서버가 들고 있는지(P-GPT)는 프로바이더 안에 숨긴다. 설계 문서 7.2 참고.
"""
from __future__ import annotations

import abc
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

OnEvent = Callable[[str, Any], None]


class ProviderError(Exception):
    """사용자에게 그대로 보여 줄 수 있는 오류.

    retry가 False면 다시 불러도 같은 결과다(키가 틀림, 모델이 거절함). 엔진이 자동으로 다시 시도하지 않는다.
    """

    def __init__(self, *args: Any, retry: bool = True) -> None:
        super().__init__(*args)
        self.retry = retry


@dataclass
class ModelInfo:
    id: str
    label: str
    efforts: list[str]
    default_effort: str
    search: bool = True
    price: Optional[dict] = None  # 100만 토큰당 달러: in, cached, write, out
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id, "label": self.label, "efforts": self.efforts,
            "default_effort": self.default_effort, "search": self.search,
            "price": self.price, "note": self.note,
        }


@dataclass
class Usage:
    input: int = 0        # 캐시를 쓰지 않은 입력
    cached: int = 0       # 캐시에서 읽은 입력
    cache_write: int = 0  # 캐시에 새로 쓴 입력
    output: int = 0
    searches: int = 0     # 웹 검색 건수 (건당 요금이 따로 붙는다)

    def add(self, other: "Usage") -> None:
        self.input += other.input
        self.cached += other.cached
        self.cache_write += other.cache_write
        self.output += other.output
        self.searches += other.searches

    @property
    def total_input(self) -> int:
        return self.input + self.cached + self.cache_write

    def cost(self, price: Optional[dict]) -> float:
        """토큰 요금(달러). 웹 검색 요금은 건수에 단가를 곱해 따로 더한다."""
        if not price:
            return 0.0
        return (
            self.input * price.get("in", 0)
            + self.cached * price.get("cached", 0)
            + self.cache_write * price.get("write", price.get("in", 0) * 1.25)
            + self.output * price.get("out", 0)
        ) / 1_000_000

    def to_dict(self) -> dict:
        return {"input": self.input, "cached": self.cached,
                "cache_write": self.cache_write, "output": self.output, "searches": self.searches}


@dataclass
class Speech:
    text: str = ""
    thinking: str = ""
    sources: list[dict] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    model: str = ""
    handle: Any = None  # 프로바이더가 쓰는 값 (P-GPT의 응답 ID 등)


class Context(abc.ABC):
    """토론 하나의 대화 문맥."""

    compactions: int = 0
    last_input_tokens: int = 0

    @abc.abstractmethod
    async def speak(self, *, speaker: str, directive: str, private: str,
                    model: str, effort: str, on_event: OnEvent) -> Speech:
        """발언을 만든다. 확정(commit)하기 전에는 문맥에 들어가지 않는다."""

    @abc.abstractmethod
    def commit(self, speaker: str, speech: Speech) -> None:
        """발언을 문맥에 넣는다."""

    @abc.abstractmethod
    def amend_last(self, text: str) -> None:
        """마지막으로 확정한 발언을 끊긴 데까지의 글로 바꾼다."""

    @abc.abstractmethod
    def add_note(self, speaker: str, text: str) -> None:
        """모델이 만들지 않은 줄(청중 질문 등)을 문맥에 넣는다."""

    @abc.abstractmethod
    async def judge(self, *, question: str, schema: dict, model: str,
                    effort: str, on_event: Optional[OnEvent] = None) -> tuple[dict, Usage]:
        """문맥을 바꾸지 않는 곁가지 호출. 정해진 틀의 JSON을 받는다.

        on_event를 주면 만들어지는 글을 ("text", 조각)으로 흘려보낸다. 처음부터 다시 받게 되면 ("reset", None)을 보낸다.
        """

    def restore(self, entries: list) -> None:
        """끊긴 토론을 이어 갈 때, 앱이 가진 기록으로 문맥을 다시 채운다."""
        for speaker, text in entries:
            self.add_note(str(speaker), str(text))

    async def maybe_compact(self, model: str) -> bool:
        """문맥이 기준을 넘으면 줄인다. 줄였으면 True."""
        return False

    def snapshot(self) -> dict:
        return {}


class Provider(abc.ABC):
    name: str = ""
    default_model: str = ""
    default_effort: str = "medium"

    @abc.abstractmethod
    async def list_models(self) -> list[ModelInfo]: ...

    @abc.abstractmethod
    def open_context(self, shared: str, *, search: bool, max_searches: int,
                     compact_threshold: int) -> Context: ...

    @abc.abstractmethod
    async def generate_json(self, *, system: str, prompt: str, schema: dict,
                            model: str, effort: str,
                            on_event: Optional[OnEvent] = None) -> tuple[dict, Usage]:
        """정해진 틀의 JSON을 받는다. on_event를 주면 만들어지는 글을 ("text", 조각)으로 흘려보낸다."""

    @abc.abstractmethod
    async def generate_text(self, *, system: str, prompt: str, model: str,
                            effort: str) -> tuple[str, Usage]: ...

    async def stream_text(self, *, system: str, prompt: str, model: str, effort: str,
                          on_event: OnEvent) -> tuple[str, Usage]:
        """글을 만들어지는 대로 ("text", 조각)으로 흘려보내며 받는다. 기본은 다 받은 뒤 한 번에 내보낸다."""
        text, usage = await self.generate_text(system=system, prompt=prompt, model=model, effort=effort)
        on_event("text", text)
        return text, usage

    @abc.abstractmethod
    async def research(self, *, prompt: str, model: str, effort: str,
                       on_event: OnEvent) -> Speech:
        """웹 도구를 써서 조사한 글을 돌려준다."""

    def status(self) -> dict:
        return {"ready": True, "message": ""}


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def parse_json(text: str) -> dict:
    """모델이 준 글에서 JSON 객체를 꺼낸다."""
    cleaned = _FENCE.sub("", text.strip())
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start >= 0 and end > start:
            return json.loads(cleaned[start:end + 1])
        raise ProviderError("모델이 정해진 형식(JSON)으로 답하지 않았습니다.")


_CLOSE = {"{": "}", "[": "]"}
_HALF_ESCAPE = re.compile(r"(\\+)(u[0-9a-fA-F]{0,3})?$")


def partial_json(text: str) -> Optional[dict]:
    """아직 다 오지 않은 JSON에서 지금까지 온 만큼을 읽는다. 읽을 것이 없으면 None.

    쓰이고 있는 글(값 문자열)은 온 데까지 보여 주고, 쓰다 만 키나 낱말은 그 앞의 온전한 값까지만 읽는다.
    """
    start = text.find("{")
    if start < 0:
        return None
    s = text[start:]
    stack: list[str] = []
    in_str = esc = is_key = expect_key = False
    safe: Optional[tuple[int, tuple]] = None    # 온전한 값이 끝난 자리와 그때 열려 있던 괄호
    for i, ch in enumerate(s):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
                if not is_key:
                    safe = (i + 1, tuple(stack))
        elif ch == '"':
            in_str, is_key = True, expect_key
        elif ch in "{[":
            stack.append(ch)
            expect_key = ch == "{"
        elif ch in "}]":
            if not stack:
                break
            stack.pop()
            expect_key = False
            safe = (i + 1, tuple(stack))
            if not stack:
                break
        elif ch == ",":
            expect_key = bool(stack) and stack[-1] == "{"
        elif ch == ":":
            expect_key = False

    def closed(body: str, opened: tuple) -> Optional[dict]:
        try:
            data = json.loads(body + "".join(_CLOSE[c] for c in reversed(opened)))
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, dict) else None

    if in_str and not is_key:
        tail = _HALF_ESCAPE.search(s)   # 쓰다 만 이스케이프(\ 하나, \u00)는 떼어 낸다. 역슬래시가 짝수면 온전한 글자다
        body = s[: tail.end(1) - 1] if tail and len(tail.group(1)) % 2 else s
        data = closed(body + '"', tuple(stack))
        if data is not None:
            return data
    if safe:
        data = closed(s[: safe[0]], safe[1])
        if data is not None:
            return data
    return {}


class JsonFeed:
    """흘러나오는 JSON 글을 모아, 지금까지 읽히는 만큼을 일정한 간격으로 push에 넘긴다 (회의록을 쓰는 대로 보여 줄 때)."""

    def __init__(self, push: Callable[[dict], None], every: float = 0.2) -> None:
        self.push = push
        self.every = every
        self.text = ""
        self._last = 0.0

    def __call__(self, kind: str, payload: Any) -> None:
        if kind == "reset":      # 처음부터 다시 받는다
            self.text = ""
            return
        if kind != "text":
            return
        self.text += str(payload)
        now = time.monotonic()
        if now - self._last < self.every:
            return
        data = partial_json(self.text)
        if data:
            self._last = now
            self.push(data)


def fits(data: object, schema: dict) -> bool:
    """틀을 걸지 않고 받은 JSON이 쓸 만한지 본다: 필수 항목이 있고, 목록은 목록인지."""
    if not isinstance(data, dict):
        return False
    props = schema.get("properties", {})
    for key in schema.get("required", []):
        if key not in data:
            return False
        if props.get(key, {}).get("type") == "array" and not isinstance(data[key], list):
            return False
    return True


def clean_utterance(text: str, speaker: str = "") -> str:
    """발언 앞에 붙은 이름표나 따옴표를 떼어 낸다."""
    out = text.strip()
    out = re.sub(r"^【[^】]{0,40}】\s*", "", out)
    if speaker:
        out = re.sub(rf"^{re.escape(speaker)}\s*[:：]\s*", "", out)
    if len(out) >= 2 and out[0] in "\"“'「" and out[-1] in "\"”'」":
        out = out[1:-1].strip()
    return out
