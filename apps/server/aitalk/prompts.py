"""모델에게 보내는 글. 한곳에 모아 둔다."""
from __future__ import annotations

MOODS = ["calm", "agree", "skeptical", "heated", "curious", "surprised", "amused", "thinking"]
INTENTS = ["rebut", "add", "ask", "agree", "shift"]

LENGTHS = {"short": "1~2문장", "normal": "2~4문장", "long": "4~7문장"}

RULES = """당신은 여러 인물이 등장하는 토론 프로그램의 배우입니다. 아래 인물들이 실제 사람처럼 토론합니다. 호출마다 '지금 할 일'에서 지정한 한 사람의 다음 발언만 만듭니다.

발언 규칙
- 지정된 인물이 입으로 하는 말만 씁니다. 이름표, 따옴표, 괄호 지문(웃음, 한숨 등), 마크다운, 목록을 쓰지 않습니다.
- 방송 토론에서 실제로 말하듯 자연스러운 구어체로 씁니다. 보고서처럼 말하지 않습니다.
- 인물의 성격, 말투, 관점을 끝까지 지킵니다. 인물마다 말하는 방식이 분명히 달라야 합니다.
- 앞사람의 말을 실제로 듣고 반응합니다. 상대가 한 구체적인 표현을 짚어 반박하거나 받아들입니다. 상대를 부를 때는 이름에 '님'을 붙입니다.
- 이미 나온 말을 되풀이하지 않습니다. 새 근거, 사례, 질문으로 토론을 앞으로 밀고 갑니다.
- 설득력 있는 반론을 들으면 일부 물러서거나 입장을 다듬을 수 있습니다. 실제 사람도 그렇게 합니다.
- 지정된 길이를 지킵니다.
- 기록에서 '—'로 끝난 발언은 다음 사람이 끼어들어 끊긴 것입니다.
- 사실을 지어내지 않습니다. 확실하지 않은 수치는 어림이라고 밝히거나 쓰지 않습니다."""

# 분위기. "default"는 여기에 없다: 분위기에 대한 지시를 아무것도 넣지 않고 그대로 진행한다.
TONES = {
    "humorous": "이 토론은 유머러스한 분위기입니다. 참가자들은 재치 있는 농담, 익살스러운 비유, 가벼운 놀림을 섞어 말합니다. "
                "웃음을 주되 각자의 주장과 논리는 분명히 유지합니다. 억지스러운 농담이나 같은 농담의 되풀이는 피하고, "
                "인물마다 자기 성격에 맞는 방식으로 웃깁니다.",
    "serious": "이 토론은 진지한 분위기입니다. 농담이나 가벼운 말은 삼가고, 근거와 논리를 차분하고 무게 있게 다룹니다. "
               "상대의 주장을 정확히 짚고, 감정적인 표현보다 사실과 논증으로 말합니다.",
    "creative": "이 토론은 창의적인 분위기입니다. 뻔한 주장 대신 새로운 관점, 뜻밖의 비유, 사고 실험, '만약 ~라면' 같은 가정을 "
                "적극적으로 꺼냅니다. 상대의 생각을 받아 더 멀리 밀고 가 보기도 합니다. 엉뚱해도 좋지만 주제에서 벗어나지는 않습니다.",
}
TONE_LABEL = {"humorous": "유머러스", "serious": "진지함", "creative": "창의적"}
# 발언 지시 끝에 덧붙이는 한 줄. 앞쪽의 분위기 설명만으로는 인물의 성격 설정에 묻혀 효과가 약했다.
TONE_HINT = {
    "humorous": "분위기는 유머러스합니다. 이번 발언에 이 인물다운 재치 있는 농담이나 익살스러운 비유를 하나는 넣으세요.",
    "serious": "분위기는 진지합니다. 농담이나 가벼운 표현 없이 근거와 논리로만 무게 있게 말하세요.",
    "creative": "분위기는 창의적입니다. 이번 발언에 뜻밖의 비유, 사고 실험, '만약 ~라면' 같은 가정 가운데 하나는 넣어 새로운 각도를 여세요.",
}

