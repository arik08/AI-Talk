"""쓰이고 있는 JSON을 온 데까지 읽는 것 (회의록과 판정을 쓰는 대로 보여 줄 때 쓴다)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aitalk.providers.base import JsonFeed, partial_json  # noqa: E402

FULL = {"title": '회의 "록"\n첫 줄', "overview": "흐름 \\ 설명", "score": 87,
        "timeline": [{"turns": "#1~#5", "issues": ["비용", "속도"]}, {"turns": "#6~", "issues": []}],
        "agenda": ["안건"], "done": True, "conclusion": "맺음"}


def test_every_prefix_reads_as_a_growing_part_of_the_whole():
    text = "```json\n" + json.dumps(FULL, ensure_ascii=False)
    sizes = []
    for cut in range(len(text) + 1):
        part = partial_json(text[:cut])
        if "{" not in text[:cut]:
            assert part is None
            continue
        assert isinstance(part, dict)
        assert list(part) == list(FULL)[: len(part)]                 # 항목은 앞에서부터 차례로 나타난다
        for key, value in part.items():
            if isinstance(value, str):
                assert FULL[key].startswith(value)                   # 쓰이고 있는 글은 온 데까지 보인다
        sizes.append(len(json.dumps(part, ensure_ascii=False)))
    assert sizes == sorted(sizes)                                    # 나왔던 것이 사라지지 않는다
    assert partial_json(text) == FULL


def test_half_written_keys_and_escapes_are_left_out():
    assert partial_json('{"a": "x", "b') == {"a": "x"}
    assert partial_json('{"a": "x", "b": ') == {"a": "x"}
    assert partial_json('{"a": ["p", "q') == {"a": ["p", "q"]}
    assert partial_json('{"a": "x' + chr(92)) == {"a": "x"}
    assert partial_json('{"a": "x' + chr(92) + 'u00') == {"a": "x"}
    assert partial_json('{"a": 12, "b": tr') == {}                  # 닫힌 값이 아직 없다
    assert partial_json("JSON 없음") is None


def test_feed_pushes_what_is_readable_and_starts_over_on_reset():
    pushed = []
    feed = JsonFeed(pushed.append, every=0)
    for piece in ('{"title": "가', '나", "agenda": ["하나"', "]}"):
        feed("text", piece)
    assert pushed == [{"title": "가"}, {"title": "가나", "agenda": ["하나"]}, {"title": "가나", "agenda": ["하나"]}]
    feed("reset", None)
    feed("search", "무시")
    feed("text", '{"title": "다시"')
    assert pushed[-1] == {"title": "다시"}
