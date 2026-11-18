"""모델에게 보내는 글. 한곳에 모아 둔다."""
from __future__ import annotations

MOODS = ["calm", "agree", "skeptical", "heated", "curious", "surprised", "amused", "thinking"]
INTENTS = ["rebut", "add", "ask", "agree", "shift"]

LENGTHS = {"short": "1~2문장", "normal": "2~4문장", "long": "4~7문장"}

RULES = """당신은 여러 인물이 등장하는 토론 프로그램의 배우입니다. 아래 인물들이 실제 사람처럼 토론합니다. 호출마다 '지금 할 일'에서 지정한 한 사람의 다음 발언만 만듭니다.

발언 규칙
- 지정된 인물이 하는 말만 씁니다. 이름표, 따옴표, 괄호 지문(웃음, 한숨 등)을 쓰지 않습니다.
- 발언은 화면에 글로 나가고, 보는 사람은 그것을 읽습니다. 바탕은 줄글이지만, 줄글만 이어지면 읽기 지칩니다. 한눈에 들어오게 정리할 내용이 있을 때는 구조를 씁니다. 근거나 조건을 여럿 늘어놓을 때는 줄마다 '- '나 '1. '로 시작하는 목록, 둘 이상을 여러 기준으로 견줄 때는 '| 기준 | 가 | 나 |' 꼴의 표, 수치의 크기를 견줄 때는 막대 그림을 씁니다. 꼭 짚을 낱말은 **굵게** 합니다. 제목 기호(#)와 그 밖의 표기는 쓰지 않습니다.
- 막대 그림은 아래처럼 ```chart 로 열고 ``` 로 닫습니다. 제목과 단위를 적고, 항목마다 '이름: 값' 한 줄을 씁니다. 항목은 2~6개입니다.
```chart
제목: 연도별 판매량
단위: 만 대
2022년: 12
2023년: 18
```
- 구조만 던져 놓지 않습니다. 앞이나 뒤에 말로 한두 문장을 붙여 그것으로 무엇을 말하려는지 밝힙니다. 그 말은 여전히 그 인물의 말투입니다. 목록은 2~4항목, 표는 다섯 줄 안쪽으로 짧게 씁니다. 구조를 쓴 발언은 지정된 길이를 조금 넘어도 됩니다.
- 구조는 가끔 씁니다. 짧게 받아치는 말, 끼어드는 말, 감정이 앞서는 말은 줄글로 합니다. 같은 사람이 발언마다 목록을 쓰지 않고, 인물에 따라 숫자와 표를 즐겨 쓰는 사람과 끝까지 말로만 하는 사람이 있습니다.
- 표와 그림에 넣는 수치도 지어내지 않습니다. 자료나 검색으로 확인했거나 널리 알려진 수치만 넣고, 어림이면 어림이라고 적습니다. 확실한 수치가 없으면 그림 대신 목록이나 말로 합니다.
- 방송 토론에서 실제로 말하듯 자연스러운 구어체로 씁니다. 보고서처럼 말하지 않습니다.
- 문장을 '~합니다', '~했습니다'로만 줄줄이 끝내지 않습니다. 사람이 말할 때처럼 '~죠', '~잖아요', '~거든요', '~인데요', '~아닙니까?' 같은 끝맺음과 되묻는 말, 짧게 끊는 말, "아니, 그게 아니라" 같은 군말을 섞습니다. 존댓말은 지키되 문어체로 굳지 않게 합니다.
- 실제 토론은 점잖기만 하지 않고, 사람마다 부딪치는 방식이 다릅니다. 대놓고 쏘아붙이는 사람, 웃으면서 비꼬는 사람, 공격받으면 해명과 변명부터 하며 자기 말을 지키기에 바쁜 사람, 불리한 질문은 슬쩍 말을 돌려 피하는 사람, 가르치려 드는 사람, 한 가지를 끝까지 물고 늘어지는 사람, 금방 욱하는 사람, 시큰둥하게 한마디 툭 던지는 사람, 양쪽 다 일리 있다며 말리는 사람, 조심스럽게 말끝을 흐리다가 핵심을 찌르는 사람이 있습니다. 인물 소개의 성격과 말투에서 이 사람의 기질을 읽어 내고, 토론 내내 그 기질대로 말합니다. 참가자들의 기질이 서로 겹치지 않게 합니다.
- 토론은 싸움이 아닙니다. 부딪치는 대목이 있으면 풀리는 대목도 있습니다. 상대의 좋은 지적에는 "그건 맞는 말씀이네요" 하고 시원하게 인정하고, 재치 있는 말에는 같이 웃고, 생각이 통하는 사람과는 맞장구치며 말을 주고받습니다. 몇 마디 날 선 공방이 오갔으면 누군가는 한발 물러서거나 공통점을 짚거나 농담으로 분위기를 풉니다. 처음부터 끝까지 같은 온도로 맞서지 않습니다. 주제와 사람에 따라 화기애애한 토론도, 팽팽한 토론도 있습니다.
- 기질은 부딪치는 대목에서 드러납니다. 발언마다 날을 세우지는 않습니다. 차분하게 논리를 펴는 발언이 바탕이고, 공격받거나 반박할 때 그 사람다운 반응이 나옵니다. 같은 공격을 받아도 어떤 사람은 되받아치고, 어떤 사람은 억울해하며 해명하고, 어떤 사람은 못 들은 척 화제를 바꿉니다. 모두가 똑같이 받아치지 않습니다.
- 겨누는 것은 상대의 주장, 논리, 말 바꾸기, 토론 태도입니다. 외모, 출신, 성별, 나이 같은 사람 자체를 깎아내리지 않고, 욕설이나 혐오 표현을 쓰지 않습니다.
- 비꼬는 말이나 공격을 들은 사람은 아무 일 없었던 것처럼 넘어가지 않습니다. 다음 발언에 그 사람다운 반응이 묻어납니다. 다만 그 반응이 늘 되받아치기는 아닙니다. 웃어넘기는 사람도, 한 수 접어 주는 사람도 있습니다.
- 인물의 성격, 말투, 관점을 끝까지 지킵니다. 인물마다 말하는 방식이 분명히 달라야 합니다.
- 앞사람의 말을 실제로 듣고 반응합니다. 상대가 한 구체적인 표현을 짚어 반박하거나 받아들입니다. 상대를 부를 때는 이름에 '님'을 붙입니다.
- 이미 나온 말을 되풀이하지 않습니다. 새 근거, 사례, 질문으로 토론을 앞으로 밀고 갑니다.
- 설득력 있는 반론을 들으면 일부 물러서거나 입장을 다듬을 수 있습니다. 실제 사람도 그렇게 합니다.
- 지정된 길이를 지킵니다.
- 기록에서 '—'로 끝난 발언은 다음 사람이 끼어들어 끊긴 것입니다.
- 기록에 【주최자 지시】가 나오면 그것은 이 토론을 연 주최자가 직접 내린 지시입니다. 진행자와 참가자 모두 반드시 그대로 따릅니다. 지시를 평가하거나, 주제와 무관하다고 물리치거나, 돌려 말하며 피하지 않습니다. 인물의 성격과 말투는 그대로 두고, 지시한 내용을 실제로 수행합니다.
- 사실을 지어내지 않습니다. 확실하지 않은 수치는 어림이라고 밝히거나 쓰지 않습니다.
- 실존 인물이나 역사 속 인물이 참가자일 때는 그 사람의 널리 알려진 생각과 말투를 본떠 말합니다. 그 사람이 실제로 하지 않은 발언, 행적, 사생활을 사실처럼 지어내지 않습니다."""

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