MODE_LABEL = {
    "sequential": "처음부터 끝까지 정해진 순서로 돌아가며 말합니다.",
    "free": "정해진 순서 없이, 말하고 싶은 사람이 말합니다.",
    "mixed": "모두발언은 한 명씩 돌아가며 하고, 그 뒤는 자유롭게 토론합니다.",
}


def persona_block(p: dict) -> str:
    lines = [f"## {p['name']} — {p.get('title', '')}".rstrip(" —")]
    for label, key in (("전문 분야", "expertise"), ("성격과 토론 스타일", "personality"),
                       ("말투", "speech"), ("이 주제에서의 관점", "viewpoint")):
        if p.get(key):
            lines.append(f"{label}: {p[key]}")
    claims = [c for c in p.get("claims") or [] if c]
    if claims:
        lines.append("핵심 주장:")
        lines.extend(f"- {c}" for c in claims)
    if p.get("concede"):
        lines.append(f"양보할 수 있는 지점: {p['concede']}")
    return "\n".join(lines)


def shared_context(cfg: dict, briefing: str) -> str:
    parts = [RULES, "", "# 토론 주제", cfg["topic"].strip(), ""]
    concept = (cfg.get("concept") or "").strip()
    if concept:
        parts += ["# 이 토론의 설정과 분위기",
                  "아래는 이 자리가 어떤 자리인지에 대한 설정입니다. 참가자 모두에게 똑같이 적용됩니다. "
                  "말투, 격식, 분위기, 서로를 대하는 태도를 여기에 맞추세요. 인물 각자의 성격은 그 안에서 드러냅니다.",
                  concept, ""]
    tone = TONES.get(cfg.get("tone") or "default")
    if tone:
        parts += ["# 분위기", tone, ""]
    parts += ["# 형식",
             MODE_LABEL.get(cfg.get("mode", "mixed"), ""),
             ("발언 길이는 호출마다 '지금 할 일'에서 정해 줍니다. 짧게 받아칠 때와 길게 풀어 말할 때가 섞입니다."
              if cfg.get("length") == "auto"
              else f"발언 길이의 기본은 {LENGTHS.get(cfg.get('length', 'normal'), LENGTHS['normal'])}입니다."),
             f"모든 발언은 {'영어' if cfg.get('language') == 'en' else '한국어'}로 합니다.",
             "", "# 참가자"]
    for p in cfg["participants"]:
        parts += [persona_block(p), ""]
    if cfg.get("moderator"):
        parts += ["# 진행자", "## 진행자",
                  "중립을 지킵니다. 자기 의견을 내지 않고, 발언권을 정리하고, 논점을 짚고, 화제를 넘깁니다. "
                  "차분하고 또렷한 방송 진행자의 말투입니다.", ""]
    if cfg.get("search") in ("auto", "all"):
        parts += ["# 웹 검색",
                  "웹 검색 도구를 쓸 수 있습니다. 최신 사실이나 구체적인 수치, 사례가 꼭 필요하다고 판단될 때만 "
                  "말하기 전에 조용히 검색합니다. 대부분의 발언은 검색 없이 합니다. "
                  "검색한다는 말이나 검색 과정은 발언에 넣지 않습니다. "
                  "검색으로 확인한 내용은 어디서 본 것인지 밝히며 자연스럽게 말합니다.", ""]
    materials = cfg.get("materials") or []
    if materials or briefing:
        parts.append("# 자료")
        parts.append("참가자 모두가 아래 자료를 읽고 토론에 들어왔습니다. 자료의 내용을 근거로 쓸 수 있습니다.")
        for m in materials:
            parts += [f"## 문서: {m.get('name', '자료')}", m.get("text", ""), ""]
        if briefing:
            parts += ["## 진행자의 사전 조사 브리핑", briefing, ""]
    parts.append(director_section([p["name"] for p in cfg["participants"]]))
    return "\n".join(parts).strip()


