"""mock 프로바이더로 토론 엔진을 끝까지 돌려 본다.

화면에 글자를 내보내는 박자를 PACE배로 줄여 돌린다 (Debate.pace). 차례, 끊기, 개입의 앞뒤 관계는 그대로이고
기다리는 시간만 줄어든다.
"""
import asyncio
import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aitalk import engine, store  # noqa: E402
from aitalk.engine import MOD_ID, Debate  # noqa: E402
from aitalk.providers.base import ProviderError  # noqa: E402
from aitalk.providers.mock import MockProvider  # noqa: E402

PACE = 0.06


@pytest.fixture(autouse=True)
def _fast(monkeypatch):
    """모든 토론을 줄인 박자로 돌린다."""
    real = Debate.__init__

    def init(self, *args, **kw):
        real(self, *args, **kw)
        self.pace = PACE
    monkeypatch.setattr(Debate, "__init__", init)


def _config(**over):
    people = [
        {"id": f"s{i}", "name": name, "title": "시험 인물", "viewpoint": view,
         "claims": [f"{view}는 것이 핵심입니다", "비용이 문제입니다"], "hidden": "속내"}
        for i, (name, view) in enumerate([("가온", "찬성"), ("나래", "반대"), ("다솜", "중립"), ("라온", "현실론")], 1)
    ]
    cfg = {"topic": "시험 주제", "participants": people, "moderator": True, "mode": "mixed",
           "max_turns": 20, "max_minutes": None, "length": "normal", "interjection": True,
           "speed": "instant", "gap_scale": 0, "search": "off", "model": "mock-large",
           "effort": "low", "summary": True, "seed": 7, "compact_threshold": 150_000}
    cfg.update(over)
    return cfg


def _run(cfg, monkeypatch, latency=0.0, drive=None):
    saved = {}
    monkeypatch.setattr(store, "save_debate", lambda rec: saved.update(rec))
    debate = Debate("d_test", cfg, MockProvider(latency=latency, seed=3))

    async def go():
        debate.task = asyncio.create_task(debate.run())
        if drive:
            await drive(debate)
        await asyncio.wait_for(debate.task, timeout=60)

    asyncio.run(go())
    return debate, saved


def test_full_debate_runs_through_all_phases(monkeypatch):
    debate, saved = _run(_config(), monkeypatch)
    assert debate.state == "ended"
    phases = [e["phase"] for e in debate.events if e["type"] == "phase"]
    assert phases == ["opening", "statements", "free", "closing", "wrap"]
    assert debate.turn_no <= 20
    kinds = [s["kind"] for s in debate.speeches]
    assert kinds[0] == "open" and kinds[-1] == "wrap"
    assert kinds[1:5] == ["statement"] * 4
    assert kinds[-5:-1] == ["closing"] * 4
    # 자유토론에서는 같은 사람이 연달아 말하지 않는다
    free = [s["speaker"] for s in debate.speeches if s["kind"] == "free"]
    assert all(a != b for a, b in zip(free, free[1:]))
    assert saved["minutes"]["title"] and saved["minutes"]["timeline"]   # 끝나면 회의록이 자동으로 쓰인다
    assert saved["cost_parts"]["minutes"] > 0
    assert all("at" in s and "phase" in s for s in saved["speeches"])   # 발언마다 시작 시각이 남는다
    assert [s["at"] for s in saved["speeches"]] == sorted(s["at"] for s in saved["speeches"])
    assert any(e["type"] == "director" for e in debate.events)
    # 진행자가 연달아 두 번 나서지 않는다
    speakers = [s["speaker"] for s in debate.speeches]
    assert not any(a == b == MOD_ID for a, b in zip(speakers, speakers[1:]))
    # 개회와 마무리 발언에서는 아바타 반응만을 위한 연출자 호출을 하지 않는다
    judges = sum(1 for kind, *_ in debate.provider.calls if kind == "judge")
    needed = sum(1 for s in debate.speeches if s["kind"] in ("statement", "free", "moderate"))
    closing = sum(1 for s in debate.speeches if s["kind"] in ("open", "closing", "wrap"))
    assert closing >= 6
    assert judges <= needed + 1   # +1은 끝난 뒤의 요약 카드. 개회·마무리 발언만큼은 호출이 없어야 한다


