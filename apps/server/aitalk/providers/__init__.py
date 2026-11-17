"""어느 AI를 쓸지 고른다.

우선순위: 시험용 강제값(AITALK_FORCE_PROVIDER) > 설정 화면에서 마지막에 고른 것 > .env의 AITALK_PROVIDER.
키는 언제나 .env에서 읽는다.
"""
from __future__ import annotations

import os
from typing import Optional

from .. import store
from ..config import settings
from .base import Provider

NAMES = ("claude", "pgpt", "mock")
LABELS = {"claude": "Claude", "pgpt": "P-GPT", "mock": "시험용(mock)"}
_cached: dict[str, Provider] = {}
_chosen: Optional[str] = None
_loaded = False


def active_name() -> str:
    global _chosen, _loaded
    forced = os.environ.get("AITALK_FORCE_PROVIDER", "").lower()
    if forced in NAMES:
        return forced
    if not _loaded:
        try:
            _chosen = store.get_meta("provider")
        except Exception:  # noqa: BLE001 - 저장소를 못 읽어도 .env의 값으로 켠다
            _chosen = None
        _loaded = True
    if _chosen in NAMES:
        return _chosen
    return settings.provider if settings.provider in NAMES else "mock"


def set_active(name: str) -> None:
    """설정 화면에서 고른 AI를 기억한다. 서버를 다시 켜도 이어진다."""
    global _chosen, _loaded
    if name not in NAMES:
        raise ValueError(name)
    store.set_meta("provider", name)
    _chosen, _loaded = name, True


def build(name: str) -> Provider:
    if name in _cached:
        return _cached[name]
    if name == "claude":
        from .claude import ClaudeProvider
        provider: Provider = ClaudeProvider(settings.get("ANTHROPIC_API_KEY"))
    elif name == "pgpt":
        from .pgpt import PgptProvider
        provider = PgptProvider(
            api_key=settings.get("PGPT_API_KEY"), empno=settings.get("PGPT_EMPNO"),
            system_code=settings.get("PGPT_SYSTEM_CODE"), base_url=settings.get("PGPT_BASE_URL"),
            search_tool=settings.get("PGPT_WEB_SEARCH_TOOL"))
    else:
        from .mock import MockProvider
        provider = MockProvider()
    _cached[name] = provider
    return provider


def get_provider() -> Provider:
    return build(active_name())


def overview() -> list[dict]:
    """세 가지 AI 각각이 쓸 준비가 됐는지. 키 값은 내보내지 않는다."""
    active = active_name()
    rows = []
    for name in NAMES:
        info = build(name).status()
        rows.append({"name": name, "label": LABELS[name], "ready": info["ready"], "message": info["message"],
                     "active": name == active})
    return rows
