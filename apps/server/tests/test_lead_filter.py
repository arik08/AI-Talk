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
    # 한글이 나오는 순간 붙들던 것을 내보내고, 그 뒤로는 받는 대로 내보낸다
    assert out == ["", "AI는 도구", "입니다.\n", "Second line in English."]
    assert tail == ""


def test_text_without_any_korean_is_kept_whole():
    text = "Work is not about hours.\nIt is about outcomes."
    out, tail, _ = feed_all([text])
    assert "".join(out) + tail == text
    assert strip_lead(text) == ("", text)