def speaker_tail(speaker: str, directive: str, private: str = "") -> str:
    lines = ["━━ 지금 할 일 ━━", f"다음 발언자는 '{speaker}'입니다. {directive}"]
    if private:
        lines.append(f"({speaker}만 아는 속내: {private} 이것을 직접 드러내지는 마세요.)")
    lines.append(f"'{speaker}'가 하는 말만 쓰세요. 이름표, 따옴표, 지문, 마크다운은 쓰지 않습니다.")
    return "\n".join(lines)


def pgpt_directive(speaker: str, directive: str, private: str = "") -> str:
    lines = [f"【다음 발언: {speaker}】 {directive}"]
    if private:
        lines.append(f"({speaker}만 아는 속내: {private} 직접 드러내지는 마세요.)")
    lines.append("이 사람이 하는 말만 쓰세요. 이름표, 따옴표, 지문, 마크다운은 쓰지 않습니다.")
    return "\n".join(lines)


def director_section(names: list[str]) -> str:
    """연출자 호출의 지침. 호출마다 똑같은 글이라 공통 앞부분에 넣어 캐시에 태운다.

    예전에는 이 글(약 700토큰)을 호출마다 꼬리에 붙여 캐시 없이 보냈다.
    """
    return f"""# 연출자 호출
가끔 '지금 할 일'이 발언이 아니라 연출자 호출일 때가 있습니다. 그때는 발언을 만들지 않습니다. 보이지 않는 연출자로서, 방금까지의 흐름을 보고 참가자 한 사람 한 사람이 지금 이 순간 어떤 상태인지 판단해 JSON 하나만 출력합니다.

참가자: {', '.join(names)}

참가자마다 정할 것
- urge: 지금 말하고 싶은 정도, 0~10의 정수. 방금 자기 주장이 공격받았거나 질문을 받았으면 높습니다. 할 말을 이미 다 했거나 화제가 자기 분야에서 멀면 낮습니다. 모두에게 비슷한 점수를 주지 말고 차이를 분명히 하세요. 참을 수 없어 말을 끊고 싶을 정도일 때만 9 이상을 줍니다.
- intent: 말한다면 하려는 것. rebut(반박), add(보충), ask(질문), agree(동의), shift(화제 전환) 가운데 하나.
- target: 누구의 말에 반응하려는가. 참가자 이름 그대로. 없으면 빈 문자열.
- mood: 방금 발언을 들은 지금의 감정. calm(평온), agree(수긍), skeptical(못마땅), heated(격앙), curious(궁금), surprised(놀람), amused(웃음), thinking(고민) 가운데 하나. 인물의 성격과 입장에 맞게, 사람마다 다르게.
- length: 말한다면 얼마나 길게 할 것인가. short(한두 문장으로 받아치기), normal(2~4문장), long(4~7문장으로 풀어서 말하기) 가운데 하나. 빠르게 주고받는 공방이나 짧은 확인·되물음에는 short, 새 논점을 꺼내거나 근거와 사례를 풀어야 할 때는 long. 실제 토론처럼 짧은 호흡과 긴 호흡이 섞이게 하고, 같은 길이만 계속 고르지 마세요.

전체에 대해 정할 것
- addressed: 방금 발언이 특정 참가자에게 질문했거나 그 사람을 지목했다면 그 이름, 아니면 빈 문자열.
- moderator_needed: 같은 주장이 되풀이되거나, 논점이 흐려졌거나, 감정이 지나치게 달아올라 진행자가 정리해야 하면 true.
- moderator_reason: 그 이유를 한 문장으로. 없으면 빈 문자열.

출력 형식: 아래 모양의 JSON 하나만 씁니다. 앞뒤에 다른 글이나 코드 블록 표시를 붙이지 않고, 검색 도구도 쓰지 않습니다. participants에는 참가자 전원을 위의 순서대로 넣습니다.
{{"participants":[{{"name":"이름","urge":5,"intent":"rebut","target":"상대 이름","mood":"calm","length":"short"}}],"addressed":"","moderator_needed":false,"moderator_reason":""}}"""


