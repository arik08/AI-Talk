"""P-GPT 설정: 환경 변수 별칭과 우선순위, 인증 토큰, 주소 정리, 프로바이더 선택 순서."""
import base64
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aitalk import providers, store  # noqa: E402
from aitalk.config import PGPT_CODE_NAMES, PGPT_KEY_NAMES, ROOT, settings  # noqa: E402
from aitalk.providers.pgpt import PgptProvider, build_token, normalize_base_url  # noqa: E402

ALL = (*PGPT_KEY_NAMES, *PGPT_CODE_NAMES, "COMPANY_CODE", "PGPT_BASE_URL", "PGPT_WEB_SEARCH_TOOL")


def _clean(monkeypatch, file: dict | None = None, env: dict | None = None) -> None:
    monkeypatch.setattr(settings, "_file", dict(file or {}))
    for name in ALL:
        monkeypatch.delenv(name, raising=False)
    for name, value in (env or {}).items():
        monkeypatch.setenv(name, value)


def test_key_and_code_follow_alias_order(monkeypatch):
    _clean(monkeypatch, file={"API_KEY": "file-generic", "PGPT_API_KEY": "file-pgpt",
                              "EMPLOYEE_NO": "E3", "PGPT_EMPNO": "E2", "PGPT_SYSTEM_CODE": "E1"})
    assert settings.pgpt["api_key"] == "file-pgpt" and settings.pgpt["system_code"] == "E1"
    _clean(monkeypatch, file={"API_KEY": "file-generic", "EMPLOYEE_NO": "E3", "PGPT_EMPNO": "E2"})
    assert settings.pgpt["api_key"] == "file-generic" and settings.pgpt["system_code"] == "E2"
    _clean(monkeypatch, file={"EMPLOYEE_NO": "E3"})
    assert settings.pgpt["system_code"] == "E3" and settings.pgpt["api_key"] == ""


def test_env_file_wins_over_windows_environment_for_the_whole_alias_group(monkeypatch):
    # .env의 뒤쪽 별칭이 OS 환경 변수의 앞쪽 별칭보다 먼저다
    _clean(monkeypatch, file={"API_KEY": "from-file", "EMPLOYEE_NO": "file-emp"},
           env={"PGPT_API_KEY": "from-os", "PGPT_SYSTEM_CODE": "os-code"})
    assert settings.pgpt["api_key"] == "from-file" and settings.pgpt["system_code"] == "file-emp"
    _clean(monkeypatch, env={"API_KEY": "os-generic", "PGPT_API_KEY": "os-pgpt", "PGPT_EMPNO": "os-emp"})
    assert settings.pgpt["api_key"] == "os-pgpt" and settings.pgpt["system_code"] == "os-emp"


def test_blank_values_fall_through_to_the_next_candidate(monkeypatch):
    _clean(monkeypatch, file={"PGPT_API_KEY": "", "API_KEY": "  ", "PGPT_SYSTEM_CODE": "", "PGPT_EMPNO": "E2"},
           env={"PGPT_API_KEY": "", "API_KEY": "os-generic"})
    assert settings.pgpt["api_key"] == "os-generic" and settings.pgpt["system_code"] == "E2"


def test_company_code_defaults_to_30_and_token_carries_it(monkeypatch):
    _clean(monkeypatch)
    assert settings.pgpt["company_code"] == "30"
    _clean(monkeypatch, file={"COMPANY_CODE": "31"})
    assert settings.pgpt["company_code"] == "31"
    token = json.loads(base64.b64decode(build_token("키", "E1")).decode("utf-8"))
    assert token == {"apiKey": "키", "systemCode": "E1", "companyCode": "30"}
    assert json.loads(base64.b64decode(build_token("k", "E1", "31")))["companyCode"] == "31"


def test_base_url_is_normalized_to_v1():
    want = "http://pgpt.example/s0la01-gpt/v1"
    for given in (want, want + "/", want + "/responses", want + "/chat/completions", want + "/responses/compact",
                  "http://pgpt.example/s0la01-gpt", "http://pgpt.example/s0la01-gpt/", want + "?x=1#frag"):
        assert normalize_base_url(given) == want, given


def test_status_names_the_variables_without_showing_values(monkeypatch):
    info = PgptProvider().status()
    assert info["ready"] is False
    for name in ("PGPT_API_KEY", "API_KEY", "PGPT_EMPNO", "PGPT_SYSTEM_CODE", "EMPLOYEE_NO"):
        assert name in info["message"]
    _clean(monkeypatch, file={"PGPT_API_KEY": "sk-secret-value", "PGPT_EMPNO": "123456"})
    monkeypatch.setattr(providers, "_cached", {})
    monkeypatch.delenv("AITALK_FORCE_PROVIDER", raising=False)
    rows = {r["name"]: r for r in providers.overview()}
    assert rows["pgpt"]["ready"] is True
    assert "sk-secret-value" not in json.dumps(rows, ensure_ascii=False) and "123456" not in json.dumps(rows)


def test_provider_choice_order_is_forced_then_saved_then_env(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DB", tmp_path / "t.db")
    monkeypatch.setattr(store, "_ready_for", None)
    monkeypatch.setattr(providers, "_chosen", None)
    monkeypatch.setattr(providers, "_loaded", False)
    monkeypatch.delenv("AITALK_FORCE_PROVIDER", raising=False)
    _clean(monkeypatch, file={"AITALK_PROVIDER": "claude"})
    assert providers.active_name() == "claude"            # .env
    providers.set_active("pgpt")
    assert providers.active_name() == "pgpt"              # 설정 화면에서 고른 것
    monkeypatch.setenv("AITALK_FORCE_PROVIDER", "mock")
    assert providers.active_name() == "mock"              # 시험용 강제값


def test_openai_sdk_requirement_is_pinned():
    lines = (ROOT / "apps" / "server" / "requirements.txt").read_text(encoding="utf-8").splitlines()
    assert "openai>=3.37.0,<4" in lines
