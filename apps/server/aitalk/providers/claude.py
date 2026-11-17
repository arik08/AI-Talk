"""Claude 프로바이더. 앱이 토론 기록을 들고 있고, 호출마다 통째로 보낸다.

캐시가 맞도록 요청을 다음 순서로 조립한다 (설계 문서 8.1).
  system: 규칙 + 전원 페르소나 + 자료            ← 캐시 지점
  user:   "【이름】 발언" 블록들 (하나씩 뒤에 붙음)  ← 마지막 블록이 캐시 지점
          꼬리: "지금 할 일" (호출마다 다름)
"""
from __future__ import annotations

import json
from typing import Any, Optional

import anthropic

from .. import prompts
from .base import (Context, ModelInfo, OnEvent, Provider, ProviderError, Speech, Usage,
                   clean_utterance, parse_json)

FALLBACK_BETA = "server-side-fallback-2026-07-01"
EFFORTS = ["low", "medium", "high", "xhigh", "max"]

# 100만 토큰당 달러. 설계 문서 7.3의 표와 같다.
PRICES = {
    "claude-fable-5-2": {"in": 8, "cached": 0.2, "write": 10, "out": 40},
    "claude-opus-5-5": {"in": 4, "cached": 0.2, "write": 5, "out": 20},
    "claude-sonnet-5-5": {"in": 2, "cached": 0.1, "write": 2.5, "out": 10},
    "claude-haiku-5-5": {"in": 0.1, "cached": 0.01, "write": 0.125, "out": 0.5},
}
LABELS = {
    "claude-fable-5-2": "Claude Fable 5.2", "claude-opus-5-5": "Claude Opus 5.5",
    "claude-sonnet-5-5": "Claude Sonnet 5.5", "claude-haiku-5-5": "Claude Haiku 5.5",
}


def _usage(u: Any) -> Usage:
    return Usage(
        input=getattr(u, "input_tokens", 0) or 0,
        cached=getattr(u, "cache_read_input_tokens", 0) or 0,
        cache_write=getattr(u, "cache_creation_input_tokens", 0) or 0,
        output=getattr(u, "output_tokens", 0) or 0,
    )


def _friendly(exc: Exception) -> ProviderError:
    if isinstance(exc, ProviderError):
        return exc
    if isinstance(exc, anthropic.AuthenticationError):
        return ProviderError("Claude 키가 올바르지 않습니다. .env의 ANTHROPIC_API_KEY를 확인하세요.")
    if isinstance(exc, anthropic.RateLimitError):
        return ProviderError("Claude 사용 한도에 걸렸습니다. 잠시 뒤 '이어 하기'를 누르세요.")
    if isinstance(exc, anthropic.APIConnectionError):
        return ProviderError("Claude 서버에 연결하지 못했습니다. 인터넷 연결을 확인하세요.")
    if isinstance(exc, anthropic.APIStatusError):
        return ProviderError(f"Claude 오류 ({exc.status_code}): {str(getattr(exc, 'message', exc))[:300]}")
    return ProviderError(f"Claude 호출 실패: {type(exc).__name__}: {str(exc)[:300]}")


