"""P-GPT 프로바이더. Responses API를 상태 유지 방식으로 쓴다 (설계 문서 8.4, 8.5).

- 토론 줄기: 발언자 호출만 store=True + previous_response_id로 한 줄로 잇는다.
- 연출자: 줄기의 끝에서 갈라져 나온 곁가지. store=False, 줄기에 잇지 않는다.
- 끊긴 발언: 그 응답은 줄기에 잇지 않고, 끊긴 데까지의 글을 다음 입력에 넣는다.
- 문맥 초과: context_management의 compaction으로 서버가 자동 압축한다.

회사 OA망에서만 동작하므로 집에서는 실행해 보지 못했다. 서버가 받지 않는 선택 항목은
한 번 실패하면 끄고 대안으로 넘어가게 했다. scripts/check_pgpt.py로 회사에서 점검한다.
"""
from __future__ import annotations

import base64
import json
from typing import Any, Optional
from urllib.parse import urlsplit, urlunsplit

from .. import prompts
from .base import (Context, ModelInfo, OnEvent, Provider, ProviderError, Speech, Usage,
                   clean_utterance, parse_json)

DEFAULT_BASE_URL = "http://pgpt.posco.com/s0la01-gpt/v1"
COMPANY_CODE = "30"

_FULL = ["none", "low", "medium", "high", "xhigh", "max"]
MODELS = [
    ModelInfo("gpt-6-luna", "GPT-6 Luna", _FULL, "medium",
              price={"in": 0.1, "cached": 0.01, "write": 0.125, "out": 0.5}),
    ModelInfo("gpt-6.1-sol", "GPT-6.1 Sol", _FULL[1:], "medium",
              price={"in": 2, "cached": 0.1, "write": 2.5, "out": 10}),
    ModelInfo("gpt-6.1-terra", "GPT-6.1 Terra", _FULL[1:], "medium",
              price={"in": 1, "cached": 0.05, "write": 1.25, "out": 5}),
]


def build_token(api_key: str, system_code: str) -> str:
    payload = json.dumps({"apiKey": api_key, "systemCode": system_code, "companyCode": COMPANY_CODE},
                         ensure_ascii=False, separators=(",", ":"))
    return base64.b64encode(payload.encode("utf-8")).decode("ascii")


def normalize_base_url(value: str) -> str:
    parts = urlsplit(value.strip())
    path = parts.path.rstrip("/")
    for suffix in ("/chat/completions", "/responses", "/models", "/embeddings"):
        if path.endswith(suffix):
            path = path[: -len(suffix)]
    return urlunsplit((parts.scheme, parts.netloc, path.rstrip("/"), "", ""))


def _usage(u: Any) -> Usage:
    if u is None:
        return Usage()
    details = getattr(u, "input_tokens_details", None)
    cached = getattr(details, "cached_tokens", 0) or 0
    write = getattr(details, "cache_write_tokens", 0) or 0
    total = getattr(u, "input_tokens", 0) or 0
    return Usage(input=max(total - cached - write, 0), cached=cached, cache_write=write,
                 output=getattr(u, "output_tokens", 0) or 0)


def _friendly(exc: Exception) -> ProviderError:
    if isinstance(exc, ProviderError):
        return exc
    name = type(exc).__name__
    if "Connection" in name or "Timeout" in name:
        return ProviderError("P-GPT 서버에 연결하지 못했습니다. 회사 OA망에서만 쓸 수 있습니다.")
    if "Authentication" in name:
        return ProviderError("P-GPT 인증에 실패했습니다. .env의 PGPT_API_KEY와 PGPT_EMPNO를 확인하세요.")
    return ProviderError(f"P-GPT 호출 실패: {name}: {str(exc)[:300]}")