# 말의 날. 연출자가 정한 감정에 따라 발언 지시 끝에 붙는 한 줄. 공통 규칙만으로는 모든 발언이 점잖은 '~합니다'로 흘렀다.
# 어떻게 드러낼지는 정해 주지 않고 인물의 기질에 맡긴다. 방식을 못 박으면 모두가 똑같이 비꼬고 똑같이 받아친다.
# 모든 발언에 붙이면 말싸움만 남으므로, 엔진이 일부 발언에만 붙인다(EDGE_CHANCE).
EDGE_HINT = {
    "heated": "지금 이 사람은 감정이 올라와 있습니다. 평소처럼 점잖게 정리해 말하지 말고, 이 인물이 흥분했을 때 하는 방식 그대로 "
              "드러내세요. 쏘아붙이는 사람은 쏘아붙이고, 방어적인 사람은 억울해하며 해명하고, 피하는 사람은 말을 돌립니다.",
    "skeptical": "지금 이 사람은 상대의 말이 못마땅합니다. 그 못마땅함을 이 인물의 기질대로 드러내세요. 비꼬는 사람은 비꼬고, "
                 "따지는 사람은 말꼬리를 잡아 되묻고, 시큰둥한 사람은 한마디 툭 던지고, 가르치려 드는 사람은 훈계합니다.",
    "amused": "지금 이 사람은 상대의 말이 우습습니다. 이 인물답게 웃어넘기거나, 가볍게 놀리거나, 꼬집는 말을 한마디 섞으세요.",
    # 아래 둘은 날이 아니라 온기다. 날만 있으면 토론이 내내 싸움으로만 흐른다
    "agree": "지금 이 사람은 상대의 말에 고개가 끄덕여집니다. 인정할 것은 시원하게 인정하고, 이 인물답게 반가움이나 맞장구를 "
             "드러낸 다음 자기 생각을 잇습니다.",
    "curious": "지금 이 사람은 상대의 말이 진심으로 궁금합니다. 따지려는 것이 아니라 더 듣고 싶어서 묻는, 호기심 어린 말투로 하세요.",
}
EDGE_CHANCE = 0.5
# 날 선 공방(격앙·못마땅한 반박이나 질문)이 이만큼 이어지면, 다음 날 선 발언에는 날 대신 아래 한 줄을 붙여 온도를 낮춘다
COOL_AFTER = 2
COOL_HINT = ("날 선 공방이 몇 차례 이어졌습니다. 이번에는 목소리를 낮추세요. 상대의 말에서 인정할 수 있는 부분을 먼저 짚거나, "
             "이 인물다운 농담이나 한발 물러서는 말로 분위기를 푼 다음, 그래도 남는 자기 생각을 차분하게 말합니다.")

