"""다른 PC에서 들어올 때의 접속 코드 확인과, 끝난 토론에 대한 API(회의록, 판정, 묻고 답하기, 이어 하기)를 본다."""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from aitalk import app as app_module  # noqa: E402
from aitalk import store  # noqa: E402
from aitalk.config import settings  # noqa: E402
from aitalk.providers.mock import MockProvider  # noqa: E402


def _client(monkeypatch, tmp_path, code=""):
    monkeypatch.setattr(store, "DB", tmp_path / "t.db")
    monkeypatch.setattr(store, "_ready_for", None)
    monkeypatch.setitem(settings._file, "AITALK_ACCESS_CODE", code)
    monkeypatch.setattr(app_module, "get_provider", lambda: MockProvider(latency=0, seed=1))
    return TestClient(app_module.app)   # 시험용 클라이언트의 주소는 127.0.0.1이 아니므로 "다른 PC"로 취급된다


def _lines(res):
    """흘려보낸 응답의 줄들. 마지막 줄이 결과(done)다."""
    assert res.status_code == 200, res.text
    rows = [json.loads(line) for line in res.text.splitlines() if line.strip()]
    assert rows[-1]["type"] == "done", rows[-1]
    return rows


def _ended(debate_id="d_min"):
    store.save_debate({
        "id": debate_id, "created": "2026-11-17T10:00:00", "state": "ended", "turns": 2, "seconds": 30, "provider": "mock",
        "moderator": None,
        "config": {"topic": "시험 주제", "model": "mock-large", "effort": "low",
                   "participants": [{"name": "가온", "title": "찬성"}, {"name": "나래", "title": "반대"}]},
        "speeches": [{"id": 1, "name": "가온", "text": "저는 찬성합니다."}, {"id": 2, "name": "나래", "text": "저는 반대합니다."}],
        "events": []})


