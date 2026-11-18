"""P-GPT 문맥 관리 점검. AI-Talk의 프로바이더 코드를 그대로 써서 실제 P-GPT에서 확인한다.

    python scripts/check_pgpt_context.py                 # 무엇을 확인하는지만 보여 준다 (호출하지 않음)
    python scripts/check_pgpt_context.py --execute       # 실제로 P-GPT를 부른다 (회사 OA망, 요금이 든다)
    python scripts/check_pgpt_context.py --execute gpt-6.1-sol

키 값은 출력하지 않는다. 가상 API로 보는 회귀 시험은 apps/server/tests/test_pgpt_context.py에 있다.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "server"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from aitalk.config import settings  # noqa: E402
from aitalk.providers.base import ProviderError  # noqa: E402
from aitalk.providers.pgpt import NOT_CONFIGURED, PgptProvider  # noqa: E402

SCOPE = [
    ("상태 유지", "발언을 store=True + previous_response_id로 잇고, 앞에서 정한 암호를 뒤에서 기억하는지"),
    ("판단 분리", "store=False 곁가지 판단이 줄기에 남지 않는지 (판단에서만 말한 낱말을 다음 발언이 모르는지)"),
    ("웹 검색", "web_search(안 되면 web_search_preview)가 실제로 검색하고 출처 주소를 돌려주는지"),
    ("자동 압축", "압축 기준을 낮게 잡아 context_management 압축이 실제로 일어나는지, 압축 뒤에도 암호를 기억하는지"),
    ("명시적 압축", "/responses/compact를 직접 부를 수 있는지 (계정에 따라 403으로 거절될 수 있다)"),
    ("요약 복구", "서버 문맥 없이 앱의 기록과 요약으로 새 줄기를 세운 뒤에도 암호를 기억하는지"),
]
RESULTS: list[tuple[str, str, str]] = []
SHARED = ("# 토론 규칙\n참가자는 가온과 나래입니다. 지시받은 사람의 말만 한두 문장으로 씁니다.\n"
          "누가 암호를 물으면 앞에서 정한 암호를 그대로 말합니다.")
CODE = "은행나무-4127"
SCHEMA = {"type": "object", "properties": {"word": {"type": "string"}}, "required": ["word"], "additionalProperties": False}


def record(name: str, ok: bool | None, detail: str = "") -> None:
    mark = "됨" if ok else ("확인 필요" if ok is None else "안 됨")
    RESULTS.append((name, mark, detail[:110]))
    print(f"[{mark}] {name} {('- ' + detail[:200]) if detail else ''}")


async def say(ctx, who: str, directive: str, model: str) -> tuple[str, list]:
    events: list = []
    speech = await ctx.speak(speaker=who, directive=directive, private="", model=model, effort="low",
                             on_event=lambda kind, payload: events.append((kind, payload)))
    ctx.commit(who, speech)
    return speech.text, [speech, events]


async def execute(model: str) -> None:
    conf = settings.pgpt
    provider = PgptProvider(**conf)
    if not provider.configured:
        print(NOT_CONFIGURED)
        return
    print(f"모델: {model}\n")

    # 1. 상태 유지
    ctx = provider.open_context(SHARED, search=False, max_searches=0, compact_threshold=200_000)
    try:
        await say(ctx, "가온", f"오늘의 암호는 '{CODE}'입니다. 이 암호를 그대로 한 번 말하세요.", model)
        text, _ = await say(ctx, "나래", "가온이 말한 암호를 그대로 말하세요.", model)
        record("상태 유지", CODE in text, f"\"{text.strip()[:50]}\"")
    except ProviderError as exc:
        record("상태 유지", False, str(exc))
        return summary()

    # 2. 판단 분리
    try:
        data, _ = await ctx.judge(question="'보라색코끼리'라는 낱말을 word에 넣어 JSON으로 답하세요.",
                                  schema=SCHEMA, model=model, effort="low")
        text, _ = await say(ctx, "가온", "지금까지 이 대화에 '보라색코끼리'라는 낱말이 나온 적이 있으면 '있음', 없으면 '없음'이라고만 말하세요.", model)
        record("판단 분리", "없음" in text, f"판단 응답: {data}, 다음 발언: \"{text.strip()[:30]}\"")
    except ProviderError as exc:
        record("판단 분리", False, str(exc))

    # 3. 웹 검색
    try:
        found = provider.open_context(SHARED, search=True, max_searches=2, compact_threshold=200_000)
        text, (speech, events) = await say(found, "가온", "오늘의 주요 뉴스 하나를 웹에서 검색해 한 문장으로 말하세요.", model)
        queries = [payload for kind, payload in events if kind == "search"]
        ok = speech.usage.searches > 0 and bool(speech.sources)
        record(f"웹 검색 ({provider.search_tool})", ok,
               f"검색 {speech.usage.searches}건, 검색어 {len(queries)}개, 출처 {len(speech.sources)}개")
    except ProviderError as exc:
        record("웹 검색", False, str(exc))

    # 4. 자동 압축: 기준을 낮게 잡고 긴 발언을 쌓는다
    try:
        small = provider.open_context(SHARED, search=False, max_searches=0, compact_threshold=2_000)
        await say(small, "가온", f"오늘의 암호는 '{CODE}'입니다. 이 암호를 그대로 한 번 말하세요.", model)
        for i in range(8):
            await say(small, "나래" if i % 2 else "가온", "철강 산업의 역사를 서로 다른 내용으로 열 문장 이상 길게 말하세요.", model)
            if small.compactions:
                break
        text, _ = await say(small, "나래", "가온이 맨 처음에 말한 암호를 그대로 말하세요.", model)
        if not provider.use_compaction:
            record("자동 압축", False, "서버가 context_management를 받지 않아 껐습니다")
        else:
            record("자동 압축", bool(small.compactions) and CODE in text if small.compactions else None,
                   f"압축 {small.compactions}번, 압축 뒤 암호 기억: {'예' if CODE in text else '아니오'}")
    except ProviderError as exc:
        record("자동 압축", False, str(exc))

    # 5. 명시적 압축
    try:
        items = await provider.compact_thread(model, ctx.head or "")
        record("명시적 압축 (/responses/compact)", True, f"항목 {len(items)}개")
    except ProviderError as exc:
        record("명시적 압축 (/responses/compact)", False, str(exc))

    # 6. 요약 복구: 서버 문맥을 버리고 앱의 기록과 요약만으로 잇는다
    try:
        from aitalk.providers import pgpt as module
        module.KEEP_RECENT = 1
        for i in range(3):
            await say(ctx, "나래" if i % 2 else "가온", "방금 한 말을 한 문장으로 다시 말하세요.", model)
        provider.use_explicit_compact = False
        shrunk = await ctx._summarize(model)
        text, _ = await say(ctx, "나래", "이 토론의 암호를 그대로 말하세요.", model)
        record("요약 복구", shrunk and CODE in text, f"요약 {'만듦' if shrunk else '못 만듦'}, 암호 기억: {'예' if CODE in text else '아니오'}")
    except ProviderError as exc:
        record("요약 복구", False, str(exc))
    summary()


def summary() -> None:
    print("\n" + "=" * 78)
    print(f"{'항목':<36}{'결과':<10}비고")
    print("-" * 78)
    for name, mark, detail in RESULTS:
        print(f"{name:<36}{mark:<10}{detail}")
    print("=" * 78)
    print("한 계정·한 모델에서 본 결과입니다. 다른 모델이나 계정에서도 같다고 볼 수는 없습니다.")


def main() -> None:
    args = [a for a in sys.argv[1:] if a != "--execute"]
    model = args[0] if args else "gpt-6-luna"
    if "--execute" not in sys.argv:
        print("P-GPT 문맥 관리 점검 - 확인하는 범위 (지금은 P-GPT를 부르지 않습니다)\n")
        for name, what in SCOPE:
            print(f"- {name}: {what}")
        print("\n실제로 확인하려면 회사 OA망에서:  python scripts/check_pgpt_context.py --execute")
        print("가상 API로 보는 회귀 시험:        python -m pytest apps/server/tests/test_pgpt_context.py -q")
        return
    asyncio.run(execute(model))


if __name__ == "__main__":
    main()
