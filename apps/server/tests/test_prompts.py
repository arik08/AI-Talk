"""모델에게 보내는 공통 글이 설정대로 만들어지는지 본다."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aitalk import prompts  # noqa: E402

PEOPLE = [{"name": "가온", "title": "찬성", "viewpoint": "해야 한다", "claims": ["지금이 적기다"]},
          {"name": "나래", "title": "반대", "viewpoint": "이르다", "claims": ["준비가 안 됐다"]}]


def _shared(**over):
    return prompts.shared_context({"topic": "시험 주제", "participants": PEOPLE, **over}, "")


def test_default_tone_adds_no_instruction():
    base = _shared()
    assert "# 분위기" not in base
    assert _shared(tone="default") == base       # 기본은 아무 지시도 더하지 않는다
    assert _shared(tone="없는값") == base


def test_each_tone_adds_its_own_instruction():
    texts = {tone: _shared(tone=tone) for tone in ("humorous", "serious", "creative")}
    for tone, text in texts.items():
        assert "# 분위기" in text and prompts.TONES[tone] in text
    assert len(set(texts.values())) == 3


def test_concept_and_tone_are_separate_sections():
    text = _shared(concept="심야 라디오 토론", tone="humorous")
    assert text.index("# 이 토론의 설정과 분위기") < text.index("# 분위기") < text.index("# 형식")
    assert "심야 라디오 토론" in text


def test_director_instructions_live_in_the_shared_part_not_the_tail():
    shared = _shared()
    tail = prompts.director_question(["가온", "나래"], "가온")
    assert "# 연출자 호출" in shared and "urge" in shared
    assert len(tail) < 200 and "urge" not in tail   # 꼬리는 캐시가 안 되므로 짧아야 한다


def test_cast_prompt_mentions_tone_only_when_chosen():
    assert "분위기" not in prompts.cast_prompt("주제", 3, "auto", [], "")
    assert "유머러스" in prompts.cast_prompt("주제", 3, "auto", [], "", tone="humorous")


def test_auto_length_is_decided_per_turn_by_the_director():
    auto = _shared(length="auto")
    fixed = _shared(length="short")
    assert "발언 길이는 호출마다" in auto and "발언 길이의 기본은" not in auto
    assert "발언 길이의 기본은 1~2문장" in fixed
    assert "length" in auto and "length" in prompts.director_schema()["properties"]["participants"]["items"]["required"]


def test_timeline_times_come_from_turn_numbers():
    speeches = [{"id": i, "at": (i - 1) * 30} for i in range(1, 9)]          # 30초마다 한 발언
    minutes = {"timeline": [
        {"turns": "#1~#3", "time": "00:00~09:99", "phase": "", "summary": "", "issues": []},   # 모델이 틀리게 적은 시각
        {"turns": "#4~#8", "time": "01:00~02:00", "phase": "", "summary": "", "issues": []},
        {"turns": "알 수 없음", "time": "그대로", "phase": "", "summary": "", "issues": []}]}
    out = prompts.stamp_timeline(minutes, speeches, total_seconds=250)["timeline"]
    assert out[0]["time"] == "00:00~01:30" and out[0]["turns"] == "#1~#3"
    assert out[1]["time"] == "01:30~04:10"            # 앞 구간의 끝에서 시작해 토론의 끝까지
    assert out[2]["time"] == "그대로"                 # 턴 번호를 못 읽으면 건드리지 않는다


def test_cast_asks_for_names_that_show_who_the_person_is():
    system = prompts.CAST_SYSTEM
    assert "사람 이름이 아니라" in system and "웹툰 작가" in system and "10자 이내" in system
    assert "한국 이름을 씁니다" not in system
    assert "사람 이름이 아님" in prompts.cast_prompt("AI 저작권", 3, "auto", [], "")
    assert prompts.DRAFT_SYSTEM.startswith(system)      # 한 줄 설명으로 만드는 초안도 같은 규칙을 따른다


def test_mock_cast_uses_role_names_without_duplicates():
    import asyncio
    from aitalk.providers.mock import MockProvider
    data, _ = asyncio.run(MockProvider(latency=0, seed=1).generate_json(
        system=prompts.CAST_SYSTEM, prompt=prompts.cast_prompt("시험 주제", 8, "auto", [], ""),
        schema=prompts.cast_schema(), model="mock-large", effort="low"))
    names = [p["name"] for p in data["personas"]]
    assert names[0] == "현장 엔지니어" and len(set(names)) == 8
