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