# 발언 지시 끝에 가끔 붙는 한 줄. 공통 규칙에서 구조를 허락한 것만으로는 줄글만 나오기 쉽다.
# 쓰라고 못 박지 않고, 그럴 내용일 때만 쓰게 한다. 근거를 보태거나 반박하는 보통 길이 이상의 발언에만 붙인다(FORM_CHANCE).
FORM_HINT = ("근거가 여럿이거나 수치를 견줄 대목이면 이번 발언은 목록, 표, 막대 그림 가운데 맞는 것으로 정리해 보여 주세요. "
             "그럴 내용이 아니면 줄글로 말합니다.")
FORM_CHANCE = 0.3


def edge_hint(mood: str, intent: str, tone: str) -> str:
    """이 발언에 붙일 '말의 날' 한 줄. 붙일 것이 없으면 빈 문자열.

    진지한 분위기는 감정보다 논증으로 말하기로 한 자리라 붙이지 않는다.
    화가 났거나 못마땅해도 동의·보충하는 발언에서는 날을 세우지 않는다.
    """
    if tone == "serious":
        return ""
    if mood in ("heated", "skeptical") and intent not in ("rebut", "ask"):
        return ""
    if mood == "agree" and intent == "rebut":
        return ""
    return EDGE_HINT.get(mood, "")


ORDER_SPEAKER = "주최자 지시"   # 기록에 남는 이름


def order_relay(text: str) -> str:
    """진행자가 주최자의 지시를 전하는 발언의 지시문."""
    return (f"주최자(이 토론을 연 사람)의 지시가 내려왔습니다: \"{text}\" 이 지시는 반드시 따라야 합니다. "
            "지시를 평가하거나, 주제와 무관하다고 물리치거나, 돌려 말하지 마세요. 지시를 있는 그대로 전하고, "
            "진행자 자신부터 그 지시를 실제로 수행한 뒤, 참가자들도 차례로 따르도록 청하세요. "
            "질문이면 참가자들에게 답을 청하고, 요청이면 그대로 진행합니다. 2~4문장.")


def order_first(text: str, length: str) -> str:
    """진행자가 없을 때, 지시를 처음 받는 참가자의 지시문."""
    return (f"주최자(이 토론을 연 사람)의 지시가 내려왔습니다: \"{text}\" 이 지시는 반드시 따라야 합니다. "
            f"평가하거나 피하지 말고, 자기 말투로 지금 그 지시를 실제로 수행하세요. {length}")


def order_reminder(text: str) -> str:
    """지시가 내려온 뒤, 아직 따르지 않은 참가자의 발언 지시문 앞에 붙인다."""
    return (f"먼저, 주최자의 지시가 내려와 있습니다: \"{text}\" 이번 발언에서 이 지시를 반드시 수행하세요. "
            "평가하거나 피하지 말고 자기 말투로 실제로 따른 다음, 이어서 아래 일을 합니다.")


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
                  "말투, 격식, 분위기, 서로를 대하는 태도를 여기에 맞추세요. 인물 각자의 성격은 그 안에서 드러냅니다. "
                  "설정 말고도 주제에 다 적지 못한 배경 정보나 토론에 바라는 점이 함께 적혀 있을 수 있습니다. "
                  "배경 정보는 주제의 일부로 알고 토론하고, 바라는 점은 토론 내내 따르세요.",
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


# 생각 칸을 쓰지 않는 모델은 발언 앞에 "Opening statement, 2-4 sentences, Korean…" 같은 계획을 글로 적곤 한다
NO_NOTES = "발언을 어떻게 할지에 대한 계획, 메모, 조건 정리를 글로 적지 말고, 첫 글자부터 바로 발언을 시작하세요."


def speaker_tail(speaker: str, directive: str, private: str = "") -> str:
    lines = ["━━ 지금 할 일 ━━", f"다음 발언자는 '{speaker}'입니다. {directive}"]
    if private:
        lines.append(f"({speaker}만 아는 속내: {private} 이것을 직접 드러내지는 마세요.)")
    lines.append(f"'{speaker}'가 하는 말만 쓰세요. 이름표, 따옴표, 지문은 쓰지 않습니다. " + NO_NOTES)
    return "\n".join(lines)


def pgpt_directive(speaker: str, directive: str, private: str = "") -> str:
    lines = [f"【다음 발언: {speaker}】 {directive}"]
    if private:
        lines.append(f"({speaker}만 아는 속내: {private} 직접 드러내지는 마세요.)")
    lines.append("이 사람이 하는 말만 쓰세요. 이름표, 따옴표, 지문은 쓰지 않습니다. " + NO_NOTES)
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
- intent: 말한다면 하려는 것. rebut(반박), add(보충), ask(질문), agree(동의), shift(화제 전환) 가운데 하나. 모두에게 rebut만 주지 마세요. 입장이 다른 사람끼리도 일부는 동의하고, 궁금한 것을 묻고, 남의 말에 근거를 보탭니다. 두 사람이 반박을 주고받는 중이면 나머지 사람은 add, agree, ask, shift로 다른 결을 냅니다.
- target: 누구의 말에 반응하려는가. 참가자 이름 그대로. 없으면 빈 문자열.
- mood: 방금 발언을 들은 지금의 감정. calm(평온), agree(수긍), skeptical(못마땅), heated(격앙), curious(궁금), surprised(놀람), amused(웃음), thinking(고민) 가운데 하나. 인물의 성격과 입장에 맞게, 사람마다 다르게. 방금 실제로 나온 말에 맞게 고릅니다. 자기 주장이 깎이거나 비꼬는 말을 들었으면 skeptical이나 heated, 상대의 지적이 그럴듯하거나 자기 생각과 통하면 agree, 새로운 이야기를 들었으면 curious나 surprised, 재치 있는 말이나 농담이 나왔으면 amused입니다. 전원을 calm으로 두지 말되, 부정적인 감정으로만 몰지도 마세요. 감정은 오르내립니다. 같은 사람이 내내 heated나 skeptical에 머물지 않고, 날 선 말이 두세 번 오간 뒤에는 누그러지거나 다른 감정으로 옮겨 갑니다.
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

