"""P-GPT 프로바이더. Responses API를 상태 유지 방식으로 쓴다 (설계 문서 8.4, 8.5).

- 토론 줄기: 발언자 호출만 store=True + previous_response_id로 한 줄로 잇는다.
- 연출자: 줄기의 끝에서 갈라져 나온 곁가지. store=False, 검색 도구 없음, 줄기에 잇지 않는다.
- 끊긴 발언: 그 응답은 줄기에 잇지 않고, 화면에 확정된 데까지의 글만 다음 입력에 넣는다.
- 문맥 초과: context_management의 compaction으로 서버가 자동 압축한다. 그것이 안 되거나 그래도 넘치면
  /responses/compact를 직접 부르고, 그것도 안 되면 오래된 발언을 묶음별로 요약해 새 줄기를 세운다.
- 응답 ID를 서버가 찾지 못하면 앱이 가진 기록을 다시 넣어 새 줄기를 세운다.

회사 OA망에서만 동작한다. 서버가 받지 않는 선택 항목은 한 번 실패하면 끄고 대안으로 넘어간다.
scripts/check_pgpt.py, scripts/check_pgpt_context.py로 회사에서 점검한다.
"""
from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import urlsplit, urlunsplit

from .. import prompts
from .base import (Context, ModelInfo, OnEvent, Provider, ProviderError, Speech, Usage,
                   clean_utterance, fits, parse_json)

DEFAULT_BASE_URL = "http://pgpt.posco.com/s0la01-gpt/v1"
COMPANY_CODE = "30"
KEEP_RECENT = 6       # 요약으로 줄일 때 원문으로 남기는 최근 발언 수
SUMMARY_BATCH = 24    # 한 번에 요약하는 발언 수. 오래된 발언이 많으면 묶음마다 앞 요약에 이어 쓴다
NOT_CONFIGURED = ".env에 PGPT_API_KEY(또는 API_KEY)와 PGPT_EMPNO(또는 PGPT_SYSTEM_CODE, EMPLOYEE_NO)가 없습니다."

_FULL = ["none", "low", "medium", "high", "xhigh", "max"]
MODELS = [
    ModelInfo("gpt-6-luna", "GPT-6 Luna", _FULL, "medium",
              price={"in": 0.1, "cached": 0.01, "write": 0.125, "out": 0.5}),
    ModelInfo("gpt-6.1-sol", "GPT-6.1 Sol", _FULL[1:], "medium",
              price={"in": 2, "cached": 0.1, "write": 2.5, "out": 10}),
    ModelInfo("gpt-6.1-terra", "GPT-6.1 Terra", _FULL[1:], "medium",
              price={"in": 1, "cached": 0.05, "write": 1.25, "out": 5}),
]


class LostThread(ProviderError):
    """서버가 이전 응답을 찾지 못했다. 앱의 기록으로 줄기를 다시 세우면 된다."""


class ContextOverflow(ProviderError):
    """문맥이 모델의 한도를 넘었다. 줄인 뒤 다시 부르면 된다."""


def build_token(api_key: str, system_code: str, company_code: str = COMPANY_CODE) -> str:
    payload = json.dumps({"apiKey": api_key, "systemCode": system_code, "companyCode": company_code or COMPANY_CODE},
                         ensure_ascii=False, separators=(",", ":"))
    return base64.b64encode(payload.encode("utf-8")).decode("ascii")


def normalize_base_url(value: str) -> str:
    """끝점 이름이 붙은 주소도 받아 `/v1`에서 끝나는 주소로 맞춘다."""
    parts = urlsplit(value.strip())
    path = parts.path.rstrip("/")
    for suffix in ("/chat/completions", "/responses/compact", "/responses", "/models", "/embeddings"):
        if path.endswith(suffix):
            path = path[: -len(suffix)].rstrip("/")
    if not path.endswith("/v1"):
        path += "/v1"
    return urlunsplit((parts.scheme, parts.netloc, path, "", ""))


