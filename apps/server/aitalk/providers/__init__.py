"""`.env`의 AITALK_PROVIDER 값으로 프로바이더를 고른다."""
from __future__ import annotations

from ..config import settings
from .base import Provider

_cached: dict[str, Provider] = {}


def get_provider() -> Provider:
    name = settings.provider
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