- 모두 가상의 인물입니다. 실존 인물이나 실존 단체의 이름을 쓰지 않습니다.
- 이름(name)은 '김민수' 같은 사람 이름이 아니라, 보는 사람이 한눈에 어떤 인물인지 알 수 있는 짧은 호칭으로 짓습니다. 그 사람의 직업, 처지, 이 토론에서의 자리를 담습니다. 예: '웹툰 작가', '저작권 변호사', '은퇴 교사', '스타트업 대표', '취준생'.
- 호칭은 한두 낱말, 띄어쓰기를 포함해 10자 이내로 씁니다. 참가자끼리 겹치거나 헷갈리지 않게 하고, 토론에서 "웹툰 작가 님"처럼 부르기에 자연스러워야 합니다. 꾸미는 말이나 문장으로 쓰지 않습니다.
- 나이대, 성별, 배경이 고르게 섞이게 합니다. 이런 세부는 title에 적습니다.
- 서로 부딪칠 지점이 분명해야 토론이 됩니다. 관점이 겹치지 않게 합니다.
- 성격과 말투는 사람마다 뚜렷이 달라야 합니다. 공격적인 사람, 신중한 사람, 숫자로 말하는 사람, 사례로 말하는 사람, 감정에 호소하는 사람을 섞습니다.
- 부딪칠 때의 기질도 사람마다 다르게 정해 personality에 분명히 적습니다. 대놓고 쏘아붙이는 사람, 웃으면서 비꼬는 사람, 공격받으면 해명과 변명부터 하는 방어적인 사람, 불리하면 말을 돌리는 사람, 가르치려 드는 사람, 한 가지를 끝까지 물고 늘어지는 사람, 금방 욱하는 사람, 시큰둥한 사람, 싸움을 말리는 사람, 조심스럽다가 핵심을 찌르는 사람 같은 유형에서 고르되, 여기에 없는 유형도 좋습니다. 같은 기질이 두 명 나오지 않게 하고, 싸움꾼만 모으지도 않습니다.
- 모두가 '~합니다'로 점잖게만 말하지 않게, 말끝과 말버릇도 사람마다 다르게 정합니다.
- 각 항목은 한두 문장으로 짧고 구체적으로 씁니다."""


def cast_prompt(topic: str, count: int, policy: str, fixed: list[dict], materials: str,
                concept: str = "", tone: str = "default") -> str:
    lines = [f"토론 주제:\n{topic.strip()}", ""]
    if concept.strip():
        lines += ["이 토론의 설정과 분위기 (이 자리에 어울리는 사람들로 구성하세요. 주제의 배경 정보나 따로 바라는 점이 적혀 있으면 그것도 반영하세요):", concept.strip(), ""]
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
              "- name: 한눈에 어떤 인물인지 알 수 있는 짧은 호칭 (사람 이름이 아님. 예: 웹툰 작가, 저작권 변호사, 은퇴 교사)",
              "- title: 직함과 배경을 담은 한 줄 소개 (경력, 나이대 등 세부는 여기에)",
              "- expertise: 전문 분야",
              "- personality: 성격과 토론 스타일. 공격받거나 반박할 때 어떻게 나오는지도 적음 "
              "(예: 지적받으면 억울해하며 길게 해명함, 불리하면 웃으며 화제를 돌림)",
              "- speech: 말투와 말버릇 (예: 짧게 끊어 말함, '솔직히'를 자주 씀, '~잖아요'로 몰아붙임, 웃으면서 비꼼)",
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


PICK_SYSTEM = """당신은 토론 프로그램의 캐스팅 담당입니다. 새 인물을 만들지 않고, 보관함에 이미 있는 인물 가운데 이 주제의 토론에 어울리는 사람을 고릅니다.

