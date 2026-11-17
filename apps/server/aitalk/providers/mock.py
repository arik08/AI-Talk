"""API를 부르지 않는 프로바이더. 화면 개발과 자동 시험에 쓴다.

P-GPT의 상태 유지 방식(응답 ID, 곁가지, 압축 신호)을 흉내 내서,
집에서도 엔진의 그 처리를 시험할 수 있게 한다.
"""
from __future__ import annotations

import asyncio
import random
import re

from ..prompts import INTENTS, MOODS
from .base import Context, ModelInfo, OnEvent, Provider, Speech, Usage

_OPEN = [
    "안녕하십니까. 오늘은 '{topic}'라는 주제로 이야기를 나눠 보겠습니다. 자리에 {names} 님이 나와 주셨습니다. 먼저 한 분씩 입장을 들어 보겠습니다.",
]
_STATEMENT = [
    "저는 이 문제를 {view} 쪽에서 봅니다. {claim} 이건 현장에서 매일 확인하는 사실이에요. 그래서 오늘 그 얘기를 분명히 하고 싶습니다.",
    "먼저 분명히 해 두죠. {claim} 저는 {view} 입장이고, 듣기 좋은 말보다 실제로 벌어지는 일을 말씀드리겠습니다.",
    "솔직히 이 주제는 생각보다 단순합니다. {claim} 물론 반론이 있겠지만, {view}는 점은 바뀌지 않습니다.",
]
_LINES = {
    "rebut": [
        "{target} 님, 방금 말씀은 듣기엔 그럴듯한데 앞뒤가 안 맞습니다. {claim} 그 부분을 빼고 얘기하시면 곤란하죠.",
        "잠깐만요, {target} 님. 그건 일부 사례를 전체처럼 말씀하시는 겁니다. {claim} 제가 본 현실은 정반대였어요.",
        "{target} 님 말씀대로라면 문제는 벌써 해결됐어야 합니다. 그런데 안 됐죠. {claim}",
    ],
    "add": [
        "{target} 님 말씀에 하나만 보태겠습니다. {claim} 이걸 같이 봐야 그림이 완성됩니다.",
        "그 얘기가 나왔으니 말인데요, {claim} 저는 이 부분이 더 중요하다고 봅니다.",
    ],
    "ask": [
        "{target} 님께 하나 여쭙겠습니다. 그렇게 했을 때 비용은 누가 냅니까? 그 답이 없으면 계획이 아니라 희망이죠.",
        "{target} 님, 그럼 반대 경우에는 어떻게 하실 건가요? 그 경우를 한 번도 말씀 안 하셨습니다.",
    ],
    "agree": [
        "그 점은 {target} 님 말씀이 맞습니다. 저도 거기까지는 같은 생각이에요. 다만 {claim}",
        "{target} 님 말씀에 동의합니다. 사실 그게 핵심이죠. 거기에 더해서, {claim}",
    ],
    "shift": [
        "그런데 우리가 한 가지를 계속 빼놓고 있습니다. 실제로 영향을 받는 사람들 얘기요. {claim}",
        "이 얘기는 충분히 한 것 같으니 방향을 바꿔 보죠. {claim} 저는 여기가 진짜 갈림길이라고 봅니다.",
    ],
}
_MODERATE = [
    "네, 두 분 말씀 잘 들었습니다. 지금 쟁점은 비용과 속도, 이 두 가지로 모이는 것 같습니다. 이번에는 아직 말씀이 적었던 분의 생각을 들어 보죠.",
    "잠시 정리하겠습니다. 같은 지점에서 계속 맞서고 계신데요, 화제를 조금 옮겨서 실행 방법을 얘기해 보겠습니다.",
]
_CLOSING = [
    "오늘 얘기를 들으면서 제 생각도 조금 다듬어졌습니다. 그래도 {claim} 이것만은 끝까지 말씀드리고 싶습니다.",
    "마지막으로 한마디만 하겠습니다. {claim} 서로 다른 얘기를 했지만 결국 같은 걱정에서 출발했다고 생각합니다.",
]
_WRAP = [
    "오늘 토론을 정리하겠습니다. 문제가 있다는 데는 모두 동의하셨고, 해법의 속도와 비용 부담에서 끝까지 생각이 갈렸습니다. 함께해 주신 분들께 감사드립니다.",
]

