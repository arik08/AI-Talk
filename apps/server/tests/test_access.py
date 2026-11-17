"""다른 PC에서 들어올 때의 접속 코드 확인과, 회의록 API를 본다."""
import sys
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
    store.save_debate({
        "id": "d_min", "created": "2026-11-17T10:00:00", "state": "ended", "turns": 2, "seconds": 30, "provider": "mock",
        "moderator": None,
        "config": {"topic": "시험 주제", "model": "mock-large", "effort": "low",
                   "participants": [{"name": "가온", "title": "찬성"}, {"name": "나래", "title": "반대"}]},
        "speeches": [{"id": 1, "name": "가온", "text": "저는 찬성합니다."}, {"id": 2, "name": "나래", "text": "저는 반대합니다."}],
        "events": []})
    res = client.post("/api/debates/d_min/minutes")
    assert res.status_code == 200
    minutes = res.json()
    assert minutes["title"] and minutes["discussions"]
    assert store.load_debate("d_min")["minutes"]["title"] == minutes["title"]
    assert client.post("/api/debates/d_none/minutes").status_code == 404
