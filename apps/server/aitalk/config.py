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
        # AITALK_FORCE_PROVIDER는 시험할 때만 쓴다 (.env를 건드리지 않고 mock으로 띄우기)
        forced = os.environ.get("AITALK_FORCE_PROVIDER", "")
        return (forced or self.get("AITALK_PROVIDER", "mock")).lower()


    @property
    def host(self) -> str:
        return self.get("AITALK_HOST", "127.0.0.1")

    @property
    def port(self) -> int:
        try:
            return int(self.get("AITALK_PORT", "8765"))
        except ValueError:
            return 8765


settings = Settings()


def lan_addresses() -> list[str]:
    """이 PC가 같은 망에서 불리는 주소들."""
    import socket
    found: list[str] = []
    try:   # 밖으로 나가는 길에 쓰이는 주소. 실제로 아무것도 보내지 않는다
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("10.255.255.255", 1))
            found.append(probe.getsockname()[0])
    except OSError:
        pass
    try:
        for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
            if ip not in found:
                found.append(ip)
    except OSError:
        pass
    return [ip for ip in found if not ip.startswith("127.")]