def director_question(names: list[str], last_speaker: str) -> str:
    """연출자 호출의 꼬리. 지침은 공통 앞부분에 있으므로 여기는 짧다."""
    return f"""━━ 지금 할 일 (연출자 호출) ━━
참가자: {', '.join(names)}
방금 말한 사람: {last_speaker or '없음'}
'연출자 호출' 지침대로 판단해 JSON 하나만 출력하세요."""


def director_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "participants": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "urge": {"type": "integer"},
                        "intent": {"type": "string", "enum": INTENTS},
                        "target": {"type": "string"},
                        "mood": {"type": "string", "enum": MOODS},
                        "length": {"type": "string", "enum": list(LENGTHS)},
                    },
                    "required": ["name", "urge", "intent", "target", "mood", "length"],
                    "additionalProperties": False,
                },
            },
            "addressed": {"type": "string"},
            "moderator_needed": {"type": "boolean"},
            "moderator_reason": {"type": "string"},
        },
        "required": ["participants", "addressed", "moderator_needed", "moderator_reason"],
        "additionalProperties": False,
    }


POLICIES = {
    "balanced": "찬성과 반대가 균형을 이루게 합니다. 인원이 홀수면 한 명은 중간 입장입니다.",
    "stakeholders": "이 주제에 이해관계가 걸린 서로 다른 당사자들로 구성합니다.",
    "experts": "서로 다른 분야의 전문가들로 구성합니다. 같은 문제를 다른 렌즈로 봅니다.",
    "auto": "이 주제에서 가장 흥미로운 토론이 나올 구성을 스스로 정합니다.",
}

CAST_SYSTEM = """당신은 토론 프로그램의 캐스팅 담당입니다. 주제에 맞는 토론 참가자를 만듭니다.

- 모두 가상의 인물입니다. 실존 인물의 이름을 쓰지 않습니다.
- 한국 이름을 씁니다. 나이대, 성별, 배경이 고르게 섞이게 합니다.
- 서로 부딪칠 지점이 분명해야 토론이 됩니다. 관점이 겹치지 않게 합니다.
- 성격과 말투는 사람마다 뚜렷이 달라야 합니다. 공격적인 사람, 신중한 사람, 숫자로 말하는 사람, 사례로 말하는 사람, 감정에 호소하는 사람을 섞습니다.
- 각 항목은 한두 문장으로 짧고 구체적으로 씁니다."""


def cast_prompt(topic: str, count: int, policy: str, fixed: list[dict], materials: str,
                concept: str = "", tone: str = "default") -> str:
    lines = [f"토론 주제:\n{topic.strip()}", ""]
    if concept.strip():
        lines += ["이 토론의 설정과 분위기 (이 자리에 어울리는 사람들로 구성하세요):", concept.strip(), ""]
    if tone in TONE_LABEL:
        lines += [f"토론의 분위기: {TONE_LABEL[tone]}. 이 분위기에서 잘 살아날 인물들로 구성하세요.", ""]
    lines += [f"참가자 {count}명을 만드세요.",
             f"구성 방침: {POLICIES.get(policy, POLICIES['auto'])}"]
    if fixed:
        lines += ["", "다음 인물은 이미 정해졌습니다. 이름, 직함, 전문 분야, 성격, 말투를 그대로 옮겨 적고, "
                      "이 주제에서의 관점·핵심 주장·양보 지점·속내만 새로 정하세요. 목록의 앞쪽에 이 순서대로 넣으세요."]
        for p in fixed:
            lines.append(f"- {p['name']} / {p.get('title', '')} / 전문: {p.get('expertise', '')} / "
                         f"성격: {p.get('personality', '')} / 말투: {p.get('speech', '')}")
    if materials:
        lines += ["", "토론에 쓸 자료의 앞부분입니다. 참가자 구성에 참고하세요.", materials[:6000]]
    lines += ["", "항목 설명",
              "- name: 이름", "- title: 직함과 배경을 담은 한 줄 소개",
              "- expertise: 전문 분야", "- personality: 성격과 토론 스타일",
              "- speech: 말투와 말버릇 (예: 짧게 끊어 말함, '솔직히'를 자주 씀)",
              "- viewpoint: 이 주제에서의 관점", "- claims: 핵심 주장 2~3개",
              "- concede: 양보할 수 있는 지점", "- hidden: 남에게 드러내지 않는 속내나 이해관계"]
    return "\n".join(lines)


