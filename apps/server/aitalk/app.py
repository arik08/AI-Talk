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
from typing import Any, Awaitable, Callable, Optional

from fastapi import FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import console, materials, prompts, providers, source_titles, store
from .config import WEB_DIST, lan_addresses, settings
from .engine import Debate
from .providers import get_provider
from .providers.base import JsonFeed, Provider, ProviderError

app = FastAPI(title="AI-Talk")
LIVE: dict[str, Debate] = {}
ACTIVE = ("running", "paused", "error")   # 토론이 돌고 있는 상태
_JOBS: set[asyncio.Task] = set()          # 끝난 토론에 대한 뒷일(회의록, 판정, 답변). 화면이 닫혀도 끝까지 하고 저장한다

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
    max_minutes: Optional[float] = 20
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
    _launch(debate)
    console.say(f"토론 시작 · {cfg['topic'].strip()[:40]} · {len(cfg['participants'])}명 · {cfg['model']}", console.GOLD_HI)
    return {"id": debate.id}


def _is_live(debate_id: str) -> bool:
    live = LIVE.get(debate_id)
    return bool(live and live.state in ACTIVE)


def _resumable(record: dict) -> bool:
    """끝까지 가지 못한 토론이고, 이어 가는 데 필요한 것이 저장되어 있는가."""
    return bool(record.get("resume")) and record.get("state") != "ended" and not _is_live(record.get("id", ""))


def _shown_state(debate_id: str, state: str) -> str:
    """기록에는 '진행 중'으로 남아 있는데 실제로는 돌고 있지 않으면 서버가 꺼지며 끊긴 것이다."""
    live = LIVE.get(debate_id)
    if live and live.state in ACTIVE:
        return live.state
    return "interrupted" if state in ACTIVE else state


def _launch(debate: Debate) -> None:
    LIVE[debate.id] = debate
    debate.task = asyncio.create_task(debate.run())
    debate.task.add_done_callback(lambda _task, key=debate.id: _retire(key, debate))


def _retire(debate_id: str, debate: Optional[Debate] = None) -> None:
    """끝난 토론은 저장소에 있으므로 잠시 뒤 메모리에서 내보낸다. 서버를 오래 켜 두어도 쌓이지 않는다."""
    done = LIVE.get(debate_id)
    if done:
        console.say(f"토론 끝   · {done.cfg['topic'].strip()[:40]} · {done.turn_no}턴 · "
                    f"{round(done.cost * settings.usd_krw):,}원", console.MUTED)
    def drop() -> None:
        if debate is None or LIVE.get(debate_id) is debate:   # 그 사이 이어 하기로 새로 올라온 토론은 건드리지 않는다
            LIVE.pop(debate_id, None)
    try:
        asyncio.get_running_loop().call_later(300, drop)
    except RuntimeError:
        drop()


@app.get("/api/debates")
async def debate_list() -> list[dict]:
    saved = store.list_debates()
    known = {r["id"] for r in saved}
    for row in saved:   # 돌고 있는 토론도 발언마다 저장되므로 목록에 함께 있다. 상태와 분량은 지금 값으로 보여 준다
        live = LIVE.get(row["id"])
        if live and live.state in ACTIVE:
            row.update(turns=live.turn_no, seconds=round(live.clock), cost=round(live.cost, 4))
        row["state"] = _shown_state(row["id"], row["state"])
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
    if live and live.state in ACTIVE:
        return {**live.record(), "live": True, "resume": None}
    record = store.load_debate(debate_id)
    if not record:
        raise HTTPException(404, "토론 기록을 찾지 못했습니다.")
    # 이어 가는 데 쓰는 값(자료 전문, 숨은 속내가 든 설정)은 화면으로 보내지 않는다
    return {**record, "live": False, "resume": None, "resumable": _resumable(record),
            "state": _shown_state(debate_id, record.get("state", ""))}


