"""서버 API. 토론 진행은 SSE로 흘려보내고, 조작은 POST로 받는다. 내 PC(127.0.0.1)에서만 쓴다."""
from __future__ import annotations

import asyncio
import json
from typing import Any, Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import materials, prompts, store
from .config import WEB_DIST, settings
from .engine import Debate
from .providers import get_provider
from .providers.base import ProviderError

app = FastAPI(title="AI-Talk")
LIVE: dict[str, Debate] = {}

COMPACT_DEFAULT = {"pgpt": 200_000, "claude": 150_000, "mock": 150_000}


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
    }


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
            prompt=prompts.cast_prompt(body.topic, count, body.policy, body.fixed[:count], body.materials),
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
    return {"personas": people, "usage": usage.to_dict()}


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


# ---------------------------------------------------------------- 토론
class DebateIn(BaseModel):
    topic: str
    participants: list[dict]
    materials: list[dict] = Field(default_factory=list)
    urls: list[str] = Field(default_factory=list)
    moderator: bool = True
    mode: str = "mixed"
    max_turns: Optional[int] = 30
    max_minutes: Optional[float] = 10
    length: str = "normal"
    interjection: bool = True
    speed: str = "normal"
    gap_scale: float = 1.0
    search: str = "off"
    max_searches: int = 2
    model: Optional[str] = None
    effort: Optional[str] = None
    badge: str = "on"
    language: str = "ko"
    summary: bool = True
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
    return {"id": debate.id}


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
        return FileResponse(WEB_DIST / "index.html")