def cast_schema() -> dict:
    fields = ["name", "title", "expertise", "personality", "speech", "viewpoint", "concede", "hidden"]
    props: dict = {f: {"type": "string"} for f in fields}
    props["claims"] = {"type": "array", "items": {"type": "string"}}
    return {
        "type": "object",
        "properties": {"personas": {"type": "array", "items": {
            "type": "object", "properties": props,
            "required": fields + ["claims"], "additionalProperties": False}}},
        "required": ["personas"], "additionalProperties": False,
    }


DRAFT_SYSTEM = CAST_SYSTEM + "\n\n지금은 한 줄 설명을 받아 인물 한 명을 만듭니다. 주제가 없으므로 viewpoint, claims, concede, hidden은 이 인물이 평소 어떤 입장을 취하는 사람인지로 채웁니다."

RESEARCH_SYSTEM = """당신은 토론 프로그램의 진행자입니다. 토론에 앞서 자료를 조사해 참가자들에게 나눠 줄 브리핑을 씁니다.
중립적으로, 사실 위주로 씁니다. 자료에 없는 내용을 지어내지 않습니다."""


def research_prompt(topic: str, url: str) -> str:
    return f"""토론 주제: {topic.strip()}

다음 웹 페이지를 읽고 브리핑을 쓰세요. 필요하면 관련 내용을 더 검색하세요.
{url}

브리핑 형식 (마크다운 기호 없이 줄글과 짧은 목록으로):
요약: 3~5문장
쟁점: 토론에서 부딪칠 만한 지점 3~5개, 한 줄씩
주요 사실과 수치: 자료에 실제로 나온 것만"""


SUMMARY_SYSTEM = "당신은 토론을 지켜본 기록자입니다. 토론이 끝난 뒤 요약 카드를 만듭니다. 기록에 실제로 나온 말만 바탕으로 중립적으로 씁니다."


def summary_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "headline": {"type": "string"},
            "consensus": {"type": "array", "items": {"type": "string"}},
            "issues": {"type": "array", "items": {
                "type": "object",
                "properties": {
                    "issue": {"type": "string"},
                    "positions": {"type": "array", "items": {
                        "type": "object",
                        "properties": {"name": {"type": "string"}, "position": {"type": "string"}},
                        "required": ["name", "position"], "additionalProperties": False}},
                },
                "required": ["issue", "positions"], "additionalProperties": False}},
            "takeaway": {"type": "string"},
        },
        "required": ["headline", "consensus", "issues", "takeaway"],
        "additionalProperties": False,
    }