class PgptProvider(Provider):
    name = "pgpt"
    default_model = "gpt-6-luna"
    default_effort = "medium"

    def __init__(self, api_key: str, empno: str, system_code: str = "", base_url: str = "",
                 search_tool: str = "") -> None:
        self.configured = bool(api_key and (system_code or empno))
        self.client = None
        if self.configured:
            from openai import AsyncOpenAI
            self.client = AsyncOpenAI(api_key=build_token(api_key, system_code or empno),
                                      base_url=normalize_base_url(base_url or DEFAULT_BASE_URL))
        # 서버가 받지 않는 것으로 드러나면 끄는 선택 항목
        self.use_compaction = True
        self.use_schema = True
        self.search_tool = search_tool or "web_search"
        self._models: Optional[list[ModelInfo]] = None

    def status(self) -> dict:
        if not self.configured:
            return {"ready": False, "message": ".env에 PGPT_API_KEY와 PGPT_EMPNO가 없습니다."}
        return {"ready": True, "message": "P-GPT는 회사 OA망에서만 연결됩니다."}

    async def list_models(self) -> list[ModelInfo]:
        if self._models is not None:
            return self._models
        models = list(MODELS)
        try:
            page = await self.client.models.list()
            seen = {m.id for m in page.data}
            available = [m for m in models if m.id in seen]
            if available:
                models = available
            else:
                for m in models:
                    m.note = "P-GPT 모델 목록에서 찾지 못했습니다"
        except Exception:  # noqa: BLE001 - 목록을 못 받아도 정해 둔 세 모델로 진행
            pass
        self._models = models
        return models

    # ---- 요청 ----
    def _base(self, *, model: str, effort: str, store: bool, search: bool,
              compact_threshold: int = 0, schema: Optional[dict] = None) -> dict:
        kw: dict = {"model": model, "store": store, "reasoning": {"effort": effort}}
        if search:
            kw["tools"] = [{"type": self.search_tool}]
        if schema and self.use_schema:
            kw["text"] = {"format": {"type": "json_schema", "name": "result",
                                     "schema": schema, "strict": True}}
        if compact_threshold and self.use_compaction:
            kw["extra_body"] = {"context_management": [
                {"type": "compaction", "compact_threshold": compact_threshold}]}
        return kw

    def _degrade(self, exc: Exception, kw: dict) -> bool:
        """서버가 받지 않는 선택 항목을 끄고 다시 시도할 수 있으면 True."""
        msg = str(exc).lower()
        if getattr(exc, "status_code", 0) not in (400, 404, 422):
            return False
        if "context_management" in msg or "compaction" in msg:
            if self.use_compaction:
                self.use_compaction = False
                kw.pop("extra_body", None)
                return True
        if "web_search" in msg or "tool" in msg:
            if self.search_tool == "web_search" and kw.get("tools"):
                self.search_tool = "web_search_preview"
                kw["tools"] = [{"type": self.search_tool}]
                return True
        if ("json_schema" in msg or "text.format" in msg) and self.use_schema and "text" in kw:
            self.use_schema = False
            kw.pop("text", None)
            return True
        return False

    async def _run(self, on_event: OnEvent, kw: dict) -> tuple[Speech, bool]:
        """글자를 흘려보내며 응답 하나를 받는다. (발언, 압축이 일어났는지)를 돌려준다."""
        for _ in range(4):
            speech = Speech(model=kw["model"])
            compacted = False
            try:
                stream = await self.client.responses.create(stream=True, **kw)
                async for event in stream:
                    kind = getattr(event, "type", "")
                    if kind == "response.output_text.delta":
                        speech.text += event.delta
                        on_event("text", event.delta)
                    elif kind == "response.output_item.done":
                        item = event.item
                        itype = getattr(item, "type", "")
                        if itype == "web_search_call":
                            action = getattr(item, "action", None)
                            query = getattr(action, "query", "") or ""
                            if query:
                                on_event("search", query)
                        elif itype == "compaction":
                            compacted = True
                        elif itype == "message":
                            for part in getattr(item, "content", None) or []:
                                for ann in getattr(part, "annotations", None) or []:
                                    url = getattr(ann, "url", "")
                                    if url and all(s["url"] != url for s in speech.sources):
                                        speech.sources.append(
                                            {"title": getattr(ann, "title", "") or url, "url": url})
                    elif kind == "response.completed":
                        speech.handle = {"id": event.response.id}
                        speech.usage = _usage(getattr(event.response, "usage", None))
                    elif kind in ("response.failed", "error"):
                        detail = getattr(getattr(event, "response", None), "error", None) or getattr(event, "message", "")
                        raise ProviderError(f"P-GPT가 응답을 만들지 못했습니다: {str(detail)[:200]}")
                return speech, compacted
            except ProviderError:
                raise
            except Exception as exc:  # noqa: BLE001
                if not speech.text and self._degrade(exc, kw):
                    continue
                raise _friendly(exc) from exc
        raise ProviderError("P-GPT 요청 설정을 맞추지 못했습니다.")

    # ---- Provider ----
    def open_context(self, shared: str, *, search: bool, max_searches: int,
                     compact_threshold: int) -> Context:
        return PgptContext(self, shared, search, compact_threshold)

    async def generate_json(self, *, system: str, prompt: str, schema: dict,
                            model: str, effort: str) -> tuple[dict, Usage]:
        kw = self._base(model=model, effort=effort, store=False, search=False, schema=schema)
        kw["input"] = [{"role": "developer", "content": system},
                       {"role": "user", "content": prompt + "\n\n정해진 JSON 형식으로만 답하세요."}]
        speech, _ = await self._run(lambda *_: None, kw)
        return parse_json(speech.text), speech.usage

    async def generate_text(self, *, system: str, prompt: str, model: str,
                            effort: str) -> tuple[str, Usage]:
        kw = self._base(model=model, effort=effort, store=False, search=False)
        kw["input"] = [{"role": "developer", "content": system}, {"role": "user", "content": prompt}]
        speech, _ = await self._run(lambda *_: None, kw)
        return speech.text.strip(), speech.usage

    async def research(self, *, prompt: str, model: str, effort: str, on_event: OnEvent) -> Speech:
        kw = self._base(model=model, effort=effort, store=False, search=True)
        kw["input"] = [{"role": "developer", "content": prompts.RESEARCH_SYSTEM},
                       {"role": "user", "content": prompt}]
        speech, _ = await self._run(lambda kind, payload: on_event(kind, payload) if kind == "search" else None, kw)
        speech.text = speech.text.strip()
        return speech


