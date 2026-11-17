"""경로와 설정. `.env` 값이 OS 환경 변수보다 우선한다."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]  # AI-Talk/
DATA = ROOT / "data"
PRESETS = ROOT / "presets"
WEB_DIST = ROOT / "apps" / "web" / "dist"


def _read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip("'\"")
    return values


class Settings:
    """`.env`를 먼저 보고, 없을 때만 OS 환경 변수를 본다.

    이 PC에는 다른 도구용 OPENAI_* 변수가 잡혀 있어 섞이지 않게 하려는 것이다.
    """

    def __init__(self) -> None:
        self.reload()

    def reload(self) -> None:
        self._file = _read_env_file(ROOT / ".env")

    def get(self, key: str, default: str = "") -> str:
        value = self._file.get(key)
        if value is None or value == "":
            value = os.environ.get(key, "")
        return value or default

    @property
    def provider(self) -> str:
        return self.get("AITALK_PROVIDER", "mock").lower()


settings = Settings()