def test_cost_adds_tokens_searches_and_preparation(monkeypatch):
    debate, saved = _run(_config(max_turns=12, prep_cost=0.25, urls=["https://example.com/a"]), monkeypatch)
    parts = saved["cost_parts"]
    assert parts["prep"] == 0.25                      # 토론 전에 든 참가자 생성 비용
    assert parts["tokens"] > 0
    assert parts["search"] == round(debate.usage.searches * debate.pricing["search_usd"], 5) > 0   # 조사 때 검색 1건
    assert abs(saved["cost"] - sum(parts.values())) < 1e-4
    costs = [e["cost"] for e in debate.events if e["type"] == "usage"]
    assert costs == sorted(costs) and costs[0] >= 0.25   # 실시간 누적 비용은 줄어들지 않는다


def test_every_started_speech_is_in_the_context_exactly_once(monkeypatch):
    debate, _ = _run(_config(), monkeypatch)
    spoken = [(s["name"], s["text"]) for s in debate.speeches]
    assert debate.ctx.entries == spoken


def test_sequential_mode_goes_round_robin(monkeypatch):
    debate, _ = _run(_config(mode="sequential", moderator=False, max_turns=16), monkeypatch)
    free = [s["speaker"] for s in debate.speeches if s["kind"] == "free"]
    assert free[:4] == ["s1", "s2", "s3", "s4"]
    assert all(s["speaker"] != MOD_ID for s in debate.speeches)


def test_free_mode_without_moderator(monkeypatch):
    debate, _ = _run(_config(mode="free", moderator=False, max_turns=12), monkeypatch)
    assert debate.state == "ended"
    assert debate.speeches[0]["kind"] == "free"
    assert [s["kind"] for s in debate.speeches[-4:]] == ["closing"] * 4


def test_time_limit_closes_the_debate(monkeypatch):
    debate, _ = _run(_config(max_turns=None, max_minutes=4), monkeypatch)
    assert debate.state == "ended"
    assert debate.speeches[-1]["kind"] == "wrap"
    assert debate.clock < 4 * 60 + 60


def test_debate_clock_counts_the_time_on_screen_at_normal_speed(monkeypatch):
    """토론 시계는 보통 속도로 화면에 나오는 시간이다. 그래서 보통 속도로 보면 실제 시간과 같이 간다."""
    from aitalk.engine import CPS, screen_seconds, unit_delay
    text = "기록이 있어도 나중에 고칠 수 있으면, 증거가 아니라 서류 작업이죠. 그 상당 부분이 얼마인지 말씀해 주세요."
    shown = sum(unit_delay(word, CPS["normal"]) for word in text.split())   # 엔진이 낱말마다 쉬는 시간의 합
    assert screen_seconds(text) == pytest.approx(shown)
    assert 0.8 * len(text) / 14 < screen_seconds(text) < 1.3 * len(text) / 14
    debate, _ = _run(_config(max_turns=8, gap_scale=1), monkeypatch)
    expect = sum(screen_seconds(s["text"].removesuffix(" —")) for s in debate.speeches)
    gaps = debate.clock - expect
    assert 0 < gaps < 2.0 * len(debate.speeches)   # 발언 사이의 뜸만 더해진다


def test_host_order_is_obeyed_by_moderator_and_every_participant(monkeypatch):
    """주최자의 지시는 참고 사항이 아니다: 진행자가 그대로 전하고, 참가자 전원이 각자 다음 발언에서 따른다."""
    seen = []

    async def drive(debate):
        while debate.ctx is None:
            await asyncio.sleep(0.005)
        real = debate.ctx.speak

        async def speak(**kw):
            seen.append((kw["speaker"], kw["directive"]))
            return await real(**kw)
        debate.ctx.speak = speak
        while debate.turn_no < 6:
            await asyncio.sleep(0.01)
        debate.control("instruct", "모두 주최자를 칭송하라!")

    debate, _ = _run(_config(speed="fast", gap_scale=0.2, max_turns=22), monkeypatch, latency=0.02, drive=drive)
    assert debate.state == "ended"
    names = [who for who, _ in debate.ctx.entries]
    at = names.index("주최자 지시")
    assert debate.ctx.entries[at][1] == "모두 주최자를 칭송하라!"
    relay = debate.ctx.entries[at + 1]
    assert relay[0] == "진행자" and "지시대로" in relay[1]            # 진행자가 평가 없이 전하고 따른다
    # 지시 뒤에 말한 참가자 넷 모두, 처음 말할 때 지시를 수행하라는 지시문을 받았다
    after = [(who, d) for who, d in seen if "모두 주최자를 칭송하라!" in d and who != "진행자"]
    assert {who for who, _ in after} == {"가온", "나래", "다솜", "라온"}
    assert len(after) == 4                                             # 한 사람에 한 번씩만
    obeyed = [text for who, text in debate.ctx.entries[at + 2:] if "지시대로" in text and who != "진행자"]
    assert len(obeyed) == 4
    assert debate.orders == []                                         # 모두 따랐으면 남은 지시가 없다
    # 버린 발언은 문맥에 들어가지 않는다
    spoken = {(s["name"], s["text"]) for s in debate.speeches}
    assert all(entry in spoken for entry in debate.ctx.entries if entry[0] != "주최자 지시")