class PgptContext(Context):
    def __init__(self, provider: PgptProvider, shared: str, search: bool,
                 compact_threshold: int) -> None:
        self.p = provider
        self.shared = shared
        self.search = search
        self.threshold = compact_threshold
        self.head: Optional[str] = None            # 줄기의 마지막 응답 ID
        self.pending: list[dict] = []              # 다음 호출의 입력 앞에 넣을 항목
        self.entries: list[tuple[str, str]] = []   # 앱이 가진 기록. 서버 문맥을 잃으면 이걸로 다시 세운다
        self._remind = False                       # 압축 뒤 규칙과 페르소나를 다시 넣을지

    def _input(self, tail: str) -> list[dict]:
        items: list[dict] = []
        if self.head is None:
            items.append({"role": "developer", "content": self.shared})
            if self.entries:   # 서버 문맥 없이 다시 세우는 경우: 앱의 기록을 통째로 넣는다
                script = "\n".join(f"【{who}】 {text}" for who, text in self.entries)
                items.append({"role": "user", "content": "━━ 지금까지의 토론 기록 ━━\n" + script})
        else:
            if self._remind:
                items.append({"role": "developer",
                              "content": "(앞부분이 압축되었습니다. 규칙과 인물 설정을 다시 알립니다.)\n" + self.shared})
            items += self.pending
        items.append({"role": "user", "content": tail})
        return items

    async def _call(self, on_event: OnEvent, tail: str, *, model: str, effort: str,
                    store: bool, schema: Optional[dict] = None) -> tuple[Speech, bool]:
        for attempt in range(2):
            # 연출자 호출(JSON 틀)에는 검색 도구를 넣지 않는다
            kw = self.p._base(model=model, effort=effort, store=store, search=self.search and not schema,
                              compact_threshold=self.threshold, schema=schema)
            kw["input"] = self._input(tail)
            if self.head:
                kw["previous_response_id"] = self.head
            try:
                return await self.p._run(on_event, kw)
            except ProviderError as exc:
                # 서버가 이전 응답을 찾지 못하면 앱의 기록으로 새 줄기를 세운다
                if attempt == 0 and self.head and "previous" in str(exc).lower():
                    self.head = None
                    self.pending = []
                    continue
                raise
        raise ProviderError("P-GPT 문맥을 다시 세우지 못했습니다.")

    async def speak(self, *, speaker: str, directive: str, private: str,
                    model: str, effort: str, on_event: OnEvent) -> Speech:
        tail = prompts.pgpt_directive(speaker, directive, private)
        prev_head = self.head
        speech, compacted = await self._call(on_event, tail, model=model, effort=effort, store=True)
        speech.text = clean_utterance(speech.text, speaker)
        speech.handle = {**(speech.handle or {}), "prev": prev_head, "tail": tail, "compacted": compacted}
        self.last_input_tokens = speech.usage.total_input
        return speech

    def commit(self, speaker: str, speech: Speech) -> None:
        self.entries.append((speaker, speech.text))
        handle = speech.handle or {}
        if handle.get("id"):
            self.head = handle["id"]
            self.pending = []
            self._last = handle
            self._remind = bool(handle.get("compacted"))
            if handle.get("compacted"):
                self.compactions += 1

    def amend_last(self, text: str) -> None:
        if not self.entries:
            return
        self.entries[-1] = (self.entries[-1][0], text)
        last = getattr(self, "_last", None)
        if last and last.get("id") == self.head:
            # 끊긴 발언의 응답은 줄기에서 빼고, 그 앞 응답에 "지시문 + 끊긴 데까지의 글"을 잇는다
            self.head = last.get("prev")
            self.pending = [{"role": "user", "content": last.get("tail", "")},
                            {"role": "assistant", "content": text}]

    def add_note(self, speaker: str, text: str) -> None:
        self.entries.append((speaker, text))
        self.pending.append({"role": "user", "content": f"【{speaker}】 {text}"})

    async def judge(self, *, question: str, schema: dict, model: str,
                    effort: str) -> tuple[dict, Usage]:
        tail = question
        if not self.p.use_schema:
            tail += "\n\n다음 JSON 형식으로만 답하세요:\n" + json.dumps(schema, ensure_ascii=False)
        speech, _ = await self._call(lambda *_: None, tail, model=model, effort=effort,
                                     store=False, schema=schema)
        return parse_json(speech.text), speech.usage

    def snapshot(self) -> dict:
        return {"head": self.head, "compaction": self.p.use_compaction}
