"""파일(JSON) 저장. 페르소나 보관함과 토론 기록."""
from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Optional

from .config import DATA, PRESETS

PERSONAS = DATA / "personas.json"
DEBATES = DATA / "debates"


def _read(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


# ---- 페르소나 ----
def list_personas() -> list[dict]:
    if not PERSONAS.exists():
        _write(PERSONAS, _read(PRESETS / "personas.json", []))  # 처음에는 기본 인물을 넣어 둔다
    return _read(PERSONAS, [])


def save_persona(persona: dict) -> dict:
    people = list_personas()
    persona = {**persona, "id": persona.get("id") or new_id("p")}
    for i, p in enumerate(people):
        if p["id"] == persona["id"]:
            people[i] = persona
            break
    else:
        people.insert(0, persona)
    _write(PERSONAS, people)
    return persona


def delete_persona(persona_id: str) -> None:
    _write(PERSONAS, [p for p in list_personas() if p["id"] != persona_id])


def import_personas(items: list[dict]) -> int:
    people = list_personas()
    known = {p["id"] for p in people}
    added = 0
    for item in items:
        if not isinstance(item, dict) or not item.get("name"):
            continue
        if not item.get("id") or item["id"] in known:
            item = {**item, "id": new_id("p")}
        people.append(item)
        known.add(item["id"])
        added += 1
    _write(PERSONAS, people)
    return added


# ---- 토론 기록 ----
def _debate_path(debate_id: str) -> Optional[Path]:
    if not re.fullmatch(r"[a-z0-9_]+", debate_id):
        return None
    return DEBATES / f"{debate_id}.json"


def save_debate(record: dict) -> None:
    path = _debate_path(record["id"])
    if path:
        _write(path, record)


def load_debate(debate_id: str) -> Optional[dict]:
    path = _debate_path(debate_id)
    return _read(path, None) if path else None


def delete_debate(debate_id: str) -> None:
    path = _debate_path(debate_id)
    if path and path.exists():
        path.unlink()


def list_debates() -> list[dict]:
    out = []
    if DEBATES.exists():
        for path in DEBATES.glob("*.json"):
            rec = _read(path, None)
            if not rec:
                continue
            cfg = rec.get("config", {})
            out.append({
                "id": rec["id"], "topic": cfg.get("topic", ""), "created": rec.get("created", ""),
                "state": rec.get("state", ""), "turns": rec.get("turns", 0),
                "seconds": rec.get("seconds", 0), "provider": rec.get("provider", ""),
                "cost": rec.get("cost", 0),
                "participants": [{"name": p["name"], "color": p.get("color"), "avatar": p.get("avatar")}
                                 for p in cfg.get("participants", [])],
            })
    return sorted(out, key=lambda r: r["created"], reverse=True)