def _get(obj: Any, name: str, default: Any = None) -> Any:
    """SDK 객체와 dict를 같은 방식으로 읽는다."""
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _usage(u: Any) -> Usage:
    if u is None:
        return Usage()
    details = _get(u, "input_tokens_details")
    cached = _get(details, "cached_tokens", 0) or 0
    write = _get(details, "cache_write_tokens", 0) or 0
    total = _get(u, "input_tokens", 0) or 0
    return Usage(input=max(total - cached - write, 0), cached=cached, cache_write=write,
                 output=_get(u, "output_tokens", 0) or 0)


_BEARER = re.compile(r"(?i)\b(bearer)\s+\S+")
_KEY_FIELD = re.compile(r"(?i)(\"?(?:api[_-]?key|apikey|authorization|token|systemcode)\"?\s*[:=]\s*)\"?[^\s\",}]+\"?")
_LONG_TOKEN = re.compile(r"[A-Za-z0-9+/_=-]{40,}")


def scrub(text: str, secrets: tuple[str, ...] = ()) -> str:
    """오류 안내에 섞여 들어온 비밀값을 가린다."""
    out = text
    for secret in secrets:
        if secret and len(secret) >= 4:
            out = out.replace(secret, "***")
    out = _BEARER.sub(r"\1 ***", out)
    out = _KEY_FIELD.sub(r"\1***", out)
    return _LONG_TOKEN.sub("***", out)


def _is_lost(msg: str, status: int) -> bool:
    if "previous_response_not_found" in msg:
        return True
    return ("previous_response" in msg or "previous response" in msg) and ("not found" in msg or status == 404)


def _is_overflow(msg: str) -> bool:
    return any(key in msg for key in ("context_length_exceeded", "context window", "context length",
                                      "maximum context", "exceeds the context", "input is too long"))


@dataclass
class _Run:
    """응답 하나를 받는 동안의 상태."""
    speech: Speech
    compacted: bool = False
    searches: int = 0
    completed: bool = False
    seen: set = field(default_factory=set)


def _text_only(on_event: Optional[OnEvent]) -> OnEvent:
    if on_event is None:
        return lambda *_: None
    return lambda kind, payload: on_event(kind, payload) if kind == "text" else None


