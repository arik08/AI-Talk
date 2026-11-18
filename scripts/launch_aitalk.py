"""AI-Talk 실행기. ai-talk.bat이 부른다.

서버(python -m aitalk)를 별도 프로세스로 켜 두고, 이 창에서 키를 읽는다.

- R (또는 r, 한글 입력 상태의 ㄱ): Enter 없이 바로 하드 리셋. 진행 중인 토론과 서버·빌드 자식 프로세스를
  끝내고, 새 파이썬 프로세스로 .env와 코드를 다시 읽어 켠다. 저장된 토론 기록과 페르소나는 그대로다.
- Ctrl+C: 서버와 실행기를 끝낸다.
- 서버가 코드 오류 등으로 꺼져도 이 창은 남는다. 고친 뒤 R을 누르면 다시 켠다.

주의: 켜기 전과 다시 켜기 전에 설정된 포트(.env의 AITALK_PORT, 기본 8765)를 듣고 있는 프로세스를 모두 끝낸다.
다른 프로그램이 같은 포트를 쓰고 있어도 끝내므로, 겹치면 AITALK_PORT를 바꿔야 한다.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Optional

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "apps" / "server"

VK_R = 0x52
SCAN_R = 0x13            # 자판의 R 자리. 한글 입력 상태에서도 같다
RESET_CHARS = "rRㄱ"
HOLD_GAP = 1.2           # 누르고 있으면 이 시간 안에 반복 입력이 온다. 이보다 뜸하면 새로 누른 것이다
SYSTEM_PIDS = {0, 4}


class ResetKey:
    """리셋 키가 새로 눌렸는지 판별한다. 누르고 있는 동안에는 한 번만 참이 된다."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self.clock = clock
        self.held = False
        self.last = 0.0

    @staticmethod
    def is_reset(vk: int = 0, scan: int = 0, char: str = "") -> bool:
        return vk == VK_R or scan == SCAN_R or (bool(char) and char in RESET_CHARS)

    def feed(self, *, down: bool, vk: int = 0, scan: int = 0, char: str = "", modified: bool = False) -> bool:
        if not self.is_reset(vk, scan, char):
            return False
        now = self.clock()
        if not down:
            self.held = False
            return False
        if modified:                       # Ctrl+R, Alt+R은 리셋이 아니다
            return False
        fresh = not self.held or now - self.last > HOLD_GAP   # 키를 뗀 신호를 놓쳤을 때를 대비한다
        self.held, self.last = True, now
        return fresh


class ConsoleKeys:
    """Windows 콘솔의 키 입력을 Enter 없이 읽는다. 서버에는 표준 입력을 넘기지 않으므로 여기서만 읽는다."""

    def __init__(self) -> None:
        self.detector = ResetKey()
        self.available = False
        self._handle = None
        if os.name != "nt":
            return
        try:
            import ctypes
            from ctypes import wintypes

            class KeyEvent(ctypes.Structure):
                _fields_ = [("bKeyDown", wintypes.BOOL), ("wRepeatCount", wintypes.WORD),
                            ("wVirtualKeyCode", wintypes.WORD), ("wVirtualScanCode", wintypes.WORD),
                            ("UnicodeChar", wintypes.WCHAR), ("dwControlKeyState", wintypes.DWORD)]

            class Event(ctypes.Union):
                _fields_ = [("Key", KeyEvent), ("raw", ctypes.c_byte * 16)]

            class InputRecord(ctypes.Structure):
                _fields_ = [("EventType", wintypes.WORD), ("Event", Event)]

            self._ctypes, self._wintypes, self._record = ctypes, wintypes, InputRecord
            self._kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            self._kernel.GetStdHandle.restype = wintypes.HANDLE
            handle = self._kernel.GetStdHandle(wintypes.DWORD(-10 & 0xFFFFFFFF))   # STD_INPUT_HANDLE
            mode = wintypes.DWORD()
            if handle and self._kernel.GetConsoleMode(wintypes.HANDLE(handle), ctypes.byref(mode)):
                self._handle = wintypes.HANDLE(handle)
                self.available = True
        except Exception:  # noqa: BLE001 - 콘솔이 아니면(다른 프로그램이 띄운 경우 등) 키 없이 돈다
            self.available = False

    def reset_pressed(self) -> bool:
        """쌓인 키 입력을 모두 읽어, 그 가운데 리셋 키가 새로 눌린 것이 있으면 True."""
        if not self.available:
            return False
        ctypes, wintypes = self._ctypes, self._wintypes
        pressed = False
        count = wintypes.DWORD()
        while self._kernel.GetNumberOfConsoleInputEvents(self._handle, ctypes.byref(count)) and count.value:
            records = (self._record * min(count.value, 64))()
            read = wintypes.DWORD()
            if not self._kernel.ReadConsoleInputW(self._handle, records, len(records), ctypes.byref(read)):
                break
            for record in records[:read.value]:
                if record.EventType != 1:   # KEY_EVENT
                    continue
                key = record.Event.Key
                modified = bool(key.dwControlKeyState & 0x000F)   # Ctrl, Alt
                if self.detector.feed(down=bool(key.bKeyDown), vk=key.wVirtualKeyCode, scan=key.wVirtualScanCode,
                                      char=key.UnicodeChar, modified=modified):
                    pressed = True
        return pressed