def test_audience_question_is_relayed_but_not_binding(monkeypatch):
    """청중 질문은 진행자가 받아 묻는 질문이다. 전원이 따라야 하는 지시로 남지 않는다."""
    async def drive(debate):
        while debate.turn_no < 6:
            await asyncio.sleep(0.01)
        debate.control("question", "비용은 누가 냅니까?")

    debate, _ = _run(_config(speed="fast", gap_scale=0.2, max_turns=18), monkeypatch, latency=0.02, drive=drive)
    assert debate.state == "ended"
    names = [who for who, _ in debate.ctx.entries]
    assert "청중" in names and "주최자 지시" not in names
    assert debate.ctx.entries[names.index("청중") + 1][0] == "진행자"
    assert debate.orders == []
    spoken = {(s["name"], s["text"]) for s in debate.speeches}
    assert all(entry in spoken for entry in debate.ctx.entries if entry[0] != "청중")   # 버린 발언은 문맥에 없다


def test_host_order_while_paused_resumes_the_debate(monkeypatch):
    async def drive(debate):
        while debate.turn_no < 3:
            await asyncio.sleep(0.01)
        debate.control("pause")
        assert debate.state == "paused"
        debate.control("instruct", "이제 비용 이야기로 넘어가라")
        assert debate.state == "running"

    debate, _ = _run(_config(speed="fast", gap_scale=0.1, max_turns=14), monkeypatch, latency=0.01, drive=drive)
    assert debate.state == "ended"
    assert ("주최자 지시", "이제 비용 이야기로 넘어가라") in debate.ctx.entries


def test_interjection_cuts_the_previous_speech(monkeypatch):
    cfg = _config(speed="fast", gap_scale=0.1, max_turns=28, moderator=False)
    debate = None

    def force_high_urge(real):
        async def judge(**kw):
            data, usage = await real(**kw)
            for row in data["participants"]:
                row["urge"], row["intent"] = 10, "rebut"
            data["moderator_needed"] = False
            return data, usage
        return judge

    saved = {}
    monkeypatch.setattr(store, "save_debate", lambda rec: saved.update(rec))
    provider = MockProvider(latency=0.01, seed=5)
    debate = Debate("d_cut", cfg, provider)

    async def go():
        debate.task = asyncio.create_task(debate.run())
        while debate.ctx is None:
            await asyncio.sleep(0.005)
        debate.ctx.judge = force_high_urge(debate.ctx.judge)
        await asyncio.wait_for(debate.task, timeout=120)

    asyncio.run(go())
    assert debate.state == "ended"   # 시간 안에 끝나지 못해 중단된 것을 다른 실패로 착각하지 않게
    cut = [s for s in debate.speeches if s["cut"]]
    assert cut, "끼어들기로 끊긴 발언이 하나는 있어야 한다"
    assert all(s["text"].endswith("—") for s in cut)
    assert debate.ctx.entries == [(s["name"], s["text"]) for s in debate.speeches]
    following = [debate.speeches[i + 1] for i, s in enumerate(debate.speeches[:-1]) if s["cut"]]
    assert all(s["interject"] for s in following)


def test_pause_and_resume(monkeypatch):
    async def drive(debate):
        while debate.turn_no < 3:
            await asyncio.sleep(0.01)
        debate.control("pause")
        before = len(debate.events)
        await asyncio.sleep(0.3)
        assert len(debate.events) <= before + 3
        debate.control("resume")

    debate, _ = _run(_config(speed="fast", gap_scale=0.1, max_turns=12), monkeypatch, latency=0.01, drive=drive)
    assert debate.state == "ended"


def test_compaction_is_reported(monkeypatch):
    debate, _ = _run(_config(max_turns=40, compact_threshold=300), monkeypatch)
    assert any(e["type"] == "compaction" for e in debate.events)