@app.post("/api/debates/{debate_id}/resume")
async def debate_resume(debate_id: str) -> dict:
    """서버가 꺼지거나 중단되어 끝까지 가지 못한 토론을, 마지막으로 끝난 발언 다음부터 이어 간다."""
    if _is_live(debate_id):
        return {"id": debate_id}
    record = store.load_debate(debate_id)
    if not record:
        raise HTTPException(404, "토론 기록을 찾지 못했습니다.")
    if not _resumable(record):
        raise HTTPException(400, "이어 갈 수 없는 토론입니다. 이미 끝났거나, 이어 가는 데 필요한 기록이 없습니다.")
    provider = get_provider()
    if not provider.status()["ready"]:
        raise HTTPException(400, provider.status()["message"])
    cfg = record["resume"]["cfg"]
    models = {m.id: m for m in await provider.list_models()}
    if cfg.get("model") not in models:   # 그때와 다른 AI로 바꿔 둔 경우: 지금 AI의 기본 모델로 이어 간다
        cfg["model"], cfg["effort"] = provider.default_model, provider.default_effort
        for person in cfg.get("participants") or []:
            person.pop("model", None)
            person.pop("effort", None)
    try:
        debate = Debate.restore(record, provider)
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(400, f"저장된 기록으로 토론을 다시 세우지 못했습니다. ({type(exc).__name__}: {exc})") from exc
    _launch(debate)
    console.say(f"토론 이어 하기 · {cfg['topic'].strip()[:40]} · {debate.turn_no}턴부터", console.GOLD_HI)
    return {"id": debate.id}


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