# ---------------------------------------------------------------- 포트와 프로세스
def parse_netstat(text: str, port: int) -> set[int]:
    """`netstat -ano` 출력에서 그 포트를 듣고 있는 프로세스 번호를 찾는다."""
    found: set[int] = set()
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 5 or parts[0].upper() != "TCP" or parts[3].upper() != "LISTENING":
            continue
        if parts[1].rsplit(":", 1)[-1] != str(port):
            continue
        try:
            found.add(int(parts[4]))
        except ValueError:
            continue
    return found


def listeners(port: int) -> set[int]:
    if os.name != "nt":
        return set()
    found: set[int] = set()
    for proto in ("TCP", "TCPv6"):
        try:
            done = subprocess.run(["netstat", "-ano", "-p", proto], capture_output=True, text=True, errors="replace",
                                  timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            continue
        found |= parse_netstat(done.stdout, port)
    return found


def kill_tree(pid: int) -> None:
    """프로세스와 그 자식(빌드 중인 npm 등)까지 끝낸다."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, timeout=15)
    else:
        try:
            os.kill(pid, 15)
        except OSError:
            pass


def free_port(port: int, *, find: Callable[[int], set[int]] = listeners, kill: Callable[[int], None] = kill_tree,
              sleep: Callable[[float], None] = time.sleep, waits: int = 50) -> set[int]:
    """그 포트를 듣는 프로세스를 끝내고 포트가 빌 때까지 잠깐 기다린다. 끝낸 프로세스 번호를 돌려준다."""
    own = {os.getpid(), os.getppid()} | SYSTEM_PIDS
    killed: set[int] = set()
    for _ in range(waits):
        targets = find(port) - own
        if not targets:
            break
        for pid in targets - killed:
            kill(pid)
            killed.add(pid)
        sleep(0.1)
    return killed


def read_port() -> int:
    """.env를 다시 읽어 포트를 구한다 (재시작할 때 바뀐 설정을 따른다)."""
    if str(SERVER) not in sys.path:
        sys.path.insert(0, str(SERVER))
    from aitalk.config import settings
    settings.reload()
    return settings.port


def server_command(first: bool) -> list[str]:
    """브라우저는 처음 켤 때만 연다."""
    return [sys.executable, "-m", "aitalk"] + (["--open"] if first else [])


def start_server(first: bool) -> subprocess.Popen:
    flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)   # Ctrl+C는 실행기가 받아서 정리한다
    return subprocess.Popen(server_command(first), cwd=SERVER, stdin=subprocess.DEVNULL,
                            env={**os.environ, "AITALK_LAUNCHER": "1"}, creationflags=flags)


def stop_server(proc: Optional[subprocess.Popen]) -> None:
    if proc is None:
        return
    if proc.poll() is None:
        kill_tree(proc.pid)
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()


def say(text: str) -> None:
    try:
        print(f"\n  [AI-Talk] {text}", flush=True)
    except (UnicodeEncodeError, OSError):
        pass


class Launcher:
    def __init__(self, *, keys, start=start_server, stop=stop_server, free=free_port, port=read_port,
                 tell=say, sleep=time.sleep) -> None:
        self.keys, self.start, self.stop, self.free, self.port = keys, start, stop, free, port
        self.tell, self.sleep = tell, sleep

    def watch(self, proc) -> object:
        """리셋 키가 눌리면 "reset", 서버가 꺼졌고 키를 읽을 수 없으면 종료 코드를 돌려준다."""
        told = False
        while True:
            if self.keys.reset_pressed():
                return "reset"
            code = proc.poll()
            if code is not None:
                if not self.keys.available:
                    return code
                if not told:
                    self.tell(f"서버가 꺼졌습니다 (종료 코드 {code}). 고친 뒤 R을 누르면 다시 켜고, Ctrl+C를 누르면 끝냅니다.")
                    told = True
            self.sleep(0.05)

    def run(self) -> int:
        proc = None
        first = True
        try:
            while True:
                killed = self.free(self.port())
                if killed and first:
                    self.tell(f"같은 포트를 쓰던 프로세스를 끝냈습니다: {sorted(killed)}")
                proc = self.start(first)
                first = False
                result = self.watch(proc)
                self.stop(proc)
                if result != "reset":
                    return int(result or 0)
                self.tell("하드 리셋: 서버를 끝내고 설정과 코드를 다시 읽어 켭니다. 브라우저는 새로고침해 주세요.")
        except KeyboardInterrupt:
            self.stop(proc)
            self.tell("끝냅니다.")
            return 0


def main() -> int:
    if not (ROOT / ".env").exists():
        print(".env 파일이 없습니다. installer.bat을 먼저 실행해 주세요.")
        return 1
    return Launcher(keys=ConsoleKeys()).run()


if __name__ == "__main__":
    sys.exit(main())