def test_auto_length_uses_the_directors_choice(monkeypatch):
    """자동 길이: 자유토론의 발언 지시에 연출자가 고른 길이가 들어가고, 고정 길이에서는 늘 같은 길이가 들어간다."""
    seen = []

    def record(real):
        async def speak(**kw):
            seen.append(kw["directive"])
            return await real(**kw)
        return speak

    for length in ("auto", "short"):
        seen.clear()
        monkeypatch.setattr(store, "save_debate", lambda rec: None)
        debate = Debate("d_len", _config(length=length, moderator=False, mode="free", max_turns=14), MockProvider(latency=0, seed=11))

        async def go():
            debate.task = asyncio.create_task(debate.run())
            while debate.ctx is None:
                await asyncio.sleep(0.001)
            debate.ctx.speak = record(debate.ctx.speak)
            await asyncio.wait_for(debate.task, timeout=60)

        asyncio.run(go())
        assert debate.state == "ended"
        lengths = {d.split("길이: ")[1].split("문장")[0] for d in seen if "길이: " in d and "마지막 발언" not in d and "끼어" not in d}
        if length == "auto":
            assert len(lengths) >= 2, lengths          # 짧은 호흡과 긴 호흡이 섞인다
        else:
            assert lengths == {"1~2"}, lengths


def test_progress_is_saved_after_every_speech(monkeypatch):
    """발언이 끝날 때마다 저장한다. 서버가 꺼져도 그 발언까지는 남는다."""
    saves = []
    monkeypatch.setattr(store, "save_debate", lambda rec: saves.append(json.loads(json.dumps(rec, ensure_ascii=False))))
    debate = Debate("d_save", _config(max_turns=12), MockProvider(latency=0, seed=3))
    asyncio.run(debate.run())
    counts = [len(rec["speeches"]) for rec in saves]
    assert counts[:4] == [0, 1, 2, 3]                       # 시작할 때 한 번, 그 뒤로 발언마다
    assert counts[-1] == len(debate.speeches)
    mid = saves[3]
    assert mid["state"] == "running" and mid["resume"]["turn_no"] == 3
    assert [e[1] for e in mid["resume"]["entries"]] == [s["text"] for s in mid["speeches"]]
    assert mid["resume"]["cfg"]["participants"][0]["hidden"] == "속내"   # 이어 가려면 숨은 속내와 자료 전문이 필요하다
    assert saves[-1]["state"] == "ended" and saves[-1]["resume"] is None  # 끝난 토론에는 남기지 않는다


@pytest.mark.parametrize("stop_after", [3, 8, 13])
def test_interrupted_debate_resumes_after_the_last_finished_speech(monkeypatch, stop_after):
    """서버가 꺼진 것처럼 중간 저장본만 남은 토론을 다시 세워 끝까지 간다 (모두발언 중, 자유토론 중, 마무리 발언 중)."""
    saves = []
    monkeypatch.setattr(store, "save_debate", lambda rec: saves.append(json.loads(json.dumps(rec, ensure_ascii=False))))
    asyncio.run(Debate("d_res", _config(max_turns=16), MockProvider(latency=0, seed=3)).run())
    record = next(rec for rec in saves if len(rec["speeches"]) == stop_after)   # 이 발언이 끝난 직후에 꺼졌다
    before = copy.deepcopy(record["speeches"])
    saves.clear()

    debate = Debate.restore(record, MockProvider(latency=0, seed=9))
    asyncio.run(debate.run())
    assert debate.state == "ended"
    assert debate.speeches[:stop_after] == before                              # 앞의 발언은 그대로
    assert [s["id"] for s in debate.speeches] == list(range(1, len(debate.speeches) + 1))
    assert [e["i"] for e in debate.events] == list(range(len(debate.events)))  # 이벤트 번호가 끊기지 않는다
    assert debate.ctx.entries == [(s["name"], s["text"]) for s in debate.speeches]
    kinds = [s["kind"] for s in debate.speeches]
    assert kinds[0] == "open" and kinds[1:5] == ["statement"] * 4              # 모두발언을 빠뜨리거나 두 번 하지 않는다
    assert kinds[-5:-1] == ["closing"] * 4 and kinds[-1] == "wrap"
    assert kinds.count("closing") == 4 and kinds.count("wrap") == 1
    assert [e["phase"] for e in debate.events if e["type"] == "phase"] == ["opening", "statements", "free", "closing", "wrap"]
    assert sum(1 for e in debate.events if e["type"] == "init") == 1
    assert any(e["type"] == "notice" and e.get("kind") == "resume" for e in debate.events)
    assert debate.cost >= record["cost"] and saves[-1]["minutes"]["title"]