class ClaudeProvider(Provider):
    name = "claude"
    default_model = "claude-opus-5-5"
    default_effort = "low"

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key
        self.client = anthropic.AsyncAnthropic(api_key=api_key) if api_key else None
        self.use_fallbacks = True   # 요청이 거절되면 다른 모델로 넘기는 설정. 안 받으면 끈다
        self.use_thinking = True
        self._models: Optional[list[ModelInfo]] = None

    def status(self) -> dict:
        if not self.client:
            return {"ready": False, "message": ".env에 ANTHROPIC_API_KEY가 없습니다."}
        return {"ready": True, "message": ""}

    async def list_models(self) -> list[ModelInfo]:
        if self._models is not None:
            return self._models
        ids = list(PRICES)
        try:
            page = await self.client.models.list(limit=100)
            seen = {m.id for m in page.data}
            ids = [i for i in ids if i in seen] or ids
        except Exception:  # noqa: BLE001 - 목록을 못 받아도 기본 목록으로 진행
            pass
        order = ["claude-opus-5-5", "claude-fable-5-2", "claude-sonnet-5-5", "claude-haiku-5-5"]
        self._models = [ModelInfo(i, LABELS[i], EFFORTS, "low", price=PRICES[i])
                        for i in order if i in ids]
        return self._models

    # ---- 요청 조립 ----
    def _kwargs(self, *, model: str, effort: str, system: Any, messages: list, max_tokens: int,
                tools: Optional[list] = None, schema: Optional[dict] = None) -> dict:
        output_config: dict = {"effort": effort}
        if schema:
            output_config["format"] = {"type": "json_schema", "schema": schema}
        kw: dict = {"model": model, "max_tokens": max_tokens, "system": system,
                    "messages": messages, "output_config": output_config}
        if self.use_thinking:
            kw["thinking"] = {"type": "adaptive", "display": "summarized"}
        if tools:
            kw["tools"] = tools
        if self.use_fallbacks:
            kw["betas"] = [FALLBACK_BETA]
            kw["extra_body"] = {"fallbacks": "default"}
        return kw

    def _degrade(self, exc: Exception) -> bool:
        """모델이나 SDK가 받지 않는 선택 항목을 끄고 다시 시도할 수 있으면 True."""
        if not isinstance(exc, anthropic.BadRequestError):
            return False
        msg = str(exc).lower()
        if self.use_fallbacks and ("fallback" in msg or "beta" in msg):
            self.use_fallbacks = False
            return True
        if self.use_thinking and "thinking" in msg:
            self.use_thinking = False
            return True
        return False

    async def _create(self, **params: Any) -> Any:
        for _ in range(3):
            try:
                return await self.client.beta.messages.create(**self._kwargs(**params))
            except Exception as exc:  # noqa: BLE001
                if self._degrade(exc):
                    continue
                raise _friendly(exc) from exc
        raise ProviderError("Claude 요청 설정을 맞추지 못했습니다.")

    async def _stream(self, on_event: OnEvent, **params: Any) -> Speech:
        """글자를 흘려보내며 받는다. 서버 도구가 중간에 멈추면(pause_turn) 이어서 받는다."""
        speech = Speech(model=params["model"])
        messages = list(params.pop("messages"))
        emitted = False
        for _ in range(6):
            try:
                final = await self._stream_once(on_event, speech, messages=messages, **params)
            except Exception as exc:  # noqa: BLE001
                if not emitted and not speech.text and self._degrade(exc):
                    continue
                raise _friendly(exc) from exc
            emitted = True
            speech.usage.add(_usage(final.usage))
            speech.model = getattr(final, "model", speech.model) or speech.model
            for block in final.content:
                if getattr(block, "type", "") == "text":
                    for c in getattr(block, "citations", None) or []:
                        url = getattr(c, "url", "")
                        if url and all(s["url"] != url for s in speech.sources):
                            speech.sources.append({"title": getattr(c, "title", "") or url, "url": url})
            if final.stop_reason == "pause_turn":
                messages = messages + [{"role": "assistant", "content": final.content}]
                continue
            if final.stop_reason == "refusal":
                raise ProviderError("모델이 이 요청에 답하기를 거절했습니다.")
            return speech
        return speech

    async def _stream_once(self, on_event: OnEvent, speech: Speech, **params: Any) -> Any:
        tool_json: dict[int, str] = {}
        async with self.client.beta.messages.stream(**self._kwargs(**params)) as stream:
            async for event in stream:
                kind = event.type
                if kind == "content_block_start":
                    if getattr(event.content_block, "type", "") == "server_tool_use":
                        tool_json[event.index] = ""
                elif kind == "content_block_delta":
                    dtype = event.delta.type
                    if dtype == "text_delta":
                        speech.text += event.delta.text
                        on_event("text", event.delta.text)
                    elif dtype == "thinking_delta":
                        speech.thinking += event.delta.thinking
                    elif dtype == "input_json_delta" and event.index in tool_json:
                        tool_json[event.index] += event.delta.partial_json
                elif kind == "content_block_stop" and event.index in tool_json:
                    try:
                        data = json.loads(tool_json.pop(event.index) or "{}")
                    except json.JSONDecodeError:
                        data = {}
                    query = data.get("query") or data.get("url") or ""
                    if query:
                        on_event("search", query)
            return await stream.get_final_message()

    # ---- Provider ----
    def open_context(self, shared: str, *, search: bool, max_searches: int,
                     compact_threshold: int) -> Context:
        return ClaudeContext(self, shared, search, max_searches, compact_threshold)

    async def generate_json(self, *, system: str, prompt: str, schema: dict,
                            model: str, effort: str) -> tuple[dict, Usage]:
        msg = await self._create(model=model, effort=effort, system=system, max_tokens=8000,
                                 messages=[{"role": "user", "content": prompt}], schema=schema)
        if msg.stop_reason == "refusal":
            raise ProviderError("모델이 이 요청에 답하기를 거절했습니다.")
        text = next((b.text for b in msg.content if b.type == "text"), "")
        return parse_json(text), _usage(msg.usage)

    async def generate_text(self, *, system: str, prompt: str, model: str,
                            effort: str) -> tuple[str, Usage]:
        msg = await self._create(model=model, effort=effort, system=system, max_tokens=4000,
                                 messages=[{"role": "user", "content": prompt}])
        text = "".join(b.text for b in msg.content if b.type == "text")
        return text.strip(), _usage(msg.usage)

    async def research(self, *, prompt: str, model: str, effort: str, on_event: OnEvent) -> Speech:
        tools = [{"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": 4},
                 {"type": "web_search_20260209", "name": "web_search", "max_uses": 4}]
        speech = await self._stream(lambda kind, payload: on_event(kind, payload) if kind == "search" else None,
                                    model=model, effort=effort, system=prompts.RESEARCH_SYSTEM,
                                    max_tokens=8000, tools=tools,
                                    messages=[{"role": "user", "content": prompt}])
        speech.text = speech.text.strip()
        return speech


