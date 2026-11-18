"""서버 API. 토론 진행은 SSE로 흘려보내고, 조작은 POST로 받는다.

기본은 내 PC(127.0.0.1)에서만 접속된다. .env에 AITALK_HOST=0.0.0.0을 두면 같은 망의 다른 PC도
들어올 수 있고, 그때 AITALK_ACCESS_CODE를 정해 두면 다른 PC에는 접속 코드를 묻는다.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import hmac
import json
from typing import Any, Optional

from fastapi import FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import console, materials, prompts, providers, source_titles, store
from .config import WEB_DIST, lan_addresses, settings
from .engine import Debate
from .providers import get_provider
from .providers.base import ProviderError

app = FastAPI(title="AI-Talk")
LIVE: dict[str, Debate] = {}

COMPACT_DEFAULT = {"pgpt": 200_000, "claude": 150_000, "mock": 150_000}


def _pass(code: str) -> str:
    """쿠키에 넣는 값. 접속 코드 자체는 쿠키에 두지 않는다 (한글 코드도 쓸 수 있게 해시로)."""
    return hashlib.sha256(("aitalk:" + code).encode("utf-8")).hexdigest()


def _is_local(request: Request) -> bool:
    return bool(request.client) and request.client.host in ("127.0.0.1", "::1", "localhost")


@app.middleware("http")
async def access_guard(request: Request, call_next):
    """다른 PC에서 온 요청에는 접속 코드를 확인한다. 코드를 정하지 않았으면 그냥 통과시킨다."""
    code = settings.get("AITALK_ACCESS_CODE")
    path = request.url.path
    if code and path.startswith("/api/") and path != "/api/enter" and not _is_local(request):
        given = request.cookies.get("aitalk_code", "")
        if not hmac.compare_digest(given, _pass(code)):
            return JSONResponse({"detail": "접속 코드가 필요합니다."}, status_code=401)
    return await call_next(request)


class EnterIn(BaseModel):
    code: str


@app.post("/api/enter")
async def enter(body: EnterIn, response: Response) -> dict:
    code = settings.get("AITALK_ACCESS_CODE")
    if code and not hmac.compare_digest(body.code.encode("utf-8"), code.encode("utf-8")):
        await asyncio.sleep(1)   # 마구 넣어 보는 것을 늦춘다
        raise HTTPException(401, "접속 코드가 맞지 않습니다.")
    response.set_cookie("aitalk_code", _pass(code), httponly=True, samesite="lax", max_age=60 * 60 * 24 * 30)
    return {"ok": True}


def _fail(exc: Exception, status: int = 502) -> HTTPException:
    return HTTPException(status_code=status, detail=str(exc))


# ---------------------------------------------------------------- 상태
@app.get("/api/status")
async def status() -> dict:
    provider = get_provider()
    info = provider.status()
    models: list[dict] = []
    if info["ready"]:
        try:
            models = [m.to_dict() for m in await provider.list_models()]
        except Exception as exc:  # noqa: BLE001
            info = {"ready": False, "message": str(exc)}
    return {
        "provider": provider.name, "ready": info["ready"], "message": info["message"],
        "models": models,
        "defaults": {
            "model": provider.default_model, "effort": provider.default_effort,
            "compact_threshold": COMPACT_DEFAULT.get(provider.name, 150_000),
            "hidden_agenda": provider.name != "pgpt",
        },
        "providers": providers.overview(),
        "pricing": {"usd_krw": settings.usd_krw, "search_usd": settings.search_usd},
        "network": {
            "shared": settings.host not in ("127.0.0.1", "localhost", "::1"),
            "port": settings.port,
            "addresses": lan_addresses() if settings.host not in ("127.0.0.1", "localhost", "::1") else [],
            "code": bool(settings.get("AITALK_ACCESS_CODE")),
        },
    }


class ProviderIn(BaseModel):
    name: str


@app.post("/api/provider")
async def provider_switch(body: ProviderIn) -> dict:
    """쓸 AI를 바꾼다. 마지막 선택을 기억한다. 진행 중인 토론은 시작할 때의 AI로 끝까지 간다."""
    if body.name not in providers.NAMES:
        raise HTTPException(400, "모르는 AI입니다.")
    providers.set_active(body.name)
    console.say(f"AI를 {providers.LABELS[body.name]}(으)로 바꿨습니다.", console.GOLD_HI)
    return await status()


# ---------------------------------------------------------------- 페르소나 보관함
class PersonaIn(BaseModel):
    id: Optional[str] = None
    name: str
    title: str = ""
    expertise: str = ""
    personality: str = ""
    speech: str = ""
    viewpoint: str = ""
    claims: list[str] = Field(default_factory=list)
    concede: str = ""
    hidden: str = ""
    color: str = ""
    avatar: dict = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)


@app.get("/api/personas")
async def personas() -> list[dict]:
    return store.list_personas()


@app.post("/api/personas")
async def persona_save(body: PersonaIn) -> dict:
    if not body.name.strip():
        raise HTTPException(400, "이름을 적어 주세요.")
    return store.save_persona(body.model_dump())


@app.delete("/api/personas/{persona_id}")
async def persona_delete(persona_id: str) -> dict:
    store.delete_persona(persona_id)
    return {"ok": True}


@app.post("/api/personas/import")
async def persona_import(items: list[dict]) -> dict:
    return {"added": store.import_personas(items)}


class DraftIn(BaseModel):
    hint: str


@app.post("/api/personas/draft")
async def persona_draft(body: DraftIn) -> dict:
    provider = get_provider()
    try:
        data, _ = await provider.generate_json(
            system=prompts.DRAFT_SYSTEM,
            prompt=f"한 줄 설명: {body.hint.strip()}\n\n참가자 1명을 만드세요.",
            schema=prompts.cast_schema(), model=provider.default_model, effort=provider.default_effort)
    except ProviderError as exc:
        raise _fail(exc) from exc
    people = data.get("personas") or []
    if not people:
        raise HTTPException(502, "인물을 만들지 못했습니다.")
    return people[0]


# ---------------------------------------------------------------- 참가자 자동 생성
class CastIn(BaseModel):
    topic: str
    concept: str = ""
    tone: str = "default"
    count: int = 4
    policy: str = "auto"
    fixed: list[dict] = Field(default_factory=list)
    materials: str = ""
    model: Optional[str] = None
    effort: Optional[str] = None


@app.post("/api/cast")
async def cast(body: CastIn) -> dict:
    if not body.topic.strip():
        raise HTTPException(400, "주제를 먼저 적어 주세요.")
    count = max(1, min(10, body.count))
    provider = get_provider()
    try:
        data, usage = await provider.generate_json(
            system=prompts.CAST_SYSTEM,
            prompt=prompts.cast_prompt(body.topic, count, body.policy, body.fixed[:count], body.materials,
                                       body.concept, body.tone),
            schema=prompts.cast_schema(), model=body.model or provider.default_model,
            effort=body.effort or provider.default_effort)
    except ProviderError as exc:
        raise _fail(exc) from exc
    people = (data.get("personas") or [])[:count]
    for i, fixed in enumerate(body.fixed[:count]):
        if i < len(people):   # 보관함에서 고른 인물은 인물 정보를 그대로 두고 입장만 새로 받는다
            for key in ("id", "name", "title", "expertise", "personality", "speech", "color", "avatar", "tags"):
                if fixed.get(key):
                    people[i][key] = fixed[key]
    used = body.model or provider.default_model
    price = next((m.price for m in await provider.list_models() if m.id == used), None)
    return {"personas": people, "usage": usage.to_dict(), "cost": round(usage.cost(price), 5)}


class CastLibraryIn(BaseModel):
    topic: str
    concept: str = ""
    tone: str = "default"
    count: int = 4
    policy: str = "auto"
    picked: list[str] = Field(default_factory=list)   # 사용자가 직접 고른 인물의 id. 남은 자리만 AI가 고른다
    materials: str = ""
    model: Optional[str] = None
    effort: Optional[str] = None


@app.post("/api/cast/library")
async def cast_from_library(body: CastLibraryIn) -> dict:
    """새로 만들지 않고, 보관함의 인물 가운데 주제에 어울리는 사람을 골라 입장만 주제에 맞춘다."""
    if not body.topic.strip():
        raise HTTPException(400, "주제를 먼저 적어 주세요.")
    library = [p for p in store.list_personas() if p.get("id") and p.get("name")]
    if len(library) < 2:
        raise HTTPException(400, "보관함에 인물이 2명 이상 있어야 합니다. 페르소나 메뉴에서 만들 수 있습니다.")
    count = max(2, min(10, body.count, len(library)))
    known = {p["id"] for p in library}
    picked = list(dict.fromkeys(pid for pid in body.picked if pid in known))[:count]
    provider = get_provider()
    used = body.model or provider.default_model
    try:
        data, usage = await provider.generate_json(
            system=prompts.PICK_SYSTEM,
            prompt=prompts.pick_prompt(body.topic, count, body.policy, library, body.materials, body.concept, body.tone,
                                       picked),
            schema=prompts.pick_schema(), model=used, effort=body.effort or provider.default_effort)
    except ProviderError as exc:
        raise _fail(exc) from exc
    people = prompts.merge_picks(data.get("personas") or [], library, count, picked)
    price = next((m.price for m in await provider.list_models() if m.id == used), None)
    return {"personas": people, "usage": usage.to_dict(), "cost": round(usage.cost(price), 5),
            "library": len(library), "asked": body.count}


# ---------------------------------------------------------------- 자료
@app.post("/api/materials")
async def material_upload(file: UploadFile = File(...)) -> dict:
    data = await file.read()
    if len(data) > 30 * 1024 * 1024:
        raise HTTPException(413, "30MB보다 큰 파일은 올릴 수 없습니다.")
    try:
        text = materials.extract_text(file.filename or "", data)
    except materials.MaterialError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"name": file.filename, "text": text, "chars": len(text),
            "tokens": materials.estimate_tokens(text)}


# ---------------------------------------------------------------- 출처 제목
class SourceTitlesIn(BaseModel):
    urls: list[str] = Field(default_factory=list)


@app.post("/api/source-titles")
async def source_title_lookup(body: SourceTitlesIn) -> dict:
    """출처 페이지의 실제 탭 제목을 한꺼번에 조회한다. 조회하지 못한 주소는 빈 문자열로 돌려준다."""
    if len(body.urls) > source_titles.MAX_URLS:
        raise HTTPException(400, f"한 번에 {source_titles.MAX_URLS}개까지 조회할 수 있습니다.")
    return {"titles": await source_titles.fetch_titles(body.urls)}


# ---------------------------------------------------------------- 토론
class DebateIn(BaseModel):
    topic: str
    concept: str = ""
    tone: str = "default"      # default | humorous | serious | creative
    participants: list[dict]
    materials: list[dict] = Field(default_factory=list)
    urls: list[str] = Field(default_factory=list)
    moderator: bool = True
    mode: str = "mixed"
    max_turns: Optional[int] = 30
    max_minutes: Optional[float] = 10
    length: str = "auto"       # auto | short | normal | long
    interjection: bool = True
    speed: str = "normal"
    gap_scale: float = 1.0
    search: str = "auto"
    max_searches: int = 2
    model: Optional[str] = None
    effort: Optional[str] = None
    badge: str = "on"
    language: str = "ko"
    summary: bool = True
    prep_cost: float = 0       # 토론을 시작하기 전에 든 비용(참가자 생성). 총 비용에 더한다
    reactions: str = "smart"
    hidden_agenda: Optional[bool] = None
    compact_threshold: Optional[int] = None


@app.post("/api/debates")
async def debate_start(body: DebateIn) -> dict:
    provider = get_provider()
    if not provider.status()["ready"]:
        raise HTTPException(400, provider.status()["message"])
    if not body.topic.strip():
        raise HTTPException(400, "주제를 적어 주세요.")
    if not 2 <= len(body.participants) <= 10:
        raise HTTPException(400, "참가자는 2명에서 10명 사이여야 합니다.")
    if not body.max_turns and not body.max_minutes:
        raise HTTPException(400, "턴 수와 시간 제한 가운데 하나는 켜야 합니다.")
    cfg = body.model_dump()
    cfg["model"] = body.model or provider.default_model
    cfg["effort"] = body.effort or provider.default_effort
    if cfg["hidden_agenda"] is None:
        cfg["hidden_agenda"] = provider.name != "pgpt"
    cfg["compact_threshold"] = body.compact_threshold or COMPACT_DEFAULT.get(provider.name, 150_000)
    seen: set[str] = set()
    for i, p in enumerate(cfg["participants"]):
        if not str(p.get("name", "")).strip():
            raise HTTPException(400, "이름이 없는 참가자가 있습니다.")
        pid = str(p.get("id") or f"s{i + 1}")
        if pid in seen or pid == "moderator":
            pid = f"s{i + 1}_{len(seen)}"
        seen.add(pid)
        p["id"] = pid
    debate = Debate(store.new_id("d"), cfg, provider)
    LIVE[debate.id] = debate
    debate.task = asyncio.create_task(debate.run())
    debate.task.add_done_callback(lambda _task, key=debate.id: _retire(key))
    console.say(f"토론 시작 · {cfg['topic'].strip()[:40]} · {len(cfg['participants'])}명 · {cfg['model']}", console.GOLD_HI)
    return {"id": debate.id}


def _retire(debate_id: str) -> None:
    """끝난 토론은 저장소에 있으므로 잠시 뒤 메모리에서 내보낸다. 서버를 오래 켜 두어도 쌓이지 않는다."""
    done = LIVE.get(debate_id)
    if done:
        console.say(f"토론 끝   · {done.cfg['topic'].strip()[:40]} · {done.turn_no}턴 · "
                    f"{round(done.cost * settings.usd_krw):,}원", console.MUTED)
    try:
        asyncio.get_running_loop().call_later(300, LIVE.pop, debate_id, None)
    except RuntimeError:
        LIVE.pop(debate_id, None)


@app.get("/api/debates")
async def debate_list() -> list[dict]:
    saved = store.list_debates()
    known = {r["id"] for r in saved}
    live = [{"id": d.id, "topic": d.cfg["topic"], "created": d.created, "state": d.state,
             "turns": d.turn_no, "seconds": round(d.clock), "provider": d.provider.name,
             "cost": round(d.cost, 4),
             "participants": [{"name": p["name"], "color": p.get("color"), "avatar": p.get("avatar")}
                              for p in d.people]}
            for d in LIVE.values() if d.id not in known]
    return sorted(live + saved, key=lambda r: r["created"], reverse=True)


@app.get("/api/debates/{debate_id}")
async def debate_get(debate_id: str) -> dict:
    live = LIVE.get(debate_id)
    if live and live.state in ("running", "paused", "error"):
        return {**live.record(), "live": True}
    record = store.load_debate(debate_id)
    if not record:
        raise HTTPException(404, "토론 기록을 찾지 못했습니다.")
    return {**record, "live": False}


@app.delete("/api/debates/{debate_id}")
async def debate_delete(debate_id: str) -> dict:
    live = LIVE.pop(debate_id, None)
    if live and live.task and not live.task.done():
        live.task.cancel()
        try:
            await live.task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass
    store.delete_debate(debate_id)
    return {"ok": True}


def _stamp(speeches: list[dict], events: list[dict]) -> None:
    """예전 기록에는 발언의 시작 시각이 없다. 토론 시계 이벤트로 채운다."""
    ends = {e["turn"]: e.get("seconds", 0) for e in events if e.get("type") == "clock" and "turn" in e}
    for s in speeches:
        if "at" not in s:
            s["at"] = round(ends.get(s["id"] - 1, 0))


@app.post("/api/debates/{debate_id}/minutes")
async def debate_minutes(debate_id: str) -> dict:
    """끝난 토론의 기록으로 회의록을 만들어 기록에 함께 저장한다."""
    live = LIVE.get(debate_id)
    if live and live.state in ("running", "paused", "error"):
        raise HTTPException(400, "토론이 끝난 뒤에 회의록을 만들 수 있습니다.")
    record = store.load_debate(debate_id)
    if not record:
        raise HTTPException(404, "토론 기록을 찾지 못했습니다.")
    speeches = record.get("speeches") or []
    if not speeches:
        raise HTTPException(400, "발언이 없어 회의록을 만들 수 없습니다.")
    provider = get_provider()
    cfg = record.get("config", {})
    models = {m.id: m for m in await provider.list_models()}
    model = cfg.get("model") if cfg.get("model") in models else provider.default_model
    effort = cfg.get("effort") if model in models and cfg.get("effort") in models[model].efforts else provider.default_effort
    people = [f"{p['name']}({p.get('title', '')})" for p in cfg.get("participants", [])]
    if record.get("moderator"):
        people.insert(0, "진행자")
    _stamp(speeches, record.get("events") or [])
    try:
        data, usage = await provider.generate_json(
            system=prompts.MINUTES_SYSTEM, prompt=prompts.minutes_prompt(cfg.get("topic", ""), people, speeches),
            schema=prompts.minutes_schema(), model=model, effort=effort)
    except ProviderError as exc:
        raise _fail(exc) from exc
    prompts.stamp_timeline(data, speeches, float(record.get("seconds") or 0))
    record["minutes"] = {**data, "model": model, "written": dt.datetime.now().isoformat(timespec="seconds")}
    # 회의록을 쓰는 데 든 비용을 총 비용에 더한다 (다시 쓰면 그만큼 더 쌓인다)
    parts = dict(record.get("cost_parts") or {"tokens": float(record.get("cost") or 0)})
    parts["minutes"] = round(parts.get("minutes", 0) + usage.cost(models[model].price if model in models else None), 5)
    record["cost_parts"] = parts
    record["cost"] = round(sum(parts.values()), 5)
    record.setdefault("pricing", {"usd_krw": settings.usd_krw, "search_usd": settings.search_usd})
    store.save_debate(record)
    return {"minutes": record["minutes"], "cost": record["cost"], "cost_parts": parts}


class ControlIn(BaseModel):
    action: str
    value: Any = None


@app.post("/api/debates/{debate_id}/control")
async def debate_control(debate_id: str, body: ControlIn) -> dict:
    debate = LIVE.get(debate_id)
    if not debate:
        raise HTTPException(404, "진행 중인 토론이 아닙니다.")
    debate.control(body.action, body.value)
    return {"state": debate.state}


@app.get("/api/debates/{debate_id}/events")
async def debate_events(debate_id: str, since: int = 0) -> StreamingResponse:
    debate = LIVE.get(debate_id)
    if not debate:
        raise HTTPException(404, "진행 중인 토론이 아닙니다.")

    async def stream():
        queue: asyncio.Queue = asyncio.Queue()
        backlog = debate.events[since:]
        debate.subs.add(queue)
        debate.viewer_joined()
        try:
            sent = since
            for event in backlog:
                sent = event["i"] + 1
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                if event["type"] == "end":
                    return
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                if event["i"] < sent:
                    continue
                sent = event["i"] + 1
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                if event["type"] == "end":
                    return
        finally:
            debate.subs.discard(queue)
            debate.viewer_left()

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/reload")
async def reload_settings() -> dict:
    settings.reload()
    return {"provider": settings.provider}


# ---------------------------------------------------------------- 화면 (빌드된 파일)
if WEB_DIST.exists():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    async def web(path: str) -> FileResponse:
        target = WEB_DIST / path
        if path and target.is_file() and WEB_DIST in target.resolve().parents:
            return FileResponse(target)
        return FileResponse(WEB_DIST / "index.html", headers={"Cache-Control": "no-cache"})