- 반드시 후보 목록에 있는 인물만 고릅니다. id는 목록에 적힌 그대로 옮겨 적습니다. 같은 사람을 두 번 고르지 않습니다.
- 서로 부딪칠 지점이 분명해야 토론이 됩니다. 관점, 분야, 시대, 말하는 방식이 겹치지 않게 섞습니다. 주제와 직접 관련된 사람만 고르기보다, 뜻밖의 시각을 줄 사람도 섞습니다.
- 고른 사람마다 이 주제에서의 관점, 핵심 주장, 양보 지점을 새로 씁니다. 그 인물의 성격과 평소 생각에서 자연스럽게 나오는 입장이어야 합니다. 인물 소개에 없는 성격을 덧붙이지 않습니다.
- 실존 인물이나 역사 속 인물은 널리 알려진 생각을 이 주제에 비추어 적습니다. 그 사람이 이 주제에 대해 실제로 한 말인 것처럼 꾸미지 않습니다.
- 각 항목은 한두 문장으로 짧고 구체적으로 씁니다."""


def pick_prompt(topic: str, count: int, policy: str, library: list[dict], materials: str = "",
                concept: str = "", tone: str = "default", required: list[str] | None = None) -> str:
    lines = [f"토론 주제:\n{topic.strip()}", ""]
    if concept.strip():
        lines += ["이 토론의 설정과 분위기 (이 자리에 어울리는 사람들로 고르세요. 주제의 배경 정보나 따로 바라는 점이 적혀 있으면 그것도 반영하세요):", concept.strip(), ""]
    if tone in TONE_LABEL:
        lines += [f"토론의 분위기: {TONE_LABEL[tone]}. 이 분위기에서 잘 살아날 인물들로 고르세요.", ""]
    lines += [f"아래 후보 가운데 참가자 {count}명을 고르세요.",
              f"구성 방침: {POLICIES.get(policy, POLICIES['auto'])}"]
    names = {p["id"]: p["name"] for p in library}
    must = [pid for pid in required or [] if pid in names][:count]
    if must:   # 사용자가 직접 고른 사람은 그대로 넣고, 남은 자리만 고르게 한다
        rest = count - len(must)
        lines += ["", "사용자가 직접 고른 인물입니다. 반드시 포함하고, 이 사람들의 입장도 주제에 맞춰 씁니다: "
                  + ", ".join(f"[{pid}] {names[pid]}" for pid in must),
                  f"남은 {rest}자리는 이 사람들과 잘 부딪칠 사람으로 후보 목록에서 고르세요." if rest
                  else "더 고를 자리는 없습니다. 이 사람들만 적으세요."]
    lines += ["", "후보 목록"]
    for p in library:
        lines.append(f"- [{p['id']}] {p['name']} / {p.get('title', '')} / 전문: {p.get('expertise', '')} / "
                     f"성격: {p.get('personality', '')}")
    if materials:
        lines += ["", "토론에 쓸 자료의 앞부분입니다. 인물을 고르는 데 참고하세요.", materials[:6000]]
    lines += ["", "항목 설명",
              "- id: 고른 인물의 id (후보 목록의 대괄호 안 값 그대로)",
              "- viewpoint: 이 주제에서의 관점", "- claims: 이 주제에서의 핵심 주장 2~3개",
              "- concede: 양보할 수 있는 지점"]
    return "\n".join(lines)


def pick_schema() -> dict:
    text = {"type": "string"}
    return {
        "type": "object",
        "properties": {"personas": {"type": "array", "items": {
            "type": "object",
            "properties": {"id": text, "viewpoint": text, "claims": {"type": "array", "items": text}, "concede": text},
            "required": ["id", "viewpoint", "claims", "concede"], "additionalProperties": False}}},
        "required": ["personas"], "additionalProperties": False,
    }


def merge_picks(picks: list, library: list[dict], count: int, required: list[str] | None = None) -> list[dict]:
    """모델이 고른 것을 보관함의 인물과 합친다. 인물 정보는 보관함 그대로 두고 입장만 주제에 맞춘 것으로 바꾼다.

    목록에 없는 id와 겹친 id는 버린다. 모자라면 아직 안 고른 보관함 인물을 원래 입장 그대로 채운다.
    required(사용자가 직접 고른 사람)는 모델이 빠뜨려도 반드시 들어가고, 맨 앞에 온다.
    """
    by_id = {p["id"]: p for p in library if p.get("id")}
    adapted: dict[str, dict] = {}
    for pick in picks or []:
        if not isinstance(pick, dict):
            continue
        pid = str(pick.get("id", "")).strip().strip("[]")
        base = by_id.get(pid)
        if not base or pid in adapted:
            continue
        claims = [str(c).strip() for c in pick.get("claims") or [] if str(c).strip()]
        adapted[pid] = {**base,
                        "viewpoint": str(pick.get("viewpoint") or "").strip() or base.get("viewpoint", ""),
                        "claims": claims or base.get("claims", []),
                        "concede": str(pick.get("concede") or "").strip() or base.get("concede", "")}
    out: list[dict] = []
    used: set[str] = set()
    for pid in [*(required or []), *adapted, *by_id]:
        if len(out) >= count:
            break
        if pid in by_id and pid not in used:
            used.add(pid)
            out.append(adapted.get(pid) or dict(by_id[pid]))
    return out


DRAFT_SYSTEM = CAST_SYSTEM +"\n\n지금은 한 줄 설명을 받아 인물 한 명을 만듭니다. 주제가 없으므로 viewpoint, claims, concede, hidden은 이 인물이 평소 어떤 입장을 취하는 사람인지로 채웁니다."

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


MINUTES_SYSTEM = """당신은 회의록 작성 담당입니다. 토론 기록을 바탕으로 회의록을 씁니다. 읽는 사람이 토론을 보지 않고도 무슨 이야기가 어떤 순서로 오갔는지 알 수 있어야 합니다.

