"""실행 창(터미널)에 찍는 글. 여러 터미널 가운데서 AI-Talk 창을 바로 알아볼 수 있게 색을 쓴다.

낡은 콘솔에서도 깨지지 않도록 로고는 ASCII 문자로만 그린다.
"""
from __future__ import annotations

import datetime as dt
import os
import sys

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
UNDER = "\033[4m"


def rgb(r: int, g: int, b: int) -> str:
    return f"\033[38;2;{r};{g};{b}m"


def bg(r: int, g: int, b: int) -> str:
    return f"\033[48;2;{r};{g};{b}m"


GOLD = rgb(232, 193, 112)
GOLD_HI = rgb(244, 220, 154)
GOLD_LO = rgb(168, 130, 63)
EMBER = rgb(255, 122, 60)
GREEN = rgb(70, 200, 90)
CYAN = rgb(110, 220, 255)
TEXT = rgb(236, 226, 204)
MUTED = rgb(150, 138, 114)

LOGO = r"""
      ##     ####         ######    ##     ##      ##  ##
     ####     ##            ##     ####    ##      ## ##
    ##  ##    ##   ####     ##    ##  ##   ##      ####
    ######    ##            ##    ######   ##      ## ##
    ##  ##   ####           ##    ##  ##   ######  ##  ##
"""


def setup(title: str = "AI-Talk") -> None:
    """색을 쓸 수 있게 콘솔을 준비하고 창 제목을 붙인다."""
    if os.name == "nt":
        os.system("")   # Windows 콘솔의 ANSI 색 처리를 켠다
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    sys.stdout.write(f"\033]0;{title}\007")
    sys.stdout.flush()


def banner(*, provider: str, model: str, ready: bool, port: int, addresses: list[str],
           shared: bool, code: bool, launcher: bool = False) -> None:
    """켤 때 보여 주는 안내. 키와 접속 코드의 값은 찍지 않는다 (있는지 없는지만)."""
    bar = bg(232, 193, 112) + rgb(26, 18, 8) + BOLD
    width = 64
    print()
    print(bar + "  AI-TALK".ljust(width) + RESET)
    print(GOLD + LOGO.rstrip("\n") + RESET)
    print()
    print(bar + "  AI debate stage".ljust(width) + RESET)
    print()

    def row(label: str, value: str) -> None:
        print(f"  {GOLD_LO}{label}{RESET}  {value}{RESET}")

    dot = f"{GREEN}●{RESET}" if ready else f"{EMBER}●{RESET}"
    row("AI      ", f"{dot} {TEXT}{BOLD}{provider}{RESET}{MUTED}  {model}" + ("" if ready else f"  {EMBER}(키가 없어 준비 안 됨)"))
    row("이 PC   ", f"{TEXT}{UNDER}http://127.0.0.1:{port}")
    if shared:
        if addresses:
            for ip in addresses:
                row("다른 PC ", f"{CYAN}{BOLD}{UNDER}http://{ip}:{port}{RESET}{MUTED}   <- 같은 망의 다른 PC에서는 이 주소로")
        else:
            row("다른 PC ", f"{MUTED}이 PC의 IP를 찾지 못했습니다. ipconfig로 확인한 IP 뒤에 :{port} 를 붙이세요")
        if code:
            row("접속 코드", f"{GREEN}있음{RESET}{MUTED}  다른 PC에서 들어오면 코드를 묻습니다")
        else:
            row("접속 코드", f"{EMBER}없음{RESET}{MUTED}  같은 망의 누구나 들어올 수 있습니다 (.env의 AITALK_ACCESS_CODE로 정함)")
    else:
        row("다른 PC ", f"{MUTED}꺼져 있음 (.env의 AITALK_HOST=127.0.0.1)")
    row("끄기    ", f"{TEXT}Ctrl+C")
    if launcher:   # ai-talk.bat(실행기)으로 켰을 때만 통한다
        row("다시 켜기", f"{TEXT}{BOLD}R{RESET}{MUTED}  이 창에서 Enter 없이. 설정과 코드를 다시 읽습니다 (진행 중인 토론은 끊깁니다)")
    print(f"  {GOLD_LO}{'-' * (width - 4)}{RESET}")
    print()


def say(text: str, color: str = TEXT, mark: str = ">") -> None:
    """실행 창에 한 줄 알린다 (토론 시작, 끝 등)."""
    now = dt.datetime.now().strftime("%H:%M:%S")
    try:
        print(f"  {MUTED}{now}{RESET}  {GOLD}{mark}{RESET} {color}{text}{RESET}", flush=True)
    except (UnicodeEncodeError, OSError):
        pass