_FIRST = ["김", "이", "박", "최", "정", "강", "조", "윤", "장", "임"]
_GIVEN = ["서연", "도윤", "하준", "지우", "민서", "예준", "수아", "건우", "채원", "태윤"]
_ROLES = [
    ("현장 엔지니어", "20년 차 설비 엔지니어", "원칙을 중시하고 단호함", "짧게 끊어 말함"),
    ("경제학 교수", "산업 정책을 연구하는 교수", "신중하고 숫자를 좋아함", "'데이터를 보면'을 자주 씀"),
    ("스타트업 대표", "세 번째 창업 중인 대표", "공격적이고 빠름", "비유를 자주 듦"),
    ("시민단체 활동가", "15년 차 활동가", "감정에 호소하고 끈질김", "질문으로 말을 맺음"),
    ("정책 담당 공무원", "중앙부처 과장", "조심스럽고 균형을 찾음", "'현실적으로'를 자주 씀"),
    ("기자", "산업부 취재 기자", "회의적이고 캐묻기를 좋아함", "되묻는 버릇이 있음"),
]


class MockContext(Context):
    def __init__(self, provider: "MockProvider", shared: str, compact_threshold: int) -> None:
        self.p = provider
        self.shared = shared
        self.entries: list[tuple[str, str]] = []
        self.threshold = compact_threshold
        self.head = "resp_0"       # P-GPT의 응답 ID 줄기를 흉내 낸다
        self._seq = 0
        self.rng = provider.rng
        m = re.search(r"# 토론 주제\n(.+)", shared)
        self.topic = (m.group(1) if m else "이 주제").strip()[:40]
        self.people: dict[str, dict] = {}
        for block in re.split(r"\n## ", shared)[1:]:
            block = block.split("\n# ")[0]   # 인물 설명 뒤에 이어지는 다른 절(자료, 연출자 지침)은 뺀다
            name = block.split(" — ")[0].split("\n")[0].strip()
            claims = re.findall(r"^- (.+)$", block, re.MULTILINE)
            view = re.search(r"이 주제에서의 관점: (.+)", block)
            self.people[name] = {"claims": claims, "view": view.group(1) if view else "현실"}

    def _tokens(self) -> int:
        return (len(self.shared) + sum(len(t) for _, t in self.entries)) // 2

    def _text(self, speaker: str, directive: str) -> str:
        info = self.people.get(speaker, {"claims": [], "view": "현실"})
        claim = self.rng.choice(info["claims"]) if info["claims"] else "숫자가 그걸 보여 줍니다."
        if not claim.endswith((".", "다", "요", "죠")):
            claim += "입니다."
        elif not claim.endswith("."):
            claim += "."
        target_m = re.search(r"([가-힣A-Za-z]{2,}) 님", directive)
        target = target_m.group(1) if target_m else "앞서 말씀하신 분"
        others = [n for n in self.people if n not in (speaker, "진행자")]
        if speaker == "진행자":
            if "여세요" in directive:
                pool = _OPEN
            elif "정리" in directive and "마무리" in directive or "끝났습니다" in directive:
                pool = _WRAP
            else:
                pool = _MODERATE
        elif "모두발언" in directive or "첫 발언" in directive:
            pool = _STATEMENT
        elif "마지막 발언" in directive:
            pool = _CLOSING
        else:
            intent = "add"
            for key, word in (("rebut", "반박"), ("ask", "질문"), ("agree", "동의"),
                              ("shift", "화제"), ("add", "보충")):
                if word in directive:
                    intent = key
                    break
            pool = _LINES[intent]
        line = self.rng.choice(pool).format(
            topic=self.topic, names=", ".join(others), view=info["view"][:30].rstrip("."),
            claim=claim, target=target)
        if "끼어" in directive:
            line = "잠깐만요, 그건 아니죠. " + line.split(". ", 1)[-1]
        return line

    async def speak(self, *, speaker: str, directive: str, private: str,
                    model: str, effort: str, on_event: OnEvent) -> Speech:
        self.p.calls.append(("speak", speaker, self.head))
        await asyncio.sleep(self.p.latency)
        text = self._text(speaker, directive)
        for piece in re.findall(r"\S+\s*", text):
            on_event("text", piece)
            await asyncio.sleep(self.p.latency / 12)
        self._seq += 1
        prompt_tokens = self._tokens()
        usage = Usage(input=40, cached=max(prompt_tokens - 120, 0), cache_write=120,
                      output=len(text) // 2)
        self.last_input_tokens = usage.total_input
        return Speech(text=text, usage=usage, model=model,
                      thinking=f"({speaker}의 생각) 상대 주장의 약한 고리를 짚는다.",
                      handle={"id": f"resp_{self._seq}", "prev": self.head, "directive": directive})

    def commit(self, speaker: str, speech: Speech) -> None:
        self.entries.append((speaker, speech.text))
        if speech.handle:
            self.head = speech.handle["id"]

    def amend_last(self, text: str) -> None:
        if self.entries:
            self.entries[-1] = (self.entries[-1][0], text)

    def add_note(self, speaker: str, text: str) -> None:
        self.entries.append((speaker, text))

    async def judge(self, *, question: str, schema: dict, model: str,
                    effort: str) -> tuple[dict, Usage]:
        self.p.calls.append(("judge", "", self.head))
        if {"headline", "agenda"} & set(schema.get("properties", {})):   # 끝난 뒤의 회의록
            return await self.p.generate_json(system="", prompt="", schema=schema, model=model, effort=effort)
        await asyncio.sleep(self.p.latency)
        names_m = re.search(r"참가자: (.+)", question)
        names = [n.strip() for n in names_m.group(1).split(",")] if names_m else []
        last_m = re.search(r"방금 말한 사람: (.+)", question)
        last = last_m.group(1).strip() if last_m else ""
        last_text = self.entries[-1][1] if self.entries else ""
        addressed = next((n for n in names if f"{n} 님" in last_text and n != last), "")
        rows = []
        for n in names:
            urge = self.rng.randint(1, 7)
            if n == addressed:
                urge = self.rng.randint(7, 10)
            if n == last:
                urge = self.rng.randint(0, 3)
            intent = self.rng.choices(INTENTS, weights=[5, 3, 2, 2, 1])[0]
            mood = {"rebut": "heated" if urge >= 8 else "skeptical", "add": "thinking",
                    "ask": "curious", "agree": "agree", "shift": "calm"}[intent]
            if self.rng.random() < 0.2:
                mood = self.rng.choice(MOODS)
            target = last if last and last != n and last != "진행자" else ""
            rows.append({"name": n, "urge": urge, "intent": intent, "target": target, "mood": mood,
                         "length": self.rng.choice(["short", "normal", "normal", "long"])})
        data = {"participants": rows, "addressed": addressed,
                "moderator_needed": self.rng.random() < 0.08, "moderator_reason": "같은 지점에서 맞서고 있습니다."}
        return data, Usage(input=60, cached=self._tokens(), output=80)

    async def maybe_compact(self, model: str) -> bool:
        if self._tokens() <= self.threshold or len(self.entries) <= 8:
            return False
        older = self.entries[:-6]
        self.entries = [("앞부분 요약", f"(앞선 발언 {len(older)}개를 줄인 요약)")] + self.entries[-6:]
        self.compactions += 1
        return True

    def snapshot(self) -> dict:
        return {"head": self.head}


class MockProvider(Provider):
    name = "mock"
    default_model = "mock-large"
    default_effort = "medium"

    def __init__(self, latency: float = 0.5, seed: int | None = None) -> None:
        self.latency = latency
        self.rng = random.Random(seed)
        self.calls: list[tuple] = []

    async def list_models(self) -> list[ModelInfo]:
        efforts = ["low", "medium", "high"]
        return [
            ModelInfo("mock-large", "Mock Large", efforts, "medium",
                      price={"in": 4, "cached": 0.2, "write": 5, "out": 20},
                      note="API를 부르지 않는 시험용"),
            ModelInfo("mock-small", "Mock Small", efforts, "low",
                      price={"in": 0.1, "cached": 0.01, "write": 0.125, "out": 0.5},
                      note="API를 부르지 않는 시험용"),
        ]

    def open_context(self, shared: str, *, search: bool, max_searches: int,
                     compact_threshold: int) -> Context:
        return MockContext(self, shared, compact_threshold)

    async def generate_json(self, *, system: str, prompt: str, schema: dict,
                            model: str, effort: str) -> tuple[dict, Usage]:
        await asyncio.sleep(self.latency)
        props = schema.get("properties", {})
        if "personas" in props:
            m = re.search(r"참가자 (\d+)명", prompt)
            count = int(m.group(1)) if m else 1
            fixed = re.findall(r"^- (.+?) / (.*?) / 전문: (.*?) / 성격: (.*?) / 말투: (.*)$", prompt, re.MULTILINE)
            views = ["지금 당장 바꿔야 한다", "서두르면 더 큰 비용을 치른다", "방향은 맞지만 방법이 틀렸다",
                     "현장을 모르는 논의다", "숫자로 검증된 것만 믿는다", "약자의 관점이 빠졌다"]
            people = []
            names = [a + b for a, b in zip(self.rng.sample(_FIRST, 10), self.rng.sample(_GIVEN, 10))]
            for i in range(count):
                if i < len(fixed):
                    name, title, exp, pers, speech = fixed[i]
                else:
                    role = _ROLES[i % len(_ROLES)]
                    name, title, exp, pers, speech = names[i], role[1], role[0], role[2], role[3]
                view = views[i % len(views)]
                people.append({
                    "name": name, "title": title, "expertise": exp, "personality": pers, "speech": speech,
                    "viewpoint": view,
                    "claims": [f"{view}는 것이 제 경험입니다", "비용을 누가 내는지부터 정해야 합니다",
                               "말보다 실행 계획이 먼저입니다"],
                    "concede": "속도 조절은 받아들일 수 있다", "hidden": "자기 조직의 예산이 걸려 있다",
                })
            return {"personas": people}, Usage(input=400, output=600)
        if "agenda" in props:
            names = re.search(r"참석자: (.+)", prompt)
            people = [n.strip() for n in names.group(1).split(",")] if names else ["참가자"]
            return {
                "title": "시험용 회의록", "overview": "비용과 속도를 두고 논의함. 방향에는 동의했으나 방법에서 갈림.",
                "timeline": [
                    {"turns": "#1~#5", "time": "00:00~02:00", "phase": "모두발언", "summary": "각자 입장을 밝힘.", "issues": ["비용 부담"]},
                    {"turns": "#6~", "time": "02:00~", "phase": "자유토론", "summary": "속도를 두고 맞섬.", "issues": ["시행 속도"]}],
                "agenda": ["전환의 속도", "비용 부담"],
                "discussions": [{"topic": "전환의 속도", "points": [
                    {"name": n, "point": "자신의 입장을 밝히고 상대 주장에 반박함"} for n in people[:4]]}],
                "agreements": ["지금 방식은 오래가기 어렵다는 데 동의함"],
                "open_issues": ["비용을 누가 낼지 정하지 못함"], "follow_ups": [],
                "conclusion": "속도보다 비용 부담 원칙을 먼저 정해야 한다는 의견으로 마무리됨.",
            }, Usage(input=900, output=260)
        if "headline" in props:
            return {
                "headline": "문제에는 동의했지만 해법의 속도에서 갈렸다",
                "consensus": ["지금 방식은 오래가기 어렵다", "비용 부담 원칙이 필요하다"],
                "issues": [{"issue": "얼마나 빨리 바꿀 것인가", "positions": [
                    {"name": "참가자", "position": "당장 시작해야 한다는 쪽과 단계적으로 가야 한다는 쪽이 맞섰다"}]}],
                "takeaway": "속도보다 누가 비용을 내는지가 먼저 정해져야 한다.",
            }, Usage(input=900, output=200)
        return {}, Usage()

    async def generate_text(self, *, system: str, prompt: str, model: str,
                            effort: str) -> tuple[str, Usage]:
        await asyncio.sleep(self.latency)
        return "(시험용 요약) 앞부분에서는 비용과 속도를 두고 의견이 갈렸습니다.", Usage(input=300, output=60)

    async def research(self, *, prompt: str, model: str, effort: str, on_event: OnEvent) -> Speech:
        on_event("search", "시험용 검색어")
        await asyncio.sleep(self.latency * 2)
        found = re.search(r"https?://\S+", prompt)
        url = found.group(0) if found else ""
        return Speech(
            text="요약: 시험용 브리핑입니다. 실제 조사는 Claude나 P-GPT에서 이루어집니다.\n"
                 "쟁점: 비용 부담, 시행 속도, 형평성",
            sources=[{"title": "시험용 출처", "url": url or "https://example.com"}],
            usage=Usage(input=500, output=120, searches=1), model=model)

    def status(self) -> dict:
        return {"ready": True, "message": "시험용 프로바이더입니다. 실제 AI를 부르지 않습니다."}
