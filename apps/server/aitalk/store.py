"""저장소. 페르소나 보관함과 토론 기록을 SQLite 파일 하나(data/aitalk.db)에 둔다.

예전 버전이 남긴 JSON 파일(data/personas.json, data/debates/*.json)이 있으면 처음 한 번 옮겨 온다.
"""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
import threading
import uuid
from contextlib import closing
from pathlib import Path
from typing import Optional

from .config import DATA, PRESETS

DB: Path = DATA / "aitalk.db"
_lock = threading.Lock()
_ready_for: Optional[Path] = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS personas (
    id      TEXT PRIMARY KEY,
    name    TEXT NOT NULL,
    data    TEXT NOT NULL,          -- 인물 전체(JSON)
    sort    INTEGER NOT NULL,       -- 큰 값이 목록의 앞
    updated TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS debates (
    id           TEXT PRIMARY KEY,
    created      TEXT NOT NULL,
    topic        TEXT NOT NULL,
    state        TEXT NOT NULL,
    turns        INTEGER NOT NULL DEFAULT 0,
    seconds      INTEGER NOT NULL DEFAULT 0,
    provider     TEXT NOT NULL DEFAULT '',
    cost         REAL NOT NULL DEFAULT 0,
    participants TEXT NOT NULL,     -- 목록 화면용 요약(JSON)
    record       TEXT NOT NULL      -- 기록 전체(JSON): 설정, 발언, 이벤트, 요약, 회의록
);
CREATE INDEX IF NOT EXISTS debates_created ON debates (created DESC);
"""


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def _now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def _read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _connect() -> sqlite3.Connection:
    global _ready_for
    DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB, timeout=10)
    con.row_factory = sqlite3.Row
    if _ready_for != DB:
        with _lock:
            if _ready_for != DB:
                con.execute("PRAGMA journal_mode=WAL")
                con.executescript(SCHEMA)
                _first_run(con)
                con.commit()
                _ready_for = DB
    return con


PRESET_SET = "11"   # 기본 인물 묶음의 판. 묶음을 바꿀 때 올린다 (2: 유명인 13명, 3: 22명, 4: 인물 아바타, 5: 24명, 6: 27명, 7: 28명, 8: 27명, 9: 투자 구루를 더해 32명, 10: 경제학자·과학자·노동·환경·예술 쪽을 더해 49명, 11: 살아 있는 국내외 유명인 9명을 더해 58명)


def _insert_presets(con: sqlite3.Connection, people: list) -> None:
    for i, p in enumerate(reversed(people)):
        if isinstance(p, dict) and p.get("name"):
            p = {**p, "id": p.get("id") or new_id("p")}
            con.execute("INSERT OR IGNORE INTO personas (id, name, data, sort, updated) VALUES (?, ?, ?, ?, ?)",
                        (p["id"], p["name"], json.dumps(p, ensure_ascii=False), i, _now()))


def _refresh_presets(con: sqlite3.Connection) -> None:
    """기본 인물 묶음이 바뀌었으면 예전 기본 인물(id가 preset_로 시작)을 지우고 새 묶음을 넣는다.

    직접 만든 인물은 건드리지 않는다. 한 번만 한다: 그 뒤에 지운 기본 인물은 되살아나지 않는다.
    """
    row = con.execute("SELECT value FROM meta WHERE key = 'presets'").fetchone()
    if row and row["value"] == PRESET_SET:
        return
    con.execute("DELETE FROM personas WHERE substr(id, 1, 7) = 'preset_'")
    _insert_presets(con, _read_json(PRESETS / "personas.json", []))
    con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('presets', ?)", (PRESET_SET,))


def _first_run(con: sqlite3.Connection) -> None:
    """처음 한 번: 예전 JSON 파일을 옮기고, 보관함이 비어 있으면 기본 인물을 넣는다."""
    if con.execute("SELECT 1 FROM meta WHERE key = 'seeded'").fetchone():
        _refresh_presets(con)
        return
    legacy = DB.parent / "personas.json"
    people = _read_json(legacy, None) if legacy.exists() else None
    if people is None:
        people = _read_json(PRESETS / "personas.json", [])
    _insert_presets(con, people)
    con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('presets', ?)", (PRESET_SET,))
    old_debates = DB.parent / "debates"
    if old_debates.exists():
        for path in old_debates.glob("*.json"):
            rec = _read_json(path, None)
            if rec and rec.get("id"):
                _put_debate(con, rec)
    con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('seeded', ?)", (_now(),))


# ---------------------------------------------------------------- 작은 설정값 (마지막에 고른 AI 등)
def get_meta(key: str) -> Optional[str]:
    with closing(_connect()) as con:
        row = con.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_meta(key: str, value: str) -> None:
    with closing(_connect()) as con, con:
        con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value))


# ---------------------------------------------------------------- 페르소나
def _favorites(con: sqlite3.Connection) -> list[str]:
    row = con.execute("SELECT value FROM meta WHERE key = 'favorites'").fetchone()
    try:
        ids = json.loads(row["value"]) if row else []
    except ValueError:
        ids = []
    return [i for i in ids if isinstance(i, str)] if isinstance(ids, list) else []


def list_personas() -> list[dict]:
    """보관함의 인물. 즐겨 찾는 인물에는 fav=True가 붙는다.

    즐겨찾기는 인물 정보와 따로 둔다(meta의 favorites). 인물을 고쳐 저장하거나 기본 인물 묶음을 새로 넣어도 남는다.
    """
    with closing(_connect()) as con:
        rows = con.execute("SELECT data FROM personas ORDER BY sort DESC").fetchall()
        favs = set(_favorites(con))
    people = [json.loads(r["data"]) for r in rows]
    for p in people:
        p["fav"] = p.get("id") in favs
    return people


def set_favorite(persona_id: str, on: bool) -> bool:
    """인물을 즐겨찾기에 넣거나 뺀다. 보관함에 없는 인물이면 False."""
    with closing(_connect()) as con, con:
        if not con.execute("SELECT 1 FROM personas WHERE id = ?", (persona_id,)).fetchone():
            return False
        ids = [i for i in _favorites(con) if i != persona_id]
        if on:
            ids.append(persona_id)
        con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('favorites', ?)", (json.dumps(ids),))
    return True


def save_persona(persona: dict) -> dict:
    persona = {**persona, "id": persona.get("id") or new_id("p")}
    persona.pop("fav", None)   # 즐겨찾기는 따로 둔다
    blob = json.dumps(persona, ensure_ascii=False)
    with closing(_connect()) as con, con:
        if con.execute("SELECT 1 FROM personas WHERE id = ?", (persona["id"],)).fetchone():
            con.execute("UPDATE personas SET name = ?, data = ?, updated = ? WHERE id = ?",
                        (persona["name"], blob, _now(), persona["id"]))
        else:
            top = con.execute("SELECT COALESCE(MAX(sort), 0) + 1 FROM personas").fetchone()[0]
            con.execute("INSERT INTO personas (id, name, data, sort, updated) VALUES (?, ?, ?, ?, ?)",
                        (persona["id"], persona["name"], blob, top, _now()))
    return persona


def delete_persona(persona_id: str) -> None:
    with closing(_connect()) as con, con:
        con.execute("DELETE FROM personas WHERE id = ?", (persona_id,))
        ids = [i for i in _favorites(con) if i != persona_id]
        con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('favorites', ?)", (json.dumps(ids),))


def import_personas(items: list[dict]) -> int:
    added = 0
    with closing(_connect()) as con, con:
        known = {r["id"] for r in con.execute("SELECT id FROM personas")}
        top = con.execute("SELECT COALESCE(MAX(sort), 0) FROM personas").fetchone()[0]
        for item in items:
            if not isinstance(item, dict) or not str(item.get("name", "")).strip():
                continue
            if not item.get("id") or item["id"] in known:
                item = {**item, "id": new_id("p")}
            top += 1
            con.execute("INSERT INTO personas (id, name, data, sort, updated) VALUES (?, ?, ?, ?, ?)",
                        (item["id"], item["name"], json.dumps(item, ensure_ascii=False), top, _now()))
            known.add(item["id"])
            added += 1
    return added


# ---------------------------------------------------------------- 토론 기록
def _put_debate(con: sqlite3.Connection, record: dict) -> None:
    cfg = record.get("config", {})
    people = [{"name": p.get("name"), "color": p.get("color"), "avatar": p.get("avatar")}
              for p in cfg.get("participants", [])]
    con.execute(
        "INSERT OR REPLACE INTO debates (id, created, topic, state, turns, seconds, provider, cost, participants, record) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (record["id"], record.get("created") or _now(), cfg.get("topic", ""), record.get("state", ""),
         int(record.get("turns") or 0), int(record.get("seconds") or 0), record.get("provider", ""),
         float(record.get("cost") or 0), json.dumps(people, ensure_ascii=False),
         json.dumps(record, ensure_ascii=False)))


def save_debate(record: dict) -> None:
    with closing(_connect()) as con, con:
        _put_debate(con, record)


def load_debate(debate_id: str) -> Optional[dict]:
    with closing(_connect()) as con:
        row = con.execute("SELECT record FROM debates WHERE id = ?", (debate_id,)).fetchone()
    return json.loads(row["record"]) if row else None


def delete_debate(debate_id: str) -> None:
    with closing(_connect()) as con, con:
        con.execute("DELETE FROM debates WHERE id = ?", (debate_id,))


def list_debates() -> list[dict]:
    with closing(_connect()) as con:
        rows = con.execute("SELECT id, created, topic, state, turns, seconds, provider, cost, participants "
                           "FROM debates ORDER BY created DESC").fetchall()
    return [{**{k: r[k] for k in ("id", "created", "topic", "state", "turns", "seconds", "provider", "cost")},
             "participants": json.loads(r["participants"])} for r in rows]
