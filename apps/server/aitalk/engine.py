"""토론 엔진.

흐름: 준비(자료 조사) → 개회 → 모두발언 → 자유토론 → 마무리 발언 → 진행자 정리.

발언 하나의 수명
  1. 만들기: 프로바이더가 글을 만들어 버퍼에 채운다. 앞 발언이 화면에 나오는 동안 미리 만든다.
  2. 보여 주기: 서버가 정해진 박자로 화면에 내보낸다(어절 단위, 쉼표와 문장 끝에서 멈춤).
  3. 확정: 화면에 나오기 시작한 발언만 문맥에 넣는다. 미리 만들었다가 버린 발언은 들어가지 않는다.
  4. 다음 정하기: 확정되면 연출자가 전원의 발언 의지를 매기고, 규칙을 더해 다음 발언자를 고른다.
     끼어들기로 정해지면 지금 발언을 문장 끝에서 끊는다.

토큰을 미리 써 두지 않는다
  - 화면에 나오는 발언보다 한 발언만 앞서 만든다.
  - 그것도 앞 발언이 끝나기 직전에 맞춰 만든다. 최근 호출이 걸린 시간을 재서, 앞 발언의 남은 재생 시간이
    그만큼 남았을 때 시작한다. 연출자는 앞 발언이 30%쯤 나왔을 때 부른다(끼어들 자리를 남기려고).
  - 보는 사람이 없으면(창을 닫으면) 잠시 뒤 스스로 멈추고, 다시 열면 이어 간다.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import random
import re
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Optional

from . import materials, prompts, store
from .providers.base import Provider, ProviderError, Speech, Usage

MOD_ID = "moderator"
CPS = {"slow": 8.0, "normal": 14.0, "fast": 26.0}       # 화면에 나오는 속도 (초당 글자)
GAP_SPEED = {"slow": 1.25, "normal": 1.0, "fast": 0.6, "instant": 0.0}
SPEECH_CPS = 5.5                                         # 토론 시계용: 사람이 말하는 속도
GAPS = {"interject": 0.15, "rebut": 0.6, "ask": 0.9, "add": 1.1, "agree": 1.0, "shift": 1.6,
        "moderate": 1.4, "statement": 1.2, "open": 0.6, "closing": 1.3, "wrap": 1.5, "answer": 0.8}
AWAY_SECONDS = 12      # 보는 사람이 없어진 뒤 이만큼 지나면 토론을 멈춘다
REACT_AT = 0.3         # 앞 발언이 이만큼 화면에 나왔을 때 연출자를 부른다
PHASE_LABEL = {"prepare": "준비", "opening": "개회", "statements": "모두발언", "free": "자유토론",
               "closing": "마무리 발언", "wrap": "진행자 정리", "ended": "끝"}


@dataclass
class Turn:
    speaker: dict
    kind: str                 # open | statement | free | moderate | closing | wrap | answer
    directive: str
    phase: str
    intent: str = ""
    target: str = ""          # 반응하는 상대의 id
    mood: str = "calm"
    interject: bool = False
    scripted: bool = False


class Gen:
    """만들어지고 있는 발언 하나."""

    def __init__(self, turn: Turn) -> None:
        self.turn = turn
        self.text = ""
        self.searches: list[str] = []
        self.speech: Optional[Speech] = None
        self.error: Optional[ProviderError] = None
        self.done = asyncio.Event()
        self.changed = asyncio.Event()
        self.task: Optional[asyncio.Task] = None


class Debate:
    def __init__(self, debate_id: str, config: dict, provider: Provider) -> None:
        self.id = debate_id
        self.cfg = config
        self.provider = provider
        self.people: list[dict] = config["participants"]
        self.mod: Optional[dict] = (
            {"id": MOD_ID, "name": "진행자", "title": "토론 진행", "color": "#E8C170",
             "avatar": {"set": "crest", "variant": 0}} if config.get("moderator") else None)
        self.by_name = {p["name"]: p for p in self.people}
        self.rng = random.Random(config.get("seed"))

        self.events: list[dict] = []
        self.subs: set[asyncio.Queue] = set()
        self.state = "running"
        self.created = dt.datetime.now().isoformat(timespec="seconds")
        self._t0 = time.monotonic()
        self._paused_at: Optional[float] = None
        self._paused_total = 0.0
        self._gate_open = asyncio.Event()
        self._gate_open.set()
        self._resume = asyncio.Event()

        self.speed: str = config.get("speed", "normal")
        self.skip = False
        self.finish = False
        self.pending: deque[dict] = deque()

        self.phase = "prepare"
        self.script: deque[Turn] = deque()
        self.turn_no = 0
        self.clock = 0.0
        self.last_spoke: dict[str, int] = {}
        self.last_speaker: Optional[dict] = None
        self.last_interject = -99
        self.last_mod = -99
        self.milestones: set[str] = set()
        self.rr = 0
        self.director_failed = False
        self.closing = False
        self._moods: dict[str, dict] = {}
        self._lat = {"speech": 3.0, "director": 2.5}   # 최근 호출이 걸린 시간(초). 다음 발언을 만들 시점을 정한다
        self._shown = asyncio.Event()                  # 지금 화면에 나오고 있는 발언이 없으면 켜져 있다
        self._shown.set()
        self.auto_paused = False
        self._showing_mod = False
        self._away_task: Optional[asyncio.Task] = None

        self.ctx = None
        self.briefing = ""
        self.speeches: list[dict] = []
        self.usage = Usage()
        self.usage_by: dict[str, Usage] = {}
        self.calls: dict[str, int] = {}                # 누구를 위한 호출이 몇 번 있었나 ("director"는 연출자)
        self.cost = 0.0
        self.prices: dict[str, Optional[dict]] = {}
        self.summary: Optional[dict] = None
        self._pos = 0
        self._cut: Optional[int] = None
        self._plan_task: Optional[asyncio.Task] = None
        self._bg: set[asyncio.Task] = set()
        self._compactions_seen = 0
        self.task: Optional[asyncio.Task] = None

    # ------------------------------------------------------------------ 이벤트
    def _elapsed(self) -> float:
        now = self._paused_at if self._paused_at is not None else time.monotonic()
        return now - self._t0 - self._paused_total

    def emit(self, type_: str, **data: Any) -> None:
        event = {"i": len(self.events), "t": round(self._elapsed(), 3), "type": type_, **data}
        self.events.append(event)
        for queue in list(self.subs):
            queue.put_nowait(event)

    def public(self) -> dict:
        cfg = {k: v for k, v in self.cfg.items() if k != "materials"}
        cfg["materials"] = [{"name": m.get("name"), "chars": len(m.get("text", ""))}
                            for m in self.cfg.get("materials") or []]
        cfg["participants"] = [{k: v for k, v in p.items() if k != "hidden"} for p in self.people]
        return {"id": self.id, "config": cfg, "moderator": self.mod, "provider": self.provider.name,
                "created": self.created}

    # ------------------------------------------------------------------ 조작
    def control(self, action: str, value: Any = None) -> None:
        if action == "pause" and self.state == "running":
            self.state = "paused"
            self._paused_at = time.monotonic()
            self._gate_open.clear()
            self.emit("paused")
        elif action == "resume" and self.state in ("paused", "error"):
            self.auto_paused = False
            if self._paused_at is not None:
                self._paused_total += time.monotonic() - self._paused_at
                self._paused_at = None
            self.state = "running"
            self._gate_open.set()
            self._resume.set()
            self.emit("resumed")
        elif action == "speed" and value in GAP_SPEED:
            self.speed = value
            self.emit("speed", speed=value)
        elif action == "skip":
            self.skip = True
        elif action == "finish":
            self.finish = True
            self.emit("notice", kind="finish", text="마무리 단계로 넘어갑니다.")
        elif action in ("instruct", "question") and str(value or "").strip():
            self.pending.append({"kind": action, "text": str(value).strip()[:500]})
            self.emit("notice", kind=action, text=str(value).strip()[:500])
        elif action == "abort" and self.task and not self.task.done():
            self.task.cancel()

    def viewer_joined(self) -> None:
        if self._away_task and not self._away_task.done():
            self._away_task.cancel()
        if self.auto_paused and self.state == "paused":
            self.auto_paused = False
            self.control("resume")

    def viewer_left(self) -> None:
        if self.subs or self.state != "running":
            return
        self._away_task = asyncio.create_task(self._away())

    async def _away(self) -> None:
        await asyncio.sleep(AWAY_SECONDS)
        if not self.subs and self.state == "running":
            self.auto_paused = True
            self.control("pause")
            self.emit("notice", kind="info", text="보는 사람이 없어 토론을 멈췄습니다. 다시 열면 이어 갑니다.")

    async def _gate(self) -> None:
        if not self._gate_open.is_set():
            await self._gate_open.wait()

    async def _sleep(self, seconds: float, *, skippable: bool = True) -> None:
        end = time.monotonic() + seconds
        while True:
            await self._gate()
            if skippable and (self.skip or self.speed == "instant"):
                return
            remaining = end - time.monotonic()
            if remaining <= 0:
                return
            await asyncio.sleep(min(0.05, remaining))

    # ------------------------------------------------------------------ 실행
    async def run(self) -> None:
        try:
            self.emit("init", **self.public())
            for model in await self.provider.list_models():
                self.prices[model.id] = model.price
            await self._prepare()
            await self._loop()
            await self._summarize()
            self.state = "ended"
        except asyncio.CancelledError:
            self.state = "aborted"
            self.emit("notice", kind="abort", text="토론을 중단했습니다.")
        except Exception as exc:  # noqa: BLE001 - 마지막 방어선. 기록은 남긴다
            self.state = "failed"
            self.emit("error", message=f"토론이 멈췄습니다: {exc}", fatal=True)
        finally:
            for task in list(self._bg) + ([self._plan_task] if self._plan_task else []):
                if task and not task.done():
                    task.cancel()
            self.phase = "ended"
            self.emit("end", state=self.state)
            store.save_debate(self.record())

    def record(self) -> dict:
        return {**self.public(), "state": self.state, "turns": self.turn_no,
                "seconds": round(self.clock), "cost": round(self.cost, 4),
                "usage": self.usage.to_dict(), "calls": dict(self.calls),
                "judge_fallbacks": getattr(self.provider, "judge_fallbacks", 0), "briefing": self.briefing,
                "speeches": self.speeches, "summary": self.summary,
                "context": self.ctx.snapshot() if self.ctx else {}, "events": self.events}

    async def _prepare(self) -> None:
        cfg = self.cfg
        urls = [u for u in cfg.get("urls") or [] if u.strip()]
        if urls:
            self.emit("phase", phase="prepare", label=PHASE_LABEL["prepare"])
            notes = []
            for url in urls:
                self.emit("research", url=url, status="start")
                text, sources = await self._research(url)
                if text:
                    notes.append(f"[{url}]\n{text}")
                self.emit("research", url=url, status="done" if text else "failed", sources=sources)
            self.briefing = "\n\n".join(notes)
            if self.briefing:
                self.emit("briefing", text=self.briefing)
        shared = prompts.shared_context(cfg, self.briefing)
        self.ctx = self.provider.open_context(
            shared, search=cfg.get("search") in ("auto", "all"),
            max_searches=int(cfg.get("max_searches", 2)),
            compact_threshold=int(cfg.get("compact_threshold", 150_000)))

    async def _research(self, url: str) -> tuple[str, list]:
        model, effort = self.cfg["model"], self.cfg["effort"]
        try:
            speech = await self.provider.research(
                prompt=prompts.research_prompt(self.cfg["topic"], url), model=model, effort=effort,
                on_event=lambda kind, payload: self.emit("research", url=url, status="search", query=payload))
            self._account(MOD_ID, speech.usage, speech.model or model)
            if speech.text:
                return speech.text, speech.sources or [{"title": url, "url": url}]
        except ProviderError as exc:
            self.emit("notice", kind="warn", text=f"웹 도구로 조사하지 못해 페이지를 직접 읽습니다. ({exc})")
        try:   # 대안: 페이지를 직접 받아 글자만 넘긴다
            page = await materials.fetch_page(url)
            text, usage = await self.provider.generate_text(
                system=prompts.RESEARCH_SYSTEM,
                prompt=prompts.research_prompt(self.cfg["topic"], url) + "\n\n페이지 본문:\n" + page,
                model=model, effort=effort)
            self._account(MOD_ID, usage, model)
            return text, [{"title": url, "url": url}]
        except Exception as exc:  # noqa: BLE001
            self.emit("notice", kind="warn", text=f"{url} 을(를) 조사하지 못했습니다. 자료 없이 진행합니다. ({exc})")
            return "", []

    # ------------------------------------------------------------------ 대본(정해진 순서)
    def _len(self) -> str:
        return f"길이: {prompts.LENGTHS.get(self.cfg.get('length', 'normal'))}."

    def _build_opening(self) -> None:
        names = ", ".join(p["name"] for p in self.people)
        if self.mod:
            self.script.append(Turn(self.mod, "open",
                f"토론을 여세요. 주제를 한두 문장으로 소개하고, 참가자({names})를 각각 한마디로 소개한 뒤 "
                + (f"모두발언을 {self.people[0]['name']} 님부터 이 순서대로 청하세요. " if self.cfg.get("mode", "mixed") != "free"
                   else "누구든 먼저 말해 달라고 청하세요. ")
                + "4~6문장.", "opening", scripted=True))
        if self.cfg.get("mode", "mixed") != "free":
            for p in self.people:
                self.script.append(Turn(p, "statement",
                    f"모두발언입니다. 이 주제에 대한 자신의 입장을 분명히 밝히세요. {self._len()}",
                    "statements", scripted=True))

    def _enter_closing(self) -> None:
        if self.mod:
            self.script.append(Turn(self.mod, "moderate",
                "토론을 마무리할 시간입니다. 시간이 다 되었음을 알리고, 마지막 발언을 "
                + ", ".join(p["name"] for p in self.people) + " 순서로 청하세요. 2~3문장.",
                "closing", scripted=True))
        for p in self.people:
            self.script.append(Turn(p, "closing",
                "마지막 발언입니다. 토론에서 들은 말을 반영해 자신의 입장을 정리하세요. "
                f"생각이 바뀐 부분이 있으면 인정하세요. {self._len()}", "closing", scripted=True))
        if self.mod:
            self.script.append(Turn(self.mod, "wrap",
                "토론이 끝났습니다. 참가자들이 동의한 점과 끝까지 갈린 점을 중립적으로 정리하고 마무리 인사를 하세요. 4~6문장.",
                "wrap", scripted=True))
        self.closing = True

    def _reserve(self) -> int:
        return len(self.people) + (2 if self.mod else 0)

    def _progress(self, extra_chars: int = 0) -> float:
        parts = [0.0]
        if self.cfg.get("max_turns"):
            parts.append(self.turn_no / self.cfg["max_turns"])
        if self.cfg.get("max_minutes"):
            parts.append((self.clock + extra_chars / SPEECH_CPS) / (self.cfg["max_minutes"] * 60))
        return max(parts)

    def _should_close(self, extra_chars: int) -> bool:
        if self.finish:
            return True
        reserve = self._reserve()
        if self.cfg.get("max_turns") and self.turn_no + reserve >= self.cfg["max_turns"]:
            return True
        if self.cfg.get("max_minutes"):
            now = self.clock + extra_chars / SPEECH_CPS
            if now + reserve * 22 >= self.cfg["max_minutes"] * 60:
                return True
        return False

    # ------------------------------------------------------------------ 주 루프
    async def _loop(self) -> None:
        self.closing = False
        self._build_opening()
        first = self.script.popleft() if self.script else Turn(
            self.rng.choice(self.people), "free",
            f"토론의 첫 발언입니다. 주제에 대한 생각을 밝히며 토론을 여세요. {self._len()}", "free")
        gen: Optional[Gen] = self._generate(first)
        while gen is not None:
            gen = self._apply_pending(gen)
            try:
                await self._present(gen)
            except ProviderError as exc:
                self.state = "error"
                self._paused_at = time.monotonic()
                self._resume.clear()
                self.emit("error", message=str(exc), fatal=False)
                await self._resume.wait()
                gen = self._generate(gen.turn)
                continue
            gen = await self._plan_task if self._plan_task else None

    def _apply_pending(self, gen: Gen) -> Gen:
        """관람자가 개입했으면 미리 만들어 둔 발언을 버리고 그 요청부터 처리한다."""
        if not self.pending:
            return gen
        item = self.pending.popleft()
        if gen.task and not gen.task.done():
            gen.task.cancel()
        if gen.turn.scripted:
            self.script.appendleft(gen.turn)
        phase = gen.turn.phase
        text = item["text"]
        if item["kind"] == "question":
            self.ctx.add_note("청중", f"(청중 질문) {text}")
            if self.mod:
                turn = Turn(self.mod, "moderate",
                            f"청중에게서 질문이 들어왔습니다: \"{text}\" 이 질문을 소개하고, 가장 잘 답할 참가자 한 명을 지목해 답을 청하세요. 2~3문장.",
                            phase)
            else:
                who = max(self.people, key=lambda p: self.turn_no - self.last_spoke.get(p["id"], 0))
                turn = Turn(who, "answer", f"청중 질문 \"{text}\"에 자신의 입장에서 답하세요. {self._len()}", phase,
                            intent="answer")
        else:
            if self.mod:
                turn = Turn(self.mod, "moderate",
                            f"제작진의 요청입니다: \"{text}\" 이 요청을 자연스럽게 반영해 토론을 이끄세요. 2~3문장.", phase)
            else:
                self.ctx.add_note("진행 안내", text)
                who = max(self.people, key=lambda p: self.turn_no - self.last_spoke.get(p["id"], 0))
                turn = Turn(who, "free", f"방금 진행 안내에 따라 발언을 이어가세요. {self._len()}", phase, intent="shift")
        return self._generate(turn)

    # ------------------------------------------------------------------ 만들기
    def _model(self, speaker: dict) -> str:
        return speaker.get("model") or self.cfg["model"]

    def _effort(self, speaker: dict) -> str:
        return speaker.get("effort") or self.cfg["effort"]

    def _generate(self, turn: Turn) -> Gen:
        gen = Gen(turn)
        speaker = turn.speaker

        def on_event(kind: str, payload: Any) -> None:
            if kind == "text":
                gen.text += payload
            elif kind == "search":
                gen.searches.append(str(payload))
            gen.changed.set()

        async def work() -> None:
            started = time.monotonic()
            try:
                await self._gate()
                private = speaker.get("hidden", "") if self.cfg.get("hidden_agenda", True) else ""
                speech = await self.ctx.speak(
                    speaker=speaker["name"], directive=turn.directive, private=private,
                    model=self._model(speaker), effort=self._effort(speaker), on_event=on_event)
                if not speech.text.strip():
                    raise ProviderError("모델이 빈 발언을 돌려주었습니다.")
                self._note_latency("speech", time.monotonic() - started)
                # 화면에 이미 나간 글자와 자리가 어긋나지 않게 맞춘다
                raw = gen.text
                lead = len(raw) - len(raw.lstrip())
                if raw.strip() and not raw.lstrip().startswith(speech.text[:20]):
                    speech.text = raw.strip()
                gen.speech = speech
                gen.text = raw[:lead] + speech.text
            except asyncio.CancelledError:
                raise
            except ProviderError as exc:
                gen.error = exc
            except Exception as exc:  # noqa: BLE001
                gen.error = ProviderError(f"{type(exc).__name__}: {exc}")
            finally:
                gen.done.set()
                gen.changed.set()

        gen.task = asyncio.create_task(work())
        return gen

    def _account(self, who: str, usage: Usage, model: str) -> None:
        self.usage.add(usage)
        self.usage_by.setdefault(who, Usage()).add(usage)
        self.calls[who] = self.calls.get(who, 0) + 1
        self.cost += usage.cost(self.prices.get(model))
        total = self.usage.total_input
        self.emit("usage", total=self.usage.to_dict(), cost=round(self.cost, 4),
                  cache_rate=round(self.usage.cached / total, 3) if total else 0,
                  by={k: v.to_dict() for k, v in self.usage_by.items()}, calls=dict(self.calls))

    # ------------------------------------------------------------------ 보여 주기
    def _gap(self, turn: Turn) -> float:
        scale = float(self.cfg.get("gap_scale", 1.0)) * GAP_SPEED.get(self.speed, 1.0)
        key = "interject" if turn.interject else (turn.intent if turn.kind == "free" else turn.kind)
        return GAPS.get(key, 1.0) * scale * self.rng.uniform(0.75, 1.25)

    def _unit_delay(self, unit: str) -> float:
        cps = CPS.get(self.speed, 14.0)
        delay = max(len(unit.strip()), 1) / cps
        tail = unit.rstrip()[-1:] if unit.strip() else ""
        factor = 14.0 / cps
        if tail in ",，、":
            delay += 0.16 * factor
        elif tail in ".?!…。":
            delay += 0.36 * factor
        return delay

    async def _present(self, gen: Gen) -> None:
        turn, speaker = gen.turn, gen.turn.speaker
        self._plan_task = None
        self.emit("ready", speaker=speaker["id"], kind=turn.kind, intent=turn.intent,
                  interject=turn.interject, mood=turn.mood)
        await self._sleep(self._gap(turn), skippable=False if self.speed != "instant" else True)
        if gen.done.is_set() and gen.error:
            raise gen.error
        if turn.phase != self.phase:
            self.phase = turn.phase
            self.emit("phase", phase=self.phase, label=PHASE_LABEL.get(self.phase, self.phase))
        self.turn_no += 1
        sid = self.turn_no
        self.emit("speech_start", id=sid, speaker=speaker["id"], kind=turn.kind, intent=turn.intent,
                  target=turn.target, mood=turn.mood, interject=turn.interject,
                  model=self._model(speaker), effort=self._effort(speaker))
        self.skip = False
        self._cut = None
        self._pos = 0
        self._shown.clear()
        self._showing_mod = speaker["id"] == MOD_ID
        self._plan_task = asyncio.create_task(self._after_gen(gen))
        sent_searches = 0
        cut = False
        while True:
            await self._gate()
            while sent_searches < len(gen.searches):
                self.emit("search", id=sid, speaker=speaker["id"], query=gen.searches[sent_searches])
                sent_searches += 1
            finished = gen.done.is_set()
            text = gen.text
            limit = len(text) if finished else max(text.rfind(" "), text.rfind("\n")) + 1
            if self._cut is not None:
                limit = min(limit, self._cut)
            if self._pos < limit:
                if self.speed == "instant" or self.skip:
                    unit = text[self._pos:limit]
                else:
                    match = re.match(r"\s*\S+\s*", text[self._pos:limit])
                    unit = match.group(0) if match else text[self._pos:limit]
                self._pos += len(unit)
                self.emit("delta", id=sid, text=unit)
                if self.speed != "instant" and not self.skip:
                    await self._sleep(self._unit_delay(unit))
                else:
                    await asyncio.sleep(0)
                continue
            if self._cut is not None and self._pos >= self._cut:
                cut = True
                break
            if finished:
                break
            gen.changed.clear()
            try:
                await asyncio.wait_for(gen.changed.wait(), timeout=0.25)
            except asyncio.TimeoutError:
                pass
        self._shown.set()
        if gen.error:
            self.emit("speech_end", id=sid, failed=True, text="", cut=False)
            self.turn_no -= 1
            raise gen.error
        shown = gen.text[: self._pos].rstrip()
        final = shown + " —" if cut else shown
        speech = gen.speech or Speech()
        seconds = len(shown) / SPEECH_CPS + GAPS.get(turn.kind, 1.0)
        self.clock += seconds
        self.last_spoke[speaker["id"]] = sid
        self.last_speaker = speaker
        if speaker["id"] == MOD_ID:
            self.last_mod = sid
        self.speeches.append({"id": sid, "speaker": speaker["id"], "name": speaker["name"], "text": final,
                              "kind": turn.kind, "intent": turn.intent, "target": turn.target,
                              "mood": turn.mood, "cut": cut, "interject": turn.interject,
                              "sources": speech.sources, "model": speech.model})
        self.emit("speech_end", id=sid, speaker=speaker["id"], text=final, cut=cut, failed=False,
                  sources=speech.sources, thinking=speech.thinking.strip(), usage=speech.usage.to_dict(),
                  model=speech.model)
        self.emit("clock", turn=self.turn_no, max_turns=self.cfg.get("max_turns"),
                  seconds=round(self.clock, 1),
                  max_seconds=(self.cfg["max_minutes"] * 60) if self.cfg.get("max_minutes") else None,
                  progress=round(min(self._progress(), 1.0), 3))

    # ------------------------------------------------------------------ 다음 정하기
    async def _after_gen(self, gen: Gen) -> Optional[Gen]:
        await gen.done.wait()
        if gen.error or gen.speech is None:
            return None
        speaker = gen.turn.speaker
        self.ctx.commit(speaker["name"], gen.speech)
        self._account(speaker["id"], gen.speech.usage, gen.speech.model or self._model(speaker))
        try:
            if await self.ctx.maybe_compact(self.cfg["model"]) or self.ctx.compactions > self._compactions_seen:
                self._compactions_seen = self.ctx.compactions
                self.emit("compaction", count=self.ctx.compactions, at=self.turn_no)
        except ProviderError as exc:
            self.emit("notice", kind="warn", text=f"문맥을 줄이지 못했습니다. ({exc})")
        return await self._plan(gen)

    def _spawn(self, coro) -> None:
        task = asyncio.create_task(coro)
        self._bg.add(task)
        task.add_done_callback(self._bg.discard)

    def _note_latency(self, key: str, seconds: float) -> None:
        self._lat[key] = self._lat[key] * 0.6 + seconds * 0.4

    def _remaining(self, prev: Gen) -> float:
        """앞 발언이 화면에 다 나오기까지 남은 시간(초)의 어림."""
        if self._shown.is_set() or self.speed == "instant" or self.skip:
            return 0.0
        limit = self._cut if self._cut is not None else len(prev.text)
        return max(limit - self._pos, 0) / CPS.get(self.speed, 14.0) * 1.3

    async def _hold_until(self, prev: Gen, *, progress: Optional[float] = None,
                          lead: Optional[float] = None) -> None:
        """앞 발언이 충분히 나올 때까지 다음 호출을 미룬다. 토큰을 너무 앞서 쓰지 않기 위해서다."""
        while True:
            await self._gate()
            if self._shown.is_set() or self.speed == "instant" or self.skip:
                return
            if progress is not None and self._pos >= progress * len(prev.text):
                return
            if lead is not None and self._remaining(prev) <= lead:
                return
            await asyncio.sleep(0.1)

    def _lead(self) -> float:
        """다음 발언을 만들기 시작할 시점: 앞 발언의 남은 시간이 이만큼일 때."""
        return self._lat["speech"] * 1.25 + 0.8

    async def _react(self, prev: Gen) -> None:
        await self._hold_until(prev, progress=REACT_AT)
        await self._direct(react_only=True)

    async def _plan(self, prev: Gen) -> Optional[Gen]:
        chars = len(prev.text)
        await self._gate()
        if self.closing and not self.script:
            return None
        free = (not self.script and not self._should_close(chars)
                and self.cfg.get("mode") != "sequential")
        if not free:   # 다음 발언자가 정해져 있다: 발언은 때맞춰 만들고, 연출자는 감정만 정한다
            if self._wants_reaction(prev):
                self._spawn(self._react(prev))
            await self._hold_until(prev, lead=self._lead())
            return self._generate(self._next_scripted(chars))
        await self._hold_until(prev, progress=REACT_AT)
        verdict = await self._direct()
        if self._should_close(chars):   # 기다리는 사이에 "마무리"가 눌렸을 수 있다
            await self._hold_until(prev, lead=self._lead())
            return self._generate(self._next_scripted(chars))
        turn = self._milestone(chars) or self._choose(verdict, prev)
        if turn.interject:
            turn.interject = self._arm_cut(prev)
            if turn.interject:
                return self._generate(turn)   # 곧 말을 끊으므로 바로 만든다
        await self._hold_until(prev, lead=self._lead())
        return self._generate(turn)

    def _wants_reaction(self, prev: Gen) -> bool:
        """다음 발언자가 이미 정해져 있을 때, 아바타 반응만을 위해 연출자를 부를지.

        기본(smart)은 참가자의 모두발언과 순차 토론에서만 부른다. 개회와 마무리 발언에서는 부르지 않는다.
        이 호출이 전체 호출의 3분의 1쯤이었기 때문이다.
        """
        if self.cfg.get("reactions", "smart") == "all":
            return True
        turn = prev.turn
        return (turn.speaker["id"] != MOD_ID and turn.phase in ("statements", "free")
                and not self.closing and not self._should_close(len(prev.text)))

    def _next_scripted(self, chars: int) -> Turn:
        if self.script:
            return self.script.popleft()
        if self._should_close(chars):
            self._enter_closing()
            return self.script.popleft()
        return self._milestone(chars) or self._sequential_turn()

    def _milestone(self, chars: int) -> Optional[Turn]:
        if not self.mod or (self.last_speaker and self.last_speaker["id"] == MOD_ID) or self._showing_mod:
            return None   # 진행자가 방금 말했으면 다음 기회로 미룬다 (연달아 두 번 나서지 않게)
        progress = self._progress(chars)
        if progress >= 0.5 and "half" not in self.milestones:
            self.milestones.add("half")
            return Turn(self.mod, "moderate",
                        "토론이 절반을 지났습니다. 지금까지 드러난 쟁점을 한두 문장으로 짚고, 아직 다루지 않은 측면으로 화제를 넘기세요. 2~3문장.",
                        "free")
        return None

    def _sequential_turn(self) -> Turn:
        speaker = self.people[self.rr % len(self.people)]
        self.rr += 1
        state = getattr(self, "_moods", {}).get(speaker["id"], {})
        return Turn(speaker, "free",
                    f"자기 차례입니다. 앞선 발언들 가운데 가장 걸리는 말에 반응하며 토론을 이어가세요. {self._len()}",
                    "free", intent=state.get("intent", "add"), target=state.get("target", ""),
                    mood=state.get("mood", "calm"))

    async def _direct(self, react_only: bool = False) -> dict:
        """연출자를 불러 전원의 상태를 받는다. 실패하면 임시 규칙으로 채운다."""
        names = [p["name"] for p in self.people]
        last = self.ctx.entries[-1][0] if getattr(self.ctx, "entries", None) else ""
        try:
            started = time.monotonic()
            data, usage = await self.ctx.judge(
                question=prompts.director_question(names, last), schema=prompts.director_schema(),
                model=self.cfg["model"], effort=self.cfg["effort"])
            self._note_latency("director", time.monotonic() - started)
            self._account("director", usage, self.cfg["model"])
            verdict = self._normalize(data)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - 연출자가 실패해도 토론은 멈추지 않는다
            if react_only:
                return {}
            if not self.director_failed:
                self.director_failed = True
                self.emit("notice", kind="warn", text=f"다음 발언자 판단에 실패해 임시 규칙으로 진행합니다. ({exc})")
            verdict = self._normalize({"participants": [
                {"name": n, "urge": self.rng.randint(2, 7), "intent": self.rng.choice(prompts.INTENTS),
                 "target": last if last in self.by_name and last != n else "", "mood": "calm"} for n in names]})
        self._moods = verdict["by_id"]
        self.emit("director", scores=[{"id": pid, **row} for pid, row in verdict["by_id"].items()],
                  addressed=verdict["addressed"])
        return verdict

    def _normalize(self, data: dict) -> dict:
        by_id: dict[str, dict] = {}
        rows = {str(r.get("name", "")).strip(): r for r in data.get("participants") or [] if isinstance(r, dict)}
        for p in self.people:
            row = rows.get(p["name"], {})
            target = self.by_name.get(str(row.get("target", "")).strip())
            intent = row.get("intent") if row.get("intent") in prompts.INTENTS else "add"
            mood = row.get("mood") if row.get("mood") in prompts.MOODS else "calm"
            try:
                urge = max(0, min(10, int(row.get("urge", 3))))
            except (TypeError, ValueError):
                urge = 3
            by_id[p["id"]] = {"urge": urge, "intent": intent, "mood": mood,
                              "target": target["id"] if target and target["id"] != p["id"] else ""}
        addressed = self.by_name.get(str(data.get("addressed", "")).strip())
        return {"by_id": by_id, "addressed": addressed["id"] if addressed else "",
                "moderator_needed": bool(data.get("moderator_needed")),
                "moderator_reason": str(data.get("moderator_reason", "")).strip()}

    def _choose(self, verdict: dict, prev: Gen) -> Turn:
        """연출자의 점수에 규칙을 더해 다음 발언자를 고른다 (설계 문서 3.4)."""
        last = prev.turn.speaker
        by_id = verdict["by_id"]
        if (self.mod and verdict["moderator_needed"] and last["id"] != MOD_ID
                and self.turn_no - self.last_mod >= 4):
            reason = verdict["moderator_reason"] or "논점이 흐려졌습니다."
            return Turn(self.mod, "moderate",
                        f"진행자가 나설 때입니다. 상황: {reason} 논점을 한 문장으로 정리하고, 토론이 앞으로 나아가게 "
                        "구체적인 질문을 던지거나 다른 참가자에게 발언권을 넘기세요. 2~3문장.", "free")
        scores: dict[str, float] = {}
        for p in self.people:
            row = by_id[p["id"]]
            score = float(row["urge"])
            if p["id"] == last["id"]:
                score -= 6                                    # 방금 말한 사람은 감점
            if verdict["addressed"] == p["id"]:
                score += 3                                    # 지목받은 사람은 가산
            silence = self.turn_no - self.last_spoke.get(p["id"], 0)
            score += min(silence * 0.5, 3.5)                  # 오래 조용했던 사람은 조금씩 가산
            score += self.rng.uniform(0, 1.5)                 # 약간의 무작위
            scores[p["id"]] = score
        speaker = max(self.people, key=lambda p: scores[p["id"]])
        row = by_id[speaker["id"]]
        intent, target_id = row["intent"], row["target"]
        target = next((p for p in self.people if p["id"] == target_id), None)
        if target is None and intent in ("rebut", "ask", "agree") and last["id"] not in (MOD_ID, speaker["id"]):
            target = last
        tname = f"{target['name']} 님" if target else ""
        lines = {
            "rebut": f"{tname}의 방금 주장에 반박하세요. 상대가 한 구체적인 말을 짚으세요." if target
                     else "지금까지 나온 주장 가운데 가장 동의하기 어려운 것에 반박하세요.",
            "add": f"{tname}의 말에 보충하거나, 다른 각도의 근거를 더하세요." if target
                   else "지금까지의 논의에 새 근거나 사례를 보충하세요.",
            "ask": f"{tname}에게 날카로운 질문을 하나 던지세요. 왜 묻는지도 짧게 밝히세요." if target
                   else "다른 참가자 한 명을 골라 날카로운 질문을 던지세요.",
            "agree": f"{tname}의 말 가운데 동의하는 부분을 밝히고, 거기에 자신의 생각을 한 걸음 더하세요." if target
                     else "앞선 발언 가운데 동의하는 부분을 밝히고 자신의 생각을 더하세요.",
            "shift": "논의가 한쪽으로 쏠렸습니다. 아직 다루지 않은 측면으로 화제를 넘기세요.",
        }
        directive = lines[intent]
        if verdict["addressed"] == speaker["id"] and last["id"] != speaker["id"]:
            directive = f"방금 {last['name']} 님이 당신에게 물었거나 당신을 지목했습니다. 먼저 거기에 답하세요. " + directive
        interject = bool(
            self.cfg.get("interjection", True) and self.speed != "instant" and row["urge"] >= 9
            and intent == "rebut" and last["id"] not in (MOD_ID, speaker["id"])
            and self.turn_no - self.last_interject >= 4)
        if interject:
            directive = ("상대의 말이 끝나기 전에 끼어듭니다. '잠깐만요' 같은 말로 짧고 빠르게 치고 들어가세요. "
                         + directive + " 길이: 1~2문장.")
        else:
            directive += " " + self._len()
        return Turn(speaker, "free", directive, "free", intent=intent,
                    target=target["id"] if target else "", mood=row["mood"], interject=interject)

    def _arm_cut(self, prev: Gen) -> bool:
        """지금 화면에 나오는 발언을 문장 끝에서 끊도록 건다. 끊을 자리가 없으면 False."""
        text = prev.text
        if not text or self._plan_task is None:
            return False
        low = max(self._pos + 12, int(len(text) * 0.35))
        high = int(len(text) * 0.85)
        for match in re.finditer(r"[.?!…][\"”']?\s+", text):
            if low <= match.end() <= high:
                self._cut = match.end()
                self.ctx.amend_last(text[: self._cut].rstrip() + " —")
                self.last_interject = self.turn_no
                return True
        return False

    # ------------------------------------------------------------------ 끝난 뒤
    async def _summarize(self) -> None:
        if not self.cfg.get("summary", True) or len(self.speeches) < 3:
            return
        transcript = "\n".join(f"【{s['name']}】 {s['text']}" for s in self.speeches)
        try:
            self.emit("summarizing")
            try:   # 토론에 쓰던 문맥(캐시)을 그대로 이어 쓴다. 기록을 처음부터 다시 보내지 않는다
                data, usage = await self.ctx.judge(
                    question=prompts.SUMMARY_TAIL, schema=prompts.summary_schema(),
                    model=self.cfg["model"], effort=self.cfg["effort"])
            except Exception:  # noqa: BLE001 - 안 되면 기록을 통째로 보내는 예전 방식으로
                data, usage = await self.provider.generate_json(
                    system=prompts.SUMMARY_SYSTEM, prompt=prompts.summary_prompt(self.cfg["topic"], transcript),
                    schema=prompts.summary_schema(), model=self.cfg["model"], effort=self.cfg["effort"])
            self._account("director", usage, self.cfg["model"])
            self.summary = data
            self.emit("summary", **data)
        except Exception as exc:  # noqa: BLE001 - 요약이 안 되어도 토론 기록은 남는다
            self.emit("notice", kind="warn", text=f"요약 카드를 만들지 못했습니다. ({exc})")