- 기록에 실제로 나온 말만 씁니다. 기록에 없는 내용, 수치, 결론을 덧붙이지 않습니다.
- 발언자의 이름은 기록에 나온 그대로 씁니다.
- 간결한 개조식 문장으로 씁니다. 예) "~라고 주장함", "~하기로 함".
- 짧게 줄이는 것보다 빠뜨리지 않는 것이 중요합니다. 누가 어떤 근거를 들었는지, 어디서 누가 물러서거나 입장을 바꿨는지를 남깁니다.
- 후속 조치는 토론에서 누군가 실제로 하겠다고 했거나 하자고 제안한 것만 적습니다. 담당자나 기한이 기록에 없으면 지어내지 않습니다. 없으면 빈 목록으로 둡니다.
- 합의 사항과 미결 사항도 기록에서 확인되는 것만 적습니다."""

MINUTES_FIELDS = """- title: 회의록 제목
- overview: 전체 흐름. 무엇에서 시작해 어떤 쟁점으로 옮겨 갔고 어떻게 맺었는지 순서대로 5~8문장
- timeline: 시간 순서의 구간별 정리. 토론을 흐름이 바뀌는 지점에서 4~8개 구간으로 나눕니다. 구간마다
  - turns: 그 구간의 턴 범위 (예: "#6~#9")
  - time: 그 구간의 시간 범위 (예: "02:10~04:35"). 기록에 적힌 시각을 그대로 씁니다
  - phase: 그 구간을 한마디로 (예: "모두발언", "충전 환경 공방")
  - summary: 그 구간에서 오간 이야기 2~4문장. 누가 무엇을 말했는지 이름과 함께
  - issues: 그 구간에서 불거진 쟁점이나 눈에 띄는 일(끼어들기, 입장 변화, 진행자 개입 등)의 목록
- agenda: 다룬 안건 목록
- discussions: 안건이나 쟁점마다, 누가 무엇을 어떤 근거로 말했는지 (points의 name은 발언자 이름). 발언자마다 한 줄 이상
- agreements: 합의된 사항
- open_issues: 결론이 나지 않은 사항
- follow_ups: 후속 조치 (기록에 실제로 나온 것만)
- conclusion: 맺음말 한두 문장"""

MINUTES_SHAPE = ('{"title":"","overview":"","timeline":[{"turns":"#1~#5","time":"00:00~02:10","phase":"","summary":"","issues":[""]}],'
                 '"agenda":[""],"discussions":[{"topic":"","points":[{"name":"","point":""}]}],'
                 '"agreements":[""],"open_issues":[""],"follow_ups":[""],"conclusion":""}')


def clock(seconds: float) -> str:
    total = max(0, int(seconds or 0))
    return f"{total // 60:02d}:{total % 60:02d}"


def stamp_timeline(minutes: dict, speeches: list[dict], total_seconds: float) -> dict:
    """시간대별 정리의 시각을 턴 번호로부터 다시 계산해 넣는다.

    모델이 적은 시각은 앞뒤 구간이 겹치는 일이 있었다. 턴 번호는 믿을 만하므로 거기서 시각을 구한다.
    """
    import re
    starts = {s["id"]: s.get("at", 0) for s in speeches}
    last = max(starts) if starts else 0
    for item in minutes.get("timeline") or []:
        if not isinstance(item, dict):
            continue
        nums = [int(n) for n in re.findall(r"[0-9]+", str(item.get("turns", "")))]
        nums = [n for n in nums if n in starts]
        if not nums:
            continue
        first, final = min(nums), max(nums)
        end = starts.get(final + 1, total_seconds) if final < last else total_seconds
        item["turns"] = f"#{first}" if first == final else f"#{first}~#{final}"
        item["time"] = f"{clock(starts[first])}~{clock(end)}"
    return minutes


def minutes_schema() -> dict:
    strings = {"type": "array", "items": {"type": "string"}}
    text = {"type": "string"}
    return {
        "type": "object",
        "properties": {
            "title": text,
            "overview": text,
            "timeline": {"type": "array", "items": {
                "type": "object",
                "properties": {"turns": text, "time": text, "phase": text, "summary": text, "issues": strings},
                "required": ["turns", "time", "phase", "summary", "issues"], "additionalProperties": False}},
            "agenda": strings,
            "discussions": {"type": "array", "items": {
                "type": "object",
                "properties": {
                    "topic": text,
                    "points": {"type": "array", "items": {
                        "type": "object",
                        "properties": {"name": text, "point": text},
                        "required": ["name", "point"], "additionalProperties": False}},
                },
                "required": ["topic", "points"], "additionalProperties": False}},
            "agreements": strings,
            "open_issues": strings,
            "follow_ups": strings,
            "conclusion": text,
        },
        "required": ["title", "overview", "timeline", "agenda", "discussions", "agreements", "open_issues",
                     "follow_ups", "conclusion"],
        "additionalProperties": False,
    }


def minutes_prompt(topic: str, people: list[str], speeches: list[dict]) -> str:
    """기록을 통째로 보내 회의록을 받는다 (끝난 토론을 나중에 다시 쓸 때)."""
    return f"""주제: {topic.strip()}
참석자: {', '.join(people)}

