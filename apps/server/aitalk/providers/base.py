"""프로바이더 공통 틀.

엔진은 "토론 문맥(Context)"에 일을 시킨다. 문맥을 앱이 들고 있는지(Claude),
서버가 들고 있는지(P-GPT)는 프로바이더 안에 숨긴다. 설계 문서 7.2 참고.
"""
from __future__ import annotations

import abc
import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

OnEvent = Callable[[str, Any], None]


class ProviderError(Exception):
    """사용자에게 그대로 보여 줄 수 있는 오류."""


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

    def add(self, other: "Usage") -> None:
        self.input += other.input
        self.cached += other.cached
        self.cache_write += other.cache_write
        self.output += other.output

    @property
    def total_input(self) -> int:
        return self.input + self.cached + self.cache_write

    def cost(self, price: Optional[dict]) -> float:
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
                "cache_write": self.cache_write, "output": self.output}


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
                    effort: str) -> tuple[dict, Usage]:
        """문맥을 바꾸지 않는 곁가지 호출. 정해진 틀의 JSON을 받는다."""

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
                            model: str, effort: str) -> tuple[dict, Usage]: ...

    @abc.abstractmethod
    async def generate_text(self, *, system: str, prompt: str, model: str,
                            effort: str) -> tuple[str, Usage]: ...

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