SUMMARY_TAIL = """━━ 지금 할 일 (기록자 호출) ━━
토론이 끝났습니다. 발언을 만들지 않습니다. 토론을 지켜본 기록자로서, 위 기록에 실제로 나온 말만 바탕으로 요약 카드를 JSON 하나로 출력합니다. 앞뒤에 다른 글이나 코드 블록 표시를 붙이지 않습니다.
- headline: 이 토론을 한 줄로
- consensus: 참가자들이 대체로 동의한 점의 목록 (없으면 빈 목록)
- issues: 끝까지 갈린 쟁점 2~4개. 쟁점마다 issue(쟁점)와 positions(각 참가자의 name과 position 한 줄)
- takeaway: 지켜본 사람이 가져갈 한 문장
{"headline":"","consensus":[""],"issues":[{"issue":"","positions":[{"name":"","position":""}]}],"takeaway":""}"""


def summary_prompt(topic: str, transcript: str) -> str:
    return f"""토론 주제: {topic.strip()}

토론 기록:
{transcript}

요약 카드를 만드세요.
- headline: 이 토론을 한 줄로
- consensus: 참가자들이 대체로 동의한 점 (없으면 빈 목록)
- issues: 끝까지 갈린 쟁점 2~4개와, 쟁점마다 각 참가자의 입장 한 줄
- takeaway: 지켜본 사람이 가져갈 한 문장"""


COMPACT_SYSTEM = "당신은 토론 기록 정리 담당입니다. 긴 토론의 앞부분을 뒤에 이어질 토론에 필요한 만큼만 남겨 줄입니다."


def compact_prompt(transcript: str) -> str:
    return f"""다음은 토론 기록의 앞부분입니다. 뒤에 이어질 토론에서 참가자들이 기억해야 할 내용만 남겨 요약하세요.
누가 어떤 주장을 했고, 누가 누구에게 어떻게 반박했고, 무엇이 합의되고 무엇이 남았는지를 사람 이름과 함께 적으세요. 15문장 이내.

{transcript}"""


MINUTES_SYSTEM = """당신은 회의록 작성 담당입니다. 토론 기록을 바탕으로 회의록을 씁니다.

- 기록에 실제로 나온 말만 씁니다. 기록에 없는 내용, 수치, 결론을 덧붙이지 않습니다.
- 발언자의 이름은 기록에 나온 그대로 씁니다.
- 간결한 개조식 문장으로 씁니다. 예) "~라고 주장함", "~하기로 함".
- 후속 조치는 토론에서 누군가 실제로 하겠다고 했거나 하자고 제안한 것만 적습니다. 담당자나 기한이 기록에 없으면 지어내지 않습니다. 없으면 빈 목록으로 둡니다.
- 합의 사항과 미결 사항도 기록에서 확인되는 것만 적습니다."""


def minutes_schema() -> dict:
    strings = {"type": "array", "items": {"type": "string"}}
    return {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "overview": {"type": "string"},
            "agenda": strings,
            "discussions": {"type": "array", "items": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string"},
                    "points": {"type": "array", "items": {
                        "type": "object",
                        "properties": {"name": {"type": "string"}, "point": {"type": "string"}},
                        "required": ["name", "point"], "additionalProperties": False}},
                },
                "required": ["topic", "points"], "additionalProperties": False}},
            "agreements": strings,
            "open_issues": strings,
            "follow_ups": strings,
            "conclusion": {"type": "string"},
        },
        "required": ["title", "overview", "agenda", "discussions", "agreements", "open_issues",
                     "follow_ups", "conclusion"],
        "additionalProperties": False,
    }


def minutes_prompt(topic: str, people: list[str], transcript: str) -> str:
    return f"""주제: {topic.strip()}
참석자: {', '.join(people)}

기록:
{transcript}

위 기록으로 회의록을 쓰세요.
- title: 회의록 제목
- overview: 무엇을 두고 어떤 흐름으로 논의했는지 2~3문장
- agenda: 다룬 안건 목록
- discussions: 안건이나 쟁점마다, 누가 무엇을 말했는지 (points의 name은 발언자 이름)
- agreements: 합의된 사항
- open_issues: 결론이 나지 않은 사항
- follow_ups: 후속 조치 (기록에 실제로 나온 것만)
- conclusion: 맺음말 한두 문장"""