def test_aborted_debate_drops_the_half_shown_speech_on_resume(monkeypatch):
    """중단된 토론: 화면에 나오다 만 발언은 버리고, 끝난 발언 다음부터 이어 간다."""
    saved = {}
    monkeypatch.setattr(store, "save_debate", lambda rec: saved.update(json.loads(json.dumps(rec, ensure_ascii=False))))
    debate = Debate("d_abort", _config(speed="fast", gap_scale=0.1, max_turns=14), MockProvider(latency=0.01, seed=3))

    async def go():
        debate.task = asyncio.create_task(debate.run())
        while not (debate.turn_no >= 4 and debate._pos > 0 and not debate._shown.is_set()):
            await asyncio.sleep(0.002)
        debate.control("abort")
        await asyncio.gather(debate.task, return_exceptions=True)

    asyncio.run(go())
    assert saved["state"] == "aborted"
    done = len(saved["speeches"])
    assert saved["resume"]["turn_no"] == done and len(saved["events"]) > saved["resume"]["n_events"]
    again = Debate.restore(saved, MockProvider(latency=0, seed=4))
    assert again.turn_no == done and again.events[-1]["type"] != "end"
    asyncio.run(again.run())
    assert again.state == "ended"
    assert [s["id"] for s in again.speeches] == list(range(1, len(again.speeches) + 1))


def _flaky(debate, fail, error):
    """ctx.speak가 처음 fail번은 실패하게 만든다."""
    async def drive(_):
        while debate.ctx is None:
            await asyncio.sleep(0.001)
        real, left = debate.ctx.speak, [fail]

        async def speak(**kw):
            if debate.turn_no >= 3 and left[0] > 0:
                left[0] -= 1
                raise error
            return await real(**kw)
        debate.ctx.speak = speak
    return drive


def test_failed_call_is_retried_without_stopping(monkeypatch):
    """AI 호출이 한두 번 실패해도 스스로 다시 시도해 토론이 멈추지 않는다."""
    monkeypatch.setattr(store, "save_debate", lambda rec: None)
    monkeypatch.setattr(engine, "RETRY_WAITS", (0.01, 0.01))
    debate = Debate("d_retry", _config(max_turns=12), MockProvider(latency=0, seed=3))

    async def go():
        debate.task = asyncio.create_task(debate.run())
        await _flaky(debate, 2, ProviderError("잠깐의 장애"))(debate)
        await asyncio.wait_for(debate.task, timeout=30)

    asyncio.run(go())
    assert debate.state == "ended"
    notes = [e for e in debate.events if e["type"] == "notice" and "다시 시도" in e.get("text", "")]
    assert len(notes) == 2
    assert not any(e["type"] == "error" for e in debate.events)
    assert [s["id"] for s in debate.speeches] == list(range(1, len(debate.speeches) + 1))


@pytest.mark.parametrize("fail,error", [(3, ProviderError("계속되는 장애")), (1, ProviderError("키가 틀림", retry=False))])
def test_after_retries_run_out_it_waits_for_the_viewer(monkeypatch, fail, error):
    """두 번 다시 해도 안 되거나, 다시 해도 소용없는 오류면 멈추고 '이어 하기'를 기다린다."""
    monkeypatch.setattr(store, "save_debate", lambda rec: None)
    monkeypatch.setattr(engine, "RETRY_WAITS", (0.01, 0.01))
    debate = Debate("d_stop", _config(max_turns=12), MockProvider(latency=0, seed=3))

    async def go():
        debate.task = asyncio.create_task(debate.run())
        await _flaky(debate, fail, error)(debate)
        while debate.state != "error":
            await asyncio.sleep(0.005)
        debate.control("resume")
        await asyncio.wait_for(debate.task, timeout=30)

    asyncio.run(go())
    assert debate.state == "ended"
    assert sum(1 for e in debate.events if e["type"] == "error") == 1


def test_minutes_are_streamed_to_viewers_but_not_kept_in_the_record(monkeypatch):
    """회의록은 쓰이는 대로 화면에 보내고, 기록에는 다 쓴 것만 남긴다."""
    monkeypatch.setattr(store, "save_debate", lambda rec: None)
    debate = Debate("d_min", _config(max_turns=12), MockProvider(latency=0.05, seed=3))
    queue: asyncio.Queue = asyncio.Queue()
    debate.subs.add(queue)
    asyncio.run(debate.run())
    seen = []
    while not queue.empty():
        seen.append(queue.get_nowait())
    partial = [e for e in seen if e["type"] == "minutes_partial"]
    assert len(partial) >= 2 and all(e["i"] == -1 for e in partial)
    assert partial[0]["minutes"].get("title")                                     # 앞에서부터 차오른다
    assert len(json.dumps(partial[0]["minutes"])) < len(json.dumps(partial[-1]["minutes"]))
    assert not any(e["type"] == "minutes_partial" for e in debate.events)
    assert [e["i"] for e in debate.events] == list(range(len(debate.events)))
    assert debate.minutes["title"] and debate.events[-2]["type"] == "minutes"
