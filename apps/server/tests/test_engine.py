"""mock 프로바이더로 토론 엔진을 끝까지 돌려 본다."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aitalk import store  # noqa: E402
from aitalk.engine import MOD_ID, Debate  # noqa: E402
from aitalk.providers.mock import MockProvider  # noqa: E402


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


def test_audience_question_discards_pregenerated_speech(monkeypatch):
    async def drive(debate):
        while debate.turn_no < 6:
            await asyncio.sleep(0.01)
        debate.control("question", "비용은 누가 냅니까?")

    debate, _ = _run(_config(speed="fast", gap_scale=0.2, max_turns=18), monkeypatch, latency=0.02, drive=drive)
    assert debate.state == "ended"
    names = [who for who, _ in debate.ctx.entries]
    assert "청중" in names
    after = debate.ctx.entries[names.index("청중") + 1]
    assert after[0] == "진행자"
    # 버린 발언은 문맥에 들어가지 않는다
    spoken = {(s["name"], s["text"]) for s in debate.speeches}
    assert all(entry in spoken for entry in debate.ctx.entries if entry[0] != "청중")


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
