"""발언 앞에 붙어 나오는 계획 메모 걸러 내기."""
from aitalk.engine import LeadFilter, strip_lead

NOTE = "Steve Jobs's opening statement, 2-4 sentences, Korean, colloquial."
TALK = "주 4일이라는 숫자를 법으로 박아 놓고 끝낼 문제가 아닙니다. AI 시대잖아요."


def feed_all(pieces):
    f = LeadFilter()
    out = [f.feed(p) for p in pieces]
    return out, f.finish(), f


def test_english_notes_before_korean_speech_are_held_back():
    text = f"{NOTE}\n\n{TALK}"
    pieces = [text[i:i + 7] for i in range(0, len(text), 7)]
    out, tail, f = feed_all(pieces)
    assert "".join(out) + tail == TALK
    assert f.dropped.strip() == NOTE
    assert strip_lead(text) == (NOTE, TALK)


def test_korean_speech_streams_as_it_comes():
    out, tail, _ = feed_all(["AI", "는 도구", "입니다.\n", "Second line in English."])
    # 첫 문장이 끝나는 순간 붙들던 것을 내보내고, 그 뒤로는 받는 대로 내보낸다
    assert out == ["", "", "AI는 도구입니다.\n", "Second line in English."]   # 첫 문장이 끝나야 메모가 아닌 줄 안다
    assert tail == ""


def test_text_without_any_korean_is_kept_whole():
    text = "Work is not about hours.\nIt is about outcomes."
    out, tail, _ = feed_all([text])
    assert "".join(out) + tail == text
    assert strip_lead(text) == ("", text)


KO_NOTE_TEXT = ('그레타 툰베리의 마지막 발언이므로 검색 없이 바로 작성합니다. 2~4문장, 짧고 단호한 말투로, 앞서 나온 IPCC 45퍼센트 '
                '기준과 정주영 회장의 시험로, 게이츠의 중간 기한 제안을 받아 입장을 정리합니다. 이미 쓴 "이봐, 해 봤어?"나 "말뿐입니다" '
                '같은 말버릇은 반복하지 않습니다.')
KO_TALK = "시험로를 짓는 것 자체를 반대하지는 않겠어요. 다만 정 회장님도 연도를 못 박아야 한다고 하셨죠."


def test_korean_planning_notes_before_the_speech_are_held_back():
    """메모를 한국어로 적어도 걸러 낸다. 화면에 한 글자도 나가지 않는다."""
    text = f"{KO_NOTE_TEXT}\n\n{KO_TALK}"
    pieces = [text[i:i + 5] for i in range(0, len(text), 5)]
    out, tail, f = feed_all(pieces)
    assert "".join(out) + tail == KO_TALK
    assert f.dropped.strip() == KO_NOTE_TEXT
    assert strip_lead(text) == (KO_NOTE_TEXT, KO_TALK)


def test_ordinary_korean_speech_is_not_mistaken_for_a_note():
    for talk in ("게이츠 님, 그 계산이 끝날 때까지 고로는 매년 같은 양을 내뿜고 있어요.",
                 "아니, 그게 아니라요. 제가 물은 건 몇 년이 걸리느냐가 아닙니다.\n\n두 번째 문단입니다.",
                 "본인은 그 말이 영 못 미덥소",
                 "박 회장님의 마지막 발언은 좋은 발언입니다.\n저도 입장을 정리합니다.",
                 "- 첫째, 원가입니다\n- 둘째, 기한입니다"):
        assert strip_lead(talk) == ("", talk), talk


def test_a_speech_that_is_only_a_note_like_line_is_kept_whole():
    """메모처럼 보이는 줄뿐이면 버리지 않는다. 그 글이 곧 발언이다."""
    text = "이번 발언이므로 짧게 작성합니다."
    assert strip_lead(text) == ("", text)