def _ndjson(work: Callable[[Callable[[dict], None]], Awaitable[dict]]) -> StreamingResponse:
    """오래 걸리는 일을 하면서 중간 결과를 한 줄에 JSON 하나씩 흘려보낸다. 마지막 줄은 done 또는 error다.

    화면이 닫혀 연결이 끊겨도 일은 끝까지 하고 저장한다 (이미 든 요금을 버리지 않는다).
    """
    queue: asyncio.Queue = asyncio.Queue()

    async def run() -> None:
        try:
            result = await work(queue.put_nowait)
            queue.put_nowait({"type": "done", **result})
        except ProviderError as exc:
            queue.put_nowait({"type": "error", "message": str(exc)})
        except Exception as exc:  # noqa: BLE001
            queue.put_nowait({"type": "error", "message": f"{type(exc).__name__}: {exc}"})
        queue.put_nowait(None)

    task = asyncio.create_task(run())
    _JOBS.add(task)
    task.add_done_callback(_JOBS.discard)

    async def stream():
        while True:
            item = await queue.get()
            if item is None:
                return
            yield json.dumps(item, ensure_ascii=False) + "\n"

    return StreamingResponse(stream(), media_type="application/x-ndjson",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


async def _finished(debate_id: str, doing: str) -> tuple[dict, Provider, str, str, Optional[dict]]:
    """끝난(또는 끊긴) 토론의 기록과, 그 기록을 읽힐 모델을 돌려준다."""
    if _is_live(debate_id):
        raise HTTPException(400, f"토론이 끝난 뒤에 {doing} 수 있습니다.")
    record = store.load_debate(debate_id)
    if not record:
        raise HTTPException(404, "토론 기록을 찾지 못했습니다.")
    if not record.get("speeches"):
        raise HTTPException(400, f"발언이 없어 {doing} 수 없습니다.")
    provider = get_provider()
    if not provider.status()["ready"]:
        raise HTTPException(400, provider.status()["message"])
    cfg = record.get("config", {})
    models = {m.id: m for m in await provider.list_models()}
    model = cfg.get("model") if cfg.get("model") in models else provider.default_model
    effort = cfg.get("effort") if model in models and cfg.get("effort") in models[model].efforts else provider.default_effort
    _stamp(record["speeches"], record.get("events") or [])
    return record, provider, model, effort, models[model].price if model in models else None


def _people(record: dict) -> list[str]:
    people = [f"{p['name']}({p.get('title', '')})" for p in record.get("config", {}).get("participants", [])]
    if record.get("moderator"):
        people.insert(0, "진행자")
    return people


def _commit(debate_id: str, part: str, usd: float, change: Callable[[dict], None]) -> dict:
    """기록을 다시 읽어 고친 뒤 저장한다. 든 비용을 항목에 더한다 (그 사이 다른 일이 저장한 것을 덮어쓰지 않게 다시 읽는다)."""
    record = store.load_debate(debate_id)
    if not record:
        raise ProviderError("그 사이 토론 기록이 지워졌습니다.")
    change(record)
    parts = dict(record.get("cost_parts") or {"tokens": float(record.get("cost") or 0)})
    parts[part] = round(parts.get(part, 0) + usd, 5)
    record["cost_parts"] = parts
    record["cost"] = round(sum(parts.values()), 5)
    record.setdefault("pricing", {"usd_krw": settings.usd_krw, "search_usd": settings.search_usd})
    store.save_debate(record)
    return record


@app.post("/api/debates/{debate_id}/minutes")
async def debate_minutes(debate_id: str) -> StreamingResponse:
    """끝난 토론의 기록으로 회의록을 만들어 기록에 함께 저장한다. 쓰는 대로 흘려보낸다."""
    record, provider, model, effort, price = await _finished(debate_id, "회의록을 만들")
    speeches, seconds = record["speeches"], float(record.get("seconds") or 0)

    async def work(push: Callable[[dict], None]) -> dict:
        feed = JsonFeed(lambda part: push({"type": "partial",
                                           "minutes": prompts.stamp_timeline(part, speeches, seconds)}))
        data, usage = await provider.generate_json(
            system=prompts.MINUTES_SYSTEM,
            prompt=prompts.minutes_prompt(record.get("config", {}).get("topic", ""), _people(record), speeches),
            schema=prompts.minutes_schema(), model=model, effort=effort, on_event=feed)
        prompts.stamp_timeline(data, speeches, seconds)
        minutes = {**data, "model": model, "written": dt.datetime.now().isoformat(timespec="seconds")}
        # 회의록을 쓰는 데 든 비용을 총 비용에 더한다 (다시 쓰면 그만큼 더 쌓인다)
        saved = _commit(debate_id, "minutes", usage.cost(price), lambda rec: rec.update(minutes=minutes))
        return {"minutes": minutes, "cost": saved["cost"], "cost_parts": saved["cost_parts"]}

    return _ndjson(work)


@app.post("/api/debates/{debate_id}/verdict")
async def debate_verdict(debate_id: str) -> StreamingResponse:
    """끝난 토론을 심사위원의 눈으로 판정한다: 누가 더 설득력 있었는지, 근거와 함께."""
    record, provider, model, effort, price = await _finished(debate_id, "판정할")
    names = [p["name"] for p in record.get("config", {}).get("participants", [])]

    async def work(push: Callable[[dict], None]) -> dict:
        feed = JsonFeed(lambda part: push({"type": "partial", "verdict": part}))
        data, usage = await provider.generate_json(
            system=prompts.VERDICT_SYSTEM,
            prompt=prompts.verdict_prompt(record.get("config", {}).get("topic", ""), names, record["speeches"]),
            schema=prompts.verdict_schema(), model=model, effort=effort, on_event=feed)
        verdict = {**prompts.clean_verdict(data, names), "model": model,
                   "written": dt.datetime.now().isoformat(timespec="seconds")}
        saved = _commit(debate_id, "extra", usage.cost(price), lambda rec: rec.update(verdict=verdict))
        return {"verdict": verdict, "cost": saved["cost"], "cost_parts": saved["cost_parts"]}

    return _ndjson(work)


class AskIn(BaseModel):
    question: str


@app.post("/api/debates/{debate_id}/ask")
async def debate_ask(debate_id: str, body: AskIn) -> StreamingResponse:
    """끝난 토론을 두고 묻고 답한다. 답하는 쪽은 참가자가 아니라, 함께 지켜본 분석가다."""
    question = body.question.strip()[:2000]
    if not question:
        raise HTTPException(400, "질문을 적어 주세요.")
    record, provider, model, effort, price = await _finished(debate_id, "물을")

    async def work(push: Callable[[dict], None]) -> dict:
        answer, usage = await provider.stream_text(
            system=prompts.analyst_context(record.get("config", {}).get("topic", ""), _people(record),
                                           record["speeches"], record.get("minutes"), record.get("verdict")),
            prompt=prompts.analyst_prompt(record.get("qa") or [], question), model=model, effort=effort,
            on_event=lambda kind, payload: push({"type": "delta", "text": payload}) if kind == "text" else None)
        if not answer.strip():
            raise ProviderError("모델이 빈 답을 돌려주었습니다.")
        item = {"q": question, "a": answer.strip(), "model": model,
                "at": dt.datetime.now().isoformat(timespec="seconds")}
        saved = _commit(debate_id, "extra", usage.cost(price),
                        lambda rec: rec.update(qa=[*(rec.get("qa") or []), item]))
        return {"qa": saved["qa"], "cost": saved["cost"], "cost_parts": saved["cost_parts"]}

    return _ndjson(work)


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
                if event["i"] >= 0:      # i가 -1인 것은 기록에 남기지 않는 임시 이벤트(쓰는 중인 회의록)
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