class PgptProvider(Provider):
    name = "pgpt"
    default_model = "gpt-6-luna"
    default_effort = "medium"

    def __init__(self, api_key: str = "", system_code: str = "", company_code: str = COMPANY_CODE,
                 base_url: str = "", search_tool: str = "") -> None:
        self.configured = bool(api_key and system_code)
        self.client = None
        self._secrets: tuple[str, ...] = ()
        if self.configured:
            from openai import AsyncOpenAI
            token = build_token(api_key, system_code, company_code)
            self._secrets = (api_key, token)
            self.client = AsyncOpenAI(api_key=token, base_url=normalize_base_url(base_url or DEFAULT_BASE_URL))
        # 서버가 받지 않는 것으로 드러나면 끄는 선택 항목
        self.use_compaction = True          # 요청마다 붙이는 자동 압축 설정
        self.use_explicit_compact = True    # /responses/compact 직접 호출
        self.use_schema = True
        self.use_max_tool_calls = True
        self.search_tool = search_tool or "web_search"
        self._models: Optional[list[ModelInfo]] = None

    def status(self) -> dict:
        if not self.configured:
            return {"ready": False, "message": NOT_CONFIGURED}
        return {"ready": True, "message": "P-GPT는 회사 OA망에서만 연결됩니다."}

    def _friendly(self, exc: Exception) -> ProviderError:
        if isinstance(exc, ProviderError):
            return exc
        name = type(exc).__name__
        if "Connection" in name or "Timeout" in name:
            return ProviderError("P-GPT 서버에 연결하지 못했습니다. 회사 OA망에서만 쓸 수 있습니다.")
        if "Authentication" in name or getattr(exc, "status_code", 0) == 401:
            return ProviderError("P-GPT 인증에 실패했습니다. " + NOT_CONFIGURED.replace("가 없습니다.", "를 확인하세요."),
                                 retry=False)
        return ProviderError(f"P-GPT 호출 실패: {name}: {scrub(str(exc), self._secrets)[:300]}")

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
    def _base(self, *, model: str, effort: str, store: bool, search: bool, max_searches: int = 0,
              compact_threshold: int = 0, schema: Optional[dict] = None) -> dict:
        kw: dict = {"model": model, "store": store, "reasoning": {"effort": effort}}
        if search:
            kw["tools"] = [{"type": self.search_tool}]
            if max_searches and self.use_max_tool_calls:
                kw["max_tool_calls"] = max_searches
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
        if getattr(exc, "status_code", 0) not in (400, 404, 422) or _is_lost(msg, 0) or _is_overflow(msg):
            return False
        if "max_tool_calls" in msg and "max_tool_calls" in kw:
            self.use_max_tool_calls = False
            kw.pop("max_tool_calls", None)
            return True
        if ("context_management" in msg or "compaction" in msg) and self.use_compaction and "extra_body" in kw:
            self.use_compaction = False
            kw.pop("extra_body", None)
            return True
        # 검색 도구의 이름을 받지 않을 때만 예전 이름으로 바꿔 본다
        if kw.get("tools") and self.search_tool == "web_search" and ("web_search" in msg or "tools[0]" in msg):
            self.search_tool = "web_search_preview"
            kw["tools"] = [{"type": self.search_tool}]
            return True
        if ("json_schema" in msg or "text.format" in msg) and self.use_schema and "text" in kw:
            self.use_schema = False
            kw.pop("text", None)
            return True
        return False

    @staticmethod
    def _add_source(speech: Speech, url: str, title: str = "") -> None:
        if not url:
            return
        for known in speech.sources:
            if known["url"] == url:
                if title and known["title"] == url:
                    known["title"] = title
                return
        speech.sources.append({"title": title or url, "url": url})

    def _take(self, item: Any, run: _Run, on_event: OnEvent) -> None:
        """출력 항목 하나를 읽는다. 스트림 이벤트와 마지막 응답 양쪽에서 같은 항목이 와도 한 번만 센다."""
        kind = _get(item, "type", "")
        key = _get(item, "id") or f"{kind}:{_get(item, 'action', '')}:{str(_get(item, 'content', ''))[:200]}"
        if key in run.seen:
            return
        run.seen.add(key)
        if kind == "web_search_call":
            run.searches += 1
            action = _get(item, "action")
            what = _get(action, "type", "search")
            if what == "open_page":
                label = _get(action, "url", "") or ""
            elif what in ("find", "find_in_page"):
                label = _get(action, "pattern", "") or ""
            else:
                queries = [q for q in (_get(action, "queries") or []) if q] or [_get(action, "query", "") or ""]
                label = ""
                for query in queries:
                    if query:
                        on_event("search", query)
            if label:
                on_event("search", label)
            for src in _get(action, "sources") or []:
                self._add_source(run.speech, _get(src, "url", "") or "", _get(src, "title", "") or "")
            for src in _get(item, "results") or []:
                self._add_source(run.speech, _get(src, "url", "") or "", _get(src, "title", "") or "")
        elif kind == "compaction":
            run.compacted = True
        elif kind == "message":
            for part in _get(item, "content") or []:
                for ann in _get(part, "annotations") or []:
                    self._add_source(run.speech, _get(ann, "url", "") or "", _get(ann, "title", "") or "")

    async def _run(self, on_event: OnEvent, kw: dict) -> tuple[Speech, bool]:
        """글자를 흘려보내며 응답 하나를 받는다. (발언, 압축이 일어났는지)를 돌려준다.

        끝까지 오지 않은 응답은 성공으로 치지 않는다. 글자를 이미 내보낸 요청은 다시 보내지 않는다
        (같은 말이 두 번 나오게 된다).
        """
        for _ in range(5):
            run = _Run(Speech(model=kw["model"]))
            speech = run.speech
            try:
                stream = await self.client.responses.create(stream=True, **kw)
                async for event in stream:
                    kind = _get(event, "type", "")
                    if kind == "response.output_text.delta":
                        speech.text += event.delta
                        on_event("text", event.delta)
                    elif kind == "response.output_item.done":
                        self._take(event.item, run, on_event)
                    elif kind == "response.completed":
                        response = event.response
                        run.completed = True
                        speech.handle = {"id": _get(response, "id")}
                        speech.usage = _usage(_get(response, "usage"))
                        for item in _get(response, "output") or []:
                            self._take(item, run, on_event)
                    elif kind == "response.incomplete":
                        reason = _get(_get(_get(event, "response"), "incomplete_details"), "reason", "") or "알 수 없음"
                        raise ProviderError(f"P-GPT가 응답을 끝까지 만들지 못했습니다 ({scrub(str(reason), self._secrets)[:80]}).")
                    elif kind in ("response.failed", "error"):
                        detail = _get(_get(event, "response"), "error") or _get(event, "message", "") or _get(event, "error", "")
                        text = scrub(str(detail), self._secrets)
                        if not speech.text and _is_overflow(text.lower()):
                            raise ContextOverflow("대화가 모델의 문맥 한도를 넘었습니다.")
                        raise ProviderError(f"P-GPT가 응답을 만들지 못했습니다: {text[:200]}")
                if not run.completed:
                    raise ProviderError("P-GPT 응답이 끝나기 전에 연결이 끊겼습니다.")
                speech.usage.searches = run.searches
                return speech, run.compacted
            except ProviderError:
                raise
            except Exception as exc:  # noqa: BLE001
                if not speech.text:
                    if self._degrade(exc, kw):
                        continue
                    msg, status = str(exc).lower(), getattr(exc, "status_code", 0)
                    if kw.get("previous_response_id") and _is_lost(msg, status):
                        raise LostThread("P-GPT 서버가 앞의 대화를 찾지 못했습니다.") from exc
                    if _is_overflow(msg):
                        raise ContextOverflow("대화가 모델의 문맥 한도를 넘었습니다.") from exc
                raise self._friendly(exc) from exc
        raise ProviderError("P-GPT 요청 설정을 맞추지 못했습니다.")

    async def compact_thread(self, model: str, previous_response_id: str) -> list:
        """`/responses/compact`를 직접 불러 압축된 입력 항목들을 받는다.

        권한이 없거나 끝점이 없으면 이 프로바이더에서는 다시 시도하지 않는다.
        """
        if not self.use_explicit_compact:
            raise ProviderError("명시적 압축을 쓸 수 없습니다.")
        import httpx
        try:
            res = await self.client.post("/responses/compact", cast_to=httpx.Response,
                                         body={"model": model, "previous_response_id": previous_response_id})
        except Exception as exc:  # noqa: BLE001
            if getattr(exc, "status_code", 0) in (401, 403, 404, 405):
                self.use_explicit_compact = False
            raise self._friendly(exc) from exc
        data = res.json() if hasattr(res, "json") else res
        output = _get(data, "output") or []
        if not output:
            raise ProviderError("압축 결과가 비어 있습니다.")
        return list(output)

    # ---- Provider ----
    def open_context(self, shared: str, *, search: bool, max_searches: int,
                     compact_threshold: int) -> Context:
        return PgptContext(self, shared, search, compact_threshold, max_searches)

    async def generate_json(self, *, system: str, prompt: str, schema: dict,
                            model: str, effort: str,
                            on_event: Optional[OnEvent] = None) -> tuple[dict, Usage]:
        kw = self._base(model=model, effort=effort, store=False, search=False, schema=schema)
        kw["input"] = [{"role": "developer", "content": system},
                       {"role": "user", "content": prompt + "\n\n정해진 JSON 형식으로만 답하세요."}]
        speech, _ = await self._run(_text_only(on_event), kw)
        return parse_json(speech.text), speech.usage

    async def stream_text(self, *, system: str, prompt: str, model: str, effort: str,
                          on_event: OnEvent) -> tuple[str, Usage]:
        kw = self._base(model=model, effort=effort, store=False, search=False)
        kw["input"] = [{"role": "developer", "content": system}, {"role": "user", "content": prompt}]
        speech, _ = await self._run(_text_only(on_event), kw)
        return speech.text.strip(), speech.usage

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