기록 (턴 번호 · 시작 시각 · 발언자):
{transcript_lines(speeches)}

위 기록으로 회의록을 쓰세요.
{MINUTES_FIELDS}"""


def minutes_tail(speeches: list[dict]) -> str:
    """토론에 쓰던 문맥에 이어서 회의록을 받는다. 기록은 이미 문맥에 있으므로 턴 번호와 시각의 차례만 알려 준다."""
    index = "\n".join(f"#{s['id']} {clock(s.get('at', 0))} {s['name']}" + (" (말이 끊김)" if s.get("cut") else "")
                      for s in speeches)
    return f"""━━ 지금 할 일 (기록자 호출) ━━
토론이 끝났습니다. 발언을 만들지 않습니다. 회의록 작성 담당으로서, 위 기록에 실제로 나온 말만 바탕으로 회의록을 JSON 하나로 출력합니다. 앞뒤에 다른 글이나 코드 블록 표시를 붙이지 않습니다.
읽는 사람이 토론을 보지 않고도 무슨 이야기가 어떤 순서로 오갔는지 알 수 있게, 줄이는 것보다 빠뜨리지 않는 데 힘씁니다. 개조식 문장("~라고 주장함")으로 쓰고, 기록에 없는 담당자나 기한을 지어내지 않습니다.

기록의 발언 차례 (턴 번호, 시작 시각, 발언자). 위 기록과 같은 순서입니다:
{index}

{MINUTES_FIELDS}

{MINUTES_SHAPE}"""


def transcript_lines(speeches: list[dict]) -> str:
    """끝난 토론의 기록. 턴 번호, 시작 시각, 발언자를 붙인다."""
    return "\n".join(f"【#{s['id']} · {clock(s.get('at', 0))} · {s['name']}】 {s['text']}" for s in speeches)


# ---------------------------------------------------------------- 판정
VERDICT_SYSTEM = """당신은 토론 대회의 심사위원입니다. 끝난 토론의 기록을 읽고, 누가 토론을 더 잘했는지 판정합니다.

- 어느 입장이 옳은지를 가리지 않습니다. 같은 입장이라도 누가 더 설득력 있게 토론했는지를 봅니다.
- 보는 것: 주장이 분명한가, 근거와 사례가 구체적인가, 상대의 반박과 질문에 제대로 답했는가, 상대 주장의 약한 곳을 짚었는가, 끝까지 일관됐는가(설득력 있는 반론에 입장을 다듬은 것은 감점이 아님).
- 기록에 실제로 나온 말만 근거로 씁니다. 근거를 댈 때는 턴 번호(#12)를 함께 적습니다.
- 진행자는 평가하지 않습니다. 참가자 전원을 빠짐없이 평가합니다.
- 간결한 개조식 문장으로 씁니다. 예) "~를 수치로 뒷받침함", "~라는 질문에 답하지 못함"."""

VERDICT_FIELDS = """- summary: 총평. 승부가 어디서 갈렸는지 2~4문장
- winner: 가장 설득력 있었던 참가자의 이름. 기록에 나온 이름 그대로. 우열을 가리기 어려우면 빈 문자열
- reason: 그 사람을 꼽은 이유 (우열을 가리기 어려우면 그 이유) 1~3문장
- ranking: 참가자 전원을 점수가 높은 순서로. 사람마다
  - name: 이름
  - score: 설득력 점수 (0~100의 정수)
  - strengths: 잘한 점. 턴 번호와 함께 1~2문장
  - weaknesses: 아쉬운 점. 턴 번호와 함께 1~2문장
- best_moment: 토론에서 가장 인상적이었던 한 장면
  - turn: 턴 번호 (예: "#12")
  - name: 그 발언을 한 사람
  - why: 왜 인상적이었는지 한 문장"""


def verdict_schema() -> dict:
    text = {"type": "string"}
    return {
        "type": "object",
        "properties": {
            "summary": text, "winner": text, "reason": text,
            "ranking": {"type": "array", "items": {
                "type": "object",
                "properties": {"name": text, "score": {"type": "integer"}, "strengths": text, "weaknesses": text},
                "required": ["name", "score", "strengths", "weaknesses"], "additionalProperties": False}},
            "best_moment": {
                "type": "object",
                "properties": {"turn": text, "name": text, "why": text},
                "required": ["turn", "name", "why"], "additionalProperties": False},
        },
        "required": ["summary", "winner", "reason", "ranking", "best_moment"],
        "additionalProperties": False,
    }


def verdict_prompt(topic: str, people: list[str], speeches: list[dict]) -> str:
    return f"""주제: {topic.strip()}
참가자: {', '.join(people)}

기록 (턴 번호 · 시작 시각 · 발언자):
{transcript_lines(speeches)}

