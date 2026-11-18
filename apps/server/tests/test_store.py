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


def test_presets_are_the_famous_people_set():
    import json
    people = json.loads((store.PRESETS / "personas.json").read_text(encoding="utf-8"))
    names = [p["name"] for p in people]
    for name in ("일론 머스크", "스티브 잡스", "워런 버핏", "소크라테스", "니콜로 마키아벨리", "장 자크 루소", "박태준",
                 "박정희", "이순신", "세종대왕", "마하트마 간디", "샘 올트먼", "도널드 트럼프",
                 "프리드리히 니체", "이마누엘 칸트", "노자", "나폴레옹", "블라디미르 푸틴", "시진핑", "아이작 뉴턴", "정주영", "이건희", "데미스 하사비스", "다리오 아모데이",
                 "제프 베이조스", "마크 저커버그", "젠슨 황", "찰리 멍거", "조지 소로스", "레이 달리오", "캐시 우드", "마이클 버리",
                 "애덤 스미스", "존 메이너드 케인스", "카를 마르크스", "전태일", "레이첼 카슨", "앨런 튜링", "마리 퀴리", "정약용",
                 "프리드리히 하이에크", "알베르트 아인슈타인", "로버트 오펜하이머", "공자", "에이브러햄 링컨", "윈스턴 처칠",
                 "파블로 피카소", "헨리 포드", "김정일"):
        assert name in names, name
    assert len(names) == len(set(names)) == 49
    for p in people:
        assert p["id"].startswith("preset_") and p["title"] and p["personality"] and p["speech"] and len(p["claims"]) >= 2
        assert p["hidden"] == ""          # 실존 인물에게 숨은 속내를 지어 붙이지 않는다
    assert sorted(p["avatar"]["variant"] for p in people) == list(range(49))   # 인물마다 자기 얼굴 아바타 하나
    assert all(p["avatar"]["set"] == "figure" for p in people)


def test_old_preset_set_is_replaced_once_and_own_personas_are_kept(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    store.list_personas()
    mine = store.save_persona({"name": "내가 만든 인물", "title": "직접 만듦"})
    store.save_persona({"id": "preset_engineer", "name": "강도현", "title": "예전 기본 인물"})
    store.set_meta("presets", "1")                    # 예전 묶음을 쓰던 보관함인 것처럼
    monkeypatch.setattr(store, "_ready_for", None)    # 서버를 다시 켠다
    names = [p["name"] for p in store.list_personas()]
    assert "강도현" not in names and "일론 머스크" in names and "내가 만든 인물" in names
    assert len(names) == 50   # 기본 인물 49명 + 내가 만든 인물
    store.delete_persona("preset_musk")
    monkeypatch.setattr(store, "_ready_for", None)
    assert "일론 머스크" not in [p["name"] for p in store.list_personas()]   # 지운 기본 인물은 되살아나지 않는다
    assert mine["id"] in [p["id"] for p in store.list_personas()]