REMIND = "(앞부분이 압축되었습니다. 규칙과 인물 설정을 다시 알립니다.)\n"


class PgptContext(Context):
    def __init__(self, provider: PgptProvider, shared: str, search: bool,
                 compact_threshold: int, max_searches: int = 0) -> None:
        self.p = provider
        self.shared = shared
        self.search = search
        self.max_searches = max_searches
        self.threshold = compact_threshold
        self.head: Optional[str] = None            # 줄기의 마지막 응답 ID
        self.pending: list[dict] = []              # 다음 호출의 입력 앞에 넣을 항목
        self.entries: list[tuple[str, str]] = []   # 앱이 가진 원문 기록. 줄이지 않는다
        self.seed: list = []                       # 명시적 압축이 돌려준 항목. 새 줄기의 첫 입력 앞에 넣는다
        self.summary = ""                          # entries[:folded]를 대신하는 누적 요약
        self.folded = 0
        self._remind = False                       # 압축 뒤 규칙과 페르소나를 다시 넣을지
        self._last: Optional[dict] = None

    def _input(self, tail: str) -> list[dict]:
        items: list[dict] = []
        if self.head is None and self.seed:
            # 명시적 압축으로 받은 문맥에서 새 줄기를 시작한다
            items += self.seed
            items.append({"role": "developer", "content": REMIND + self.shared})
            items += self.pending
        elif self.head is None:
            items.append({"role": "developer", "content": self.shared})
            lines = [f"【앞부분 요약】 {self.summary}"] if self.summary else []
            lines += [f"【{who}】 {text}" for who, text in self.entries[self.folded:]]
            if lines:   # 서버 문맥 없이 다시 세우는 경우: 앱의 기록을 넣는다
                items.append({"role": "user", "content": "━━ 지금까지의 토론 기록 ━━\n" + "\n".join(lines)})
        else:
            if self._remind:
                items.append({"role": "developer", "content": REMIND + self.shared})
            items += self.pending
        items.append({"role": "user", "content": tail})
        return items

    async def _call(self, on_event: OnEvent, tail: str, *, model: str, effort: str,
                    store: bool, search: bool, schema: Optional[dict] = None) -> tuple[Speech, bool]:
        for _ in range(4):
            kw = self.p._base(model=model, effort=effort, store=store, search=search,
                              max_searches=self.max_searches, compact_threshold=self.threshold, schema=schema)
            kw["input"] = self._input(tail)
            if self.head:
                kw["previous_response_id"] = self.head
            try:
                return await self.p._run(on_event, kw)
            except LostThread:
                # 서버가 이전 응답을 찾지 못하면 앱의 기록으로 새 줄기를 세운다
                self.head, self.pending, self.seed = None, [], []
            except ContextOverflow:
                if not await self._shrink(model):
                    raise
        raise ProviderError("P-GPT 문맥을 다시 세우지 못했습니다.")

    async def _shrink(self, model: str) -> bool:
        """문맥을 줄인다. 명시적 압축 → 묶음별 누적 요약 순서로 시도한다. 줄였으면 True."""
        if self.head and self.p.use_explicit_compact:
            try:
                seed = await self.p.compact_thread(model, self.head)
            except ProviderError:
                seed = []
            if seed:
                self.seed, self.head = seed, None   # 아직 줄기에 들어가지 않은 pending은 그대로 둔다
                self.compactions += 1
                self.last_input_tokens = 0
                return True
        return await self._summarize(model)

    async def _summarize(self, model: str) -> bool:
        """오래된 발언을 묶음별로 요약해 새 줄기를 세울 준비를 한다.

        요약이 실패하거나 비어 있으면 아무것도 바꾸지 않는다 (원문과 복구에 쓸 값을 지우지 않는다).
        """
        target = len(self.entries) - KEEP_RECENT
        if target - self.folded < 2:
            return False
        summary, at = self.summary, self.folded
        while at < target:
            batch = self.entries[at:min(at + SUMMARY_BATCH, target)]
            lines = [f"【앞부분 요약】 {summary}"] if summary else []
            lines += [f"【{who}】 {text}" for who, text in batch]
            try:
                text, _ = await self.p.generate_text(system=prompts.COMPACT_SYSTEM,
                                                     prompt=prompts.compact_prompt("\n".join(lines)),
                                                     model=model, effort="low")
            except ProviderError:
                return False
            if not text.strip():
                return False
            summary, at = text.strip(), at + len(batch)
        self.summary, self.folded = summary, target
        self.head, self.pending, self.seed = None, [], []
        self.compactions += 1
        self.last_input_tokens = 0
        return True

    async def maybe_compact(self, model: str) -> bool:
        """서버의 자동 압축을 쓸 수 없을 때만 앱이 기준을 보고 직접 줄인다."""
        if self.p.use_compaction or not self.threshold or self.last_input_tokens <= self.threshold:
            return False
        return await self._shrink(model)

    async def speak(self, *, speaker: str, directive: str, private: str,
                    model: str, effort: str, on_event: OnEvent) -> Speech:
        tail = prompts.pgpt_directive(speaker, directive, private)
        speech, compacted = await self._call(on_event, tail, model=model, effort=effort, store=True,
                                             search=self.search)
        speech.text = clean_utterance(speech.text, speaker)
        # 호출 도중 줄기를 다시 세웠을 수 있으므로 "앞 응답"은 호출이 끝난 뒤의 값으로 적는다
        speech.handle = {**(speech.handle or {}), "prev": self.head, "tail": tail, "compacted": compacted}
        self.last_input_tokens = speech.usage.total_input
        return speech

    def commit(self, speaker: str, speech: Speech) -> None:
        self.entries.append((speaker, speech.text))
        handle = speech.handle or {}
        if handle.get("id"):
            self.head = handle["id"]
            self.pending = []
            self.seed = []
            self._last = handle
            self._remind = bool(handle.get("compacted"))
            if handle.get("compacted"):
                self.compactions += 1

    def amend_last(self, text: str) -> None:
        if not self.entries:
            return
        self.entries[-1] = (self.entries[-1][0], text)
        last = self._last
        if last and last.get("id") == self.head:
            # 끊긴 발언의 응답은 줄기에서 빼고, 그 앞 응답에 "지시문 + 끊긴 데까지의 글"을 잇는다
            self.head = last.get("prev")
            self.pending = [{"role": "user", "content": last.get("tail", "")},
                            {"role": "assistant", "content": text}]

    def add_note(self, speaker: str, text: str) -> None:
        self.entries.append((speaker, text))
        self.pending.append({"role": "user", "content": f"【{speaker}】 {text}"})

    async def judge(self, *, question: str, schema: dict, model: str,
                    effort: str, on_event: Optional[OnEvent] = None) -> tuple[dict, Usage]:
        # 곁가지: 저장하지 않고 검색 도구도 넣지 않는다. 판단 내용이 토론 줄기에 남지 않는다.
        # 먼저 틀 없이 부르고, 안 읽히면 틀을 걸어 다시 부른다.
        # on_event를 주면(회의록) 만들어지는 글을 그대로 흘려보낸다.
        speech, _ = await self._call(_text_only(on_event), question, model=model, effort=effort,
                                     store=False, search=False)
        usage = speech.usage
        try:
            data = parse_json(speech.text)
            if fits(data, schema):
                return data, usage
        except (ProviderError, ValueError):
            pass
        tail = question
        if not self.p.use_schema:
            tail += "\n\n다음 JSON 형식으로만 답하세요:\n" + json.dumps(schema, ensure_ascii=False)
        if on_event:
            on_event("reset", None)
        speech, _ = await self._call(_text_only(on_event), tail, model=model, effort=effort,
                                     store=False, search=False, schema=schema)
        usage.add(speech.usage)
        return parse_json(speech.text), usage

    def snapshot(self) -> dict:
        return {"head": self.head, "compaction": self.p.use_compaction,
                "explicit_compact": self.p.use_explicit_compact, "search_tool": self.p.search_tool,
                "folded": self.folded}
