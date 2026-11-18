"""Windows에서 실제 프로세스로 보는 실행기 검사: 포트를 듣는 프로세스 찾기와 자식까지 끝내기.

이 시험이 띄운 프로세스와 임시 포트만 건드린다. AI-Talk 서버나 8765 포트는 건드리지 않는다.
"""
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import launch_aitalk as la  # noqa: E402

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows 실행기 전용")

CHILD = """
import socket, subprocess, sys, time
grand = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
server = socket.socket()
server.bind(("127.0.0.1", int(sys.argv[1])))
server.listen()
print(grand.pid, flush=True)
time.sleep(120)
"""


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _alive(pid: int) -> bool:
    done = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH", "/FO", "CSV"], capture_output=True, text=True,
                          errors="replace", timeout=15)
    return f'"{pid}"' in done.stdout


def test_listener_is_found_and_killed_with_its_children():
    port = _free_port()
    child = subprocess.Popen([sys.executable, "-c", CHILD, str(port)], stdout=subprocess.PIPE, text=True,
                             stdin=subprocess.DEVNULL, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
    try:
        grand = int(child.stdout.readline().strip())      # 자식이 포트를 열고 손자를 띄운 뒤에 찍는다
        assert child.pid in la.listeners(port)
        assert la.free_port(port) == {child.pid}
        child.wait(timeout=10)
        for _ in range(50):
            if not _alive(grand):
                break
            time.sleep(0.1)
        assert not _alive(grand)                           # 자식 프로세스까지 끝난다
        assert la.listeners(port) == set()
    finally:
        if child.poll() is None:
            la.kill_tree(child.pid)


def test_console_keys_do_nothing_without_a_console():
    keys = la.ConsoleKeys()            # 시험은 콘솔 입력 없이 돌 수 있다. 그때는 키를 읽지 않는다
    assert keys.reset_pressed() in (False, True)
    if not keys.available:
        assert keys.reset_pressed() is False