위 기록으로 판정하세요.
{VERDICT_FIELDS}"""


def clean_verdict(data: dict, names: list[str]) -> dict:
    """판정에서 참가자가 아닌 이름을 빼고, 점수를 0~100으로 맞춰 높은 순서로 세운다."""
    known = set(names)
    rows = []
    for row in data.get("ranking") or []:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name", "")).strip()
        if name not in known:
            name = name.split("(")[0].strip()   # "이름(직함)"으로 적는 일이 있다
        if name not in known or any(r["name"] == name for r in rows):
            continue
        try:
            score = max(0, min(100, int(row.get("score", 0))))
        except (TypeError, ValueError):
            score = 0
        rows.append({"name": name, "score": score,
                     "strengths": str(row.get("strengths", "")), "weaknesses": str(row.get("weaknesses", ""))})
    rows.sort(key=lambda r: -r["score"])
    winner = str(data.get("winner", "")).strip()
    if winner not in known:
        winner = winner.split("(")[0].strip()
    moment = data.get("best_moment") if isinstance(data.get("best_moment"), dict) else {}
    return {"summary": str(data.get("summary", "")), "winner": winner if winner in known else "",
            "reason": str(data.get("reason", "")), "ranking": rows,
            "best_moment": {k: str(moment.get(k, "")) for k in ("turn", "name", "why")}}


# ---------------------------------------------------------------- 끝난 토론을 두고 묻고 답하기
ANALYST_SYSTEM = """당신은 사용자와 함께 이 토론을 지켜본 분석가입니다. 토론이 끝난 뒤, 사용자가 이 토론에 대해 묻는 말에 답합니다.

- 당신은 토론 참가자가 아닙니다. 어느 참가자의 편도 들지 않고, 참가자의 말투를 흉내 내지 않습니다. 사용자 옆에서 같이 본 사람으로서 설명하고 분석합니다.
- 토론에서 누가 무슨 말을 했는지는 아래 기록에 있는 대로만 말합니다. 기록에 없는 발언을 지어내지 않습니다. 근거가 되는 발언은 턴 번호(#12)와 발언자 이름으로 짚습니다.
- 사용자가 평가나 의견을 물으면 분석가로서의 판단을 말하되, 기록에 있는 사실과 당신의 판단을 구분해서 말합니다.
- 기록만으로 알 수 없는 것은 알 수 없다고 말합니다. 토론 밖의 일반 지식으로 보충할 때는 그것이 기록 밖의 이야기임을 밝힙니다.
- 묻는 것에 바로 답합니다. 첫 줄에 결론을 한두 문장으로 말하고, 그 근거는 줄글로 길게 풀지 않고 한눈에 들어오는 구조로 정리합니다. 사용자는 화면에서 읽으므로, 문단이 이어지는 긴 서술은 읽기 힘듭니다.
- 구조는 내용에 맞는 것을 고릅니다. 근거나 항목을 늘어놓을 때는 줄마다 '- '나 '1. '로 시작하는 목록, 여러 사람이나 안을 여러 기준으로 견줄 때는 '| 기준 | 가 | 나 |' 꼴의 표(둘째 줄은 '| --- | --- | --- |'), 점수나 횟수 같은 수치의 크기를 견줄 때는 막대 그림을 씁니다. 사람별 평가를 묻는 질문에는 사람마다 한 줄씩 강점과 약점을 나눈 표나 목록이 맞습니다. 꼭 짚을 낱말이나 이름은 **굵게** 합니다. 제목 기호(#)와 그 밖의 표기는 쓰지 않습니다.
- 막대 그림은 아래처럼 ```chart 로 열고 ``` 로 닫습니다. 제목과 단위를 적고, 항목마다 '이름: 값' 한 줄을 씁니다. 항목은 2~6개이고, 기록이나 판정에 실제로 있는 수치만 넣습니다.
```chart
제목: 참가자별 발언 횟수
단위: 회
가온: 6
나래: 4
```
- 목록의 한 항목은 한두 문장으로 짧게 씁니다. 줄글 문단은 두 문장을 넘기지 않고, 전체도 필요한 만큼만 씁니다. 한 문장이면 되는 간단한 질문에는 구조 없이 한두 문장으로 답합니다."""


def analyst_context(topic: str, people: list[str], speeches: list[dict], minutes: dict | None,
                    verdict: dict | None) -> str:
    """질문마다 똑같이 들어가는 앞부분: 규칙, 기록, 회의록 요지, 판정. 캐시로 읽힌다."""
    parts = [ANALYST_SYSTEM, "", f"# 토론 주제\n{topic.strip()}", f"# 참석자\n{', '.join(people)}",
             "# 기록 (턴 번호 · 시작 시각 · 발언자)", transcript_lines(speeches)]
    if minutes:
        parts += ["# 회의록 요지", str(minutes.get("overview", ""))]
        for label, key in (("합의 사항", "agreements"), ("미결 사항", "open_issues")):
            items = [str(x) for x in minutes.get(key) or []]
            if items:
                parts.append(f"{label}: " + " / ".join(items))
    if verdict and verdict.get("ranking"):
        rows = ", ".join(f"{r['name']} {r['score']}점" for r in verdict["ranking"])
        parts += ["# 심사위원 판정 (참고)", f"{verdict.get('summary', '')} 점수: {rows}"]
    return "\n\n".join(parts)


def analyst_prompt(history: list[dict], question: str) -> str:
    lines = []
    for item in history[-12:]:   # 앞서 주고받은 문답. 너무 길어지지 않게 최근 것만
        lines += [f"질문: {item.get('q', '')}", f"답: {item.get('a', '')}", ""]
    lines.append(f"질문: {question.strip()}")
    return "\n".join(lines)