def test_without_code_everyone_gets_in(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    assert client.get("/api/personas").status_code == 200


def test_with_code_other_pcs_must_enter_it(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path, code="열려라참깨")
    assert client.get("/api/personas").status_code == 401
    assert client.post("/api/enter", json={"code": "틀린코드"}).status_code == 401
    assert client.get("/api/personas").status_code == 401
    assert client.post("/api/enter", json={"code": "열려라참깨"}).status_code == 200
    assert client.get("/api/personas").status_code == 200


def test_minutes_are_written_and_saved_with_the_record(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    monkeypatch.setattr(app_module, "get_provider", lambda: MockProvider(latency=0.3, seed=1))   # 쓰는 데 시간이 걸린다
    _ended()
    rows = _lines(client.post("/api/debates/d_min/minutes"))
    body = rows[-1]
    minutes = body["minutes"]
    assert minutes["title"] and minutes["discussions"]
    partial = [r["minutes"] for r in rows if r["type"] == "partial"]       # 쓰이는 대로 흘러나온다
    assert partial and partial[0].get("title") == minutes["title"] and "conclusion" not in partial[0]
    assert body["cost"] > 0 and body["cost_parts"]["minutes"] > 0      # 회의록을 쓰는 비용이 총 비용에 더해진다
    again = _lines(client.post("/api/debates/d_min/minutes"))[-1]
    assert again["cost_parts"]["minutes"] > body["cost_parts"]["minutes"]  # 다시 쓰면 더 쌓인다
    assert store.load_debate("d_min")["minutes"]["title"] == minutes["title"]
    assert client.post("/api/debates/d_none/minutes").status_code == 404


def test_provider_can_be_switched_and_is_remembered(monkeypatch, tmp_path):
    from aitalk import providers
    monkeypatch.setattr(store, "DB", tmp_path / "t.db")
    monkeypatch.setattr(store, "_ready_for", None)
    monkeypatch.delenv("AITALK_FORCE_PROVIDER", raising=False)
    monkeypatch.setattr(providers, "_chosen", None)
    monkeypatch.setattr(providers, "_loaded", False)
    monkeypatch.setitem(settings._file, "AITALK_PROVIDER", "mock")
    monkeypatch.setitem(settings._file, "AITALK_ACCESS_CODE", "")
    client = TestClient(app_module.app)
    assert client.get("/api/status").json()["provider"] == "mock"
    res = client.post("/api/provider", json={"name": "pgpt"})
    assert res.status_code == 200 and res.json()["provider"] == "pgpt"
    rows = {r["name"]: r for r in res.json()["providers"]}
    assert rows["pgpt"]["active"] and not rows["mock"]["active"]
    monkeypatch.setattr(providers, "_loaded", False)       # 서버를 다시 켠 것처럼
    monkeypatch.setattr(providers, "_chosen", None)
    assert providers.active_name() == "pgpt"                # 마지막 선택을 기억한다
    assert client.post("/api/provider", json={"name": "없는것"}).status_code == 400


def test_cast_from_library_picks_existing_personas_and_adapts_their_stance(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    library = {p["id"]: p for p in client.get("/api/personas").json()}
    res = client.post("/api/cast/library", json={"topic": "AI가 만든 창작물에 저작권을 줘야 하나", "count": 3})
    assert res.status_code == 200
    body = res.json()
    people = body["personas"]
    assert len(people) == 3 and len({p["id"] for p in people}) == 3 and body["cost"] > 0
    for p in people:
        base = library[p["id"]]                           # 보관함에 있던 인물이다
        assert (p["name"], p["title"], p["personality"], p["speech"], p["avatar"]) ==                (base["name"], base["title"], base["personality"], base["speech"], base["avatar"])
        assert p["viewpoint"] != base["viewpoint"] and p["claims"] != base["claims"]   # 입장은 주제에 맞춰 새로 받는다
    # 직접 고른 사람은 반드시 들어가고 맨 앞에 온다. 남은 자리만 자동으로 채운다
    mine = list(library)[-2:]
    res = client.post("/api/cast/library", json={"topic": "주제", "count": 4, "picked": mine + ["없는사람", mine[0]]})
    ids = [p["id"] for p in res.json()["personas"]]
    assert ids[:2] == mine and len(ids) == 4 and len(set(ids)) == 4
    assert client.post("/api/cast/library", json={"topic": " ", "count": 3}).status_code == 400
    for pid in list(library)[1:]:
        client.delete(f"/api/personas/{pid}")
    assert client.post("/api/cast/library", json={"topic": "주제", "count": 3}).status_code == 400   # 고를 사람이 모자라다


def test_library_picks_ignore_unknown_and_duplicate_ids_and_fill_up():
    from aitalk import prompts
    library = [{"id": f"p{i}", "name": f"인물{i}", "viewpoint": "원래 관점", "claims": ["원래 주장"], "concede": "원래"} for i in range(4)]
    picks = [{"id": "[p2]", "viewpoint": "새 관점", "claims": ["새 주장", " "], "concede": ""},
             {"id": "없는사람", "viewpoint": "x", "claims": [], "concede": ""},
             {"id": "p2", "viewpoint": "겹침", "claims": [], "concede": ""}, "잘못된 값"]
    out = prompts.merge_picks(picks, library, 3)
    assert [p["id"] for p in out] == ["p2", "p0", "p1"]
    assert out[0]["viewpoint"] == "새 관점" and out[0]["claims"] == ["새 주장"] and out[0]["concede"] == "원래"
    assert out[1]["viewpoint"] == "원래 관점"             # 모자라서 채운 사람은 원래 입장 그대로
    out = prompts.merge_picks(picks, library, 3, ["p3", "p2"])
    assert [p["id"] for p in out] == ["p3", "p2", "p0"]
    assert out[0]["viewpoint"] == "원래 관점" and out[1]["viewpoint"] == "새 관점"   # 모델이 빠뜨린 사람도 들어간다
    text = prompts.pick_prompt("주제", 3, "auto", library, required=["p3"])
    assert "[p3] 인물3" in text and "남은 2자리" in text
    text = prompts.pick_prompt("주제", 2, "auto", library)
    assert "- [p0] 인물0" in text and "참가자 2명" in text


def test_verdict_ranks_every_participant_and_is_saved(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    _ended()
    body = _lines(client.post("/api/debates/d_min/verdict"))[-1]
    verdict = body["verdict"]
    assert [r["name"] for r in verdict["ranking"]] == ["가온", "나래"]           # 참가자 전원, 점수가 높은 순서
    assert verdict["ranking"][0]["score"] >= verdict["ranking"][1]["score"]
    assert verdict["winner"] == "가온" and verdict["summary"]
    assert body["cost_parts"]["extra"] > 0
    assert store.load_debate("d_min")["verdict"]["winner"] == "가온"
    assert client.post("/api/debates/d_none/verdict").status_code == 404


def test_questions_about_a_finished_debate_are_answered_and_kept(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    _ended()
    rows = _lines(client.post("/api/debates/d_min/ask", json={"question": "누가 더 설득력 있었어?"}))
    answer = "".join(r["text"] for r in rows if r["type"] == "delta")
    assert rows[-1]["qa"] == [{**rows[-1]["qa"][0], "q": "누가 더 설득력 있었어?", "a": answer.strip()}]
    assert "누가 더 설득력 있었어?" in answer                                   # 시험용 답변은 질문을 되짚는다
    second = _lines(client.post("/api/debates/d_min/ask", json={"question": "비용 얘기는?"}))[-1]
    assert [item["q"] for item in second["qa"]] == ["누가 더 설득력 있었어?", "비용 얘기는?"]
    assert second["cost_parts"]["extra"] > rows[-1]["cost_parts"]["extra"]
    assert len(store.load_debate("d_min")["qa"]) == 2
    assert client.post("/api/debates/d_min/ask", json={"question": "  "}).status_code == 400


def test_analyst_is_told_it_is_not_a_participant():
    from aitalk import prompts
    speeches = [{"id": 1, "name": "가온", "text": "찬성합니다.", "at": 0}]
    context = prompts.analyst_context("시험 주제", ["가온(찬성)"], speeches, {"overview": "요지"}, None)
    assert "참가자가 아닙니다" in context and "【#1 · 00:00 · 가온】 찬성합니다." in context and "요지" in context
    prompt = prompts.analyst_prompt([{"q": "앞 질문", "a": "앞 답"}], "새 질문")
    assert prompt.index("앞 질문") < prompt.index("앞 답") < prompt.index("질문: 새 질문")


def test_interrupted_debate_is_listed_as_such_and_can_be_resumed(monkeypatch, tmp_path):
    """서버가 꺼지며 끊긴 토론은 '진행 중'이 아니라 끊긴 것으로 보이고, 이어 하기로 끝까지 간다."""
    import asyncio

    from aitalk.engine import Debate

    client = _client(monkeypatch, tmp_path)
    provider = MockProvider(latency=0, seed=2)
    monkeypatch.setattr(app_module, "get_provider", lambda: provider)
    monkeypatch.setattr(app_module, "LIVE", {})
    people = [{"id": f"s{i}", "name": n, "title": "시험 인물", "viewpoint": "찬성", "claims": ["핵심입니다"], "hidden": "속내"}
              for i, n in enumerate(["가온", "나래"], 1)]
    cfg = {"topic": "시험 주제", "participants": people, "moderator": True, "mode": "mixed", "max_turns": 10,
           "max_minutes": None, "length": "normal", "speed": "instant", "gap_scale": 0, "search": "off",
           "model": "mock-large", "effort": "low", "summary": True, "seed": 7,
           "materials": [{"name": "자료", "text": "비밀 자료 전문"}]}
    saves = []
    real_save = store.save_debate
    monkeypatch.setattr(store, "save_debate", lambda rec: saves.append(json.loads(json.dumps(rec, ensure_ascii=False))))
    asyncio.run(Debate("d_cut", cfg, provider).run())
    monkeypatch.setattr(store, "save_debate", real_save)
    store.save_debate(next(rec for rec in saves if len(rec["speeches"]) == 4))   # 네 번째 발언 뒤에 서버가 꺼졌다

    assert client.get("/api/debates").json()[0]["state"] == "interrupted"
    seen = client.get("/api/debates/d_cut").json()
    assert seen["state"] == "interrupted" and seen["resumable"] and not seen["live"]
    assert seen["resume"] is None and "비밀 자료 전문" not in json.dumps(seen, ensure_ascii=False)   # 화면으로는 보내지 않는다
    with client:   # 서버의 이벤트 루프가 도는 동안 이어 하기를 끝까지 지켜본다
        assert client.post("/api/debates/d_cut/resume").json() == {"id": "d_cut"}
        for _ in range(400):
            if store.load_debate("d_cut")["state"] == "ended":
                break
            time.sleep(0.02)
    done = store.load_debate("d_cut")
    assert done["state"] == "ended" and len(done["speeches"]) > 4 and done["speeches"][-1]["kind"] == "wrap"
    after = client.get("/api/debates/d_cut").json()
    assert after["state"] == "ended" and not after["resumable"]
    _ended("d_done")
    assert client.post("/api/debates/d_done/resume").status_code == 400            # 끝난 토론은 이어 갈 수 없다