class ClaudeContext(Context):
    def __init__(self, provider: ClaudeProvider, shared: str, search: bool,
                 max_searches: int, compact_threshold: int) -> None:
        self.p = provider
        self.shared = shared
        self.entries: list[tuple[str, str]] = []
        self.search = search
        self.max_searches = max_searches
        self.threshold = compact_threshold

    def _system(self) -> list:
        return [{"type": "text", "text": self.shared, "cache_control": {"type": "ephemeral"}}]

    def _tools(self) -> Optional[list]:
        if not self.search:
            return None
        return [{"type": "web_search_20260209", "name": "web_search", "max_uses": self.max_searches}]

    def _messages(self, tail: str) -> list:
        blocks: list[dict] = [{"type": "text", "text": "━━ 토론 기록 ━━"}]
        blocks += [{"type": "text", "text": f"【{who}】 {text}"} for who, text in self.entries]
        blocks[-1] = {**blocks[-1], "cache_control": {"type": "ephemeral"}}
        blocks.append({"type": "text", "text": tail})
        return [{"role": "user", "content": blocks}]

    async def speak(self, *, speaker: str, directive: str, private: str,
                    model: str, effort: str, on_event: OnEvent) -> Speech:
        tail = prompts.speaker_tail(speaker, directive, private)
        speech = await self.p._stream(on_event, model=model, effort=effort, system=self._system(),
                                      messages=self._messages(tail), max_tokens=6000,
                                      tools=self._tools())
        speech.text = clean_utterance(speech.text, speaker)
        self.last_input_tokens = speech.usage.total_input
        return speech

    def commit(self, speaker: str, speech: Speech) -> None:
        self.entries.append((speaker, speech.text))

    def amend_last(self, text: str) -> None:
        if self.entries:
            self.entries[-1] = (self.entries[-1][0], text)

    def add_note(self, speaker: str, text: str) -> None:
        self.entries.append((speaker, text))

    async def judge(self, *, question: str, schema: dict, model: str,
                    effort: str) -> tuple[dict, Usage]:
        msg = await self.p._create(model=model, effort=effort, system=self._system(),
                                   messages=self._messages(question), max_tokens=4000,
                                   tools=self._tools(), schema=schema)
        text = next((b.text for b in msg.content if b.type == "text"), "")
        return parse_json(text), _usage(msg.usage)

    async def maybe_compact(self, model: str) -> bool:
        """기록이 기준을 넘으면 앞부분을 요약으로 바꾼다.

        기록을 한 덩어리 대본으로 보내는 구조라 서버 압축(베타)이 맞지 않아 앱이 직접 줄인다.
        """
        if self.last_input_tokens <= self.threshold or len(self.entries) <= 8:
            return False
        older, recent = self.entries[:-6], self.entries[-6:]
        transcript = "\n".join(f"【{who}】 {text}" for who, text in older)
        summary, _ = await self.p.generate_text(system=prompts.COMPACT_SYSTEM,
                                                prompt=prompts.compact_prompt(transcript),
                                                model=model, effort="low")
        self.entries = [("앞부분 요약", summary)] + recent
        self.compactions += 1
        self.last_input_tokens = 0
        return True
