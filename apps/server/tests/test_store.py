"""SQLite 저장소가 페르소나와 토론 기록을 넣고, 찾고, 지우는지 본다."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aitalk import store  # noqa: E402


def _fresh(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB", tmp_path / "t.db")
    monkeypatch.setattr(store, "_ready_for", None)


def test_first_run_seeds_presets_once(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    people = store.list_personas()
    assert len(people) >= 5 and all(p["name"] for p in people)
    for p in people:
        store.delete_persona(p["id"])
    monkeypatch.setattr(store, "_ready_for", None)   # 서버를 다시 켠 것처럼
    assert store.list_personas() == []               # 다 지운 뒤에 기본 인물이 되살아나지 않는다


def test_persona_save_update_delete_and_order(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    before = len(store.list_personas())
    saved = store.save_persona({"name": "가온", "title": "시험"})
    assert saved["id"]
    assert store.list_personas()[0]["name"] == "가온"            # 새로 만든 인물이 맨 앞
    store.save_persona({**saved, "title": "고침"})
    assert len(store.list_personas()) == before + 1
    assert store.list_personas()[0]["title"] == "고침"
    assert store.import_personas([{"name": "나래"}, {"id": saved["id"], "name": "겹침"}, {"name": ""}, "잘못된 값"]) == 2
    ids = [p["id"] for p in store.list_personas()]
    assert len(ids) == len(set(ids))
    store.delete_persona(saved["id"])
    assert all(p["id"] != saved["id"] for p in store.list_personas())


def test_debate_round_trip_and_minutes_update(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    record = {"id": "d_one", "created": "2026-11-17T10:00:00", "state": "ended", "turns": 12, "seconds": 300,
              "provider": "mock", "cost": 0.12,
              "config": {"topic": "시험 주제", "participants": [{"name": "가온", "color": "#E0764A", "avatar": {"set": "bot", "variant": 1}}]},
              "speeches": [{"id": 1, "name": "가온", "text": "안녕하세요."}], "events": [{"i": 0, "type": "init"}]}
    store.save_debate(record)
    store.save_debate({**record, "id": "d_two", "created": "2026-11-18T10:00:00"})
    listing = store.list_debates()
    assert [d["id"] for d in listing] == ["d_two", "d_one"]        # 최근 것이 먼저
    assert listing[1]["topic"] == "시험 주제" and listing[1]["participants"][0]["name"] == "가온"
    assert "events" not in listing[0]                               # 목록에는 무거운 내용을 싣지 않는다
    loaded = store.load_debate("d_one")
    assert loaded["speeches"][0]["text"] == "안녕하세요."
    store.save_debate({**loaded, "minutes": {"title": "회의록"}})
    assert store.load_debate("d_one")["minutes"]["title"] == "회의록"
    assert len(store.list_debates()) == 2
    store.delete_debate("d_one")
    assert store.load_debate("d_one") is None
