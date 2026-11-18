"""Windows 실행기(scripts/launch_aitalk.py)의 판단 부분: 리셋 키, 포트 정리, 다시 켜기 흐름."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import launch_aitalk as la  # noqa: E402
from aitalk import console  # noqa: E402


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def test_reset_key_accepts_r_in_any_input_state():
    for kw in ({"char": "r", "vk": la.VK_R}, {"char": "R", "vk": la.VK_R}, {"char": "ㄱ", "vk": 0xE5},
               {"char": "\x00", "vk": 0xE5, "scan": la.SCAN_R}, {"vk": la.VK_R}):
        assert la.ResetKey(Clock()).feed(down=True, **kw), kw
    for kw in ({"char": "t", "vk": 0x54}, {"char": "\r", "vk": 0x0D}, {"char": "ㄴ", "vk": 0xE5, "scan": 0x1F}):
        assert not la.ResetKey(Clock()).feed(down=True, **kw), kw
    assert not la.ResetKey(Clock()).feed(down=True, char="\x12", vk=la.VK_R, modified=True)   # Ctrl+R


def test_holding_the_key_resets_only_once():
    clock = Clock()
    key = la.ResetKey(clock)
    assert key.feed(down=True, char="r", vk=la.VK_R) is True
    for _ in range(40):                                  # 누르고 있는 동안 오는 반복 입력
        clock.now += 0.03
        assert key.feed(down=True, char="r", vk=la.VK_R) is False
    assert key.feed(down=False, char="r", vk=la.VK_R) is False
    assert key.feed(down=True, char="r", vk=la.VK_R) is True     # 뗐다가 다시 누르면 다시 리셋
    clock.now += la.HOLD_GAP + 0.1                        # 뗀 신호를 놓쳤어도 한참 뒤에 누른 것은 새 입력이다
    assert key.feed(down=True, char="ㄱ", vk=0xE5) is True


NETSTAT = """
활성 연결

  프로토콜  로컬 주소              외부 주소              상태            PID
  TCP    0.0.0.0:135            0.0.0.0:0              LISTENING       1188
  TCP    0.0.0.0:8765           0.0.0.0:0              LISTENING       4321
  TCP    127.0.0.1:18765        0.0.0.0:0              LISTENING       5555
  TCP    127.0.0.1:50123        127.0.0.1:8765         ESTABLISHED     7777
  TCP    [::]:8765              [::]:0                 LISTENING       4322
  UDP    0.0.0.0:8765           *:*                                    9999
"""


def test_netstat_parsing_finds_only_listeners_on_that_port():
    assert la.parse_netstat(NETSTAT, 8765) == {4321, 4322}
    assert la.parse_netstat(NETSTAT, 135) == {1188}
    assert la.parse_netstat(NETSTAT, 9) == set()


def test_free_port_kills_listeners_but_never_itself(monkeypatch):
    monkeypatch.setattr(la.os, "getpid", lambda: 4322)
    alive = {4321, 4322, 4}
    killed: list[int] = []

    def kill(pid: int) -> None:
        killed.append(pid)
        alive.discard(pid)

    out = la.free_port(8765, find=lambda port: set(alive), kill=kill, sleep=lambda s: None)
    assert out == {4321} and killed == [4321]             # 자기 자신과 시스템 프로세스는 건드리지 않는다


def test_free_port_gives_up_after_waiting():
    tries: list[int] = []
    la.free_port(8765, find=lambda port: {4321}, kill=tries.append, sleep=lambda s: None, waits=5)
    assert tries == [4321]                                # 같은 프로세스를 되풀이해 끝내려 하지 않는다


def test_browser_opens_only_on_the_first_start():
    assert la.server_command(True)[-3:] == ["-m", "aitalk", "--open"]
    assert "--open" not in la.server_command(False)


class FakeProc:
    def __init__(self, codes: list) -> None:
        self.codes = codes      # poll()이 차례로 돌려줄 값

    def poll(self):
        return self.codes.pop(0) if len(self.codes) > 1 else self.codes[0]


class FakeKeys:
    def __init__(self, presses: list, available: bool = True) -> None:
        self.presses, self.available = presses, available

    def reset_pressed(self) -> bool:
        step = self.presses.pop(0) if self.presses else False
        if step is KeyboardInterrupt:
            raise KeyboardInterrupt
        return bool(step)


def _launcher(keys, procs: list):
    log: list = []
    said: list[str] = []

    def start(first: bool):
        log.append(("start", first))
        return procs.pop(0)

    launcher = la.Launcher(keys=keys, start=start, stop=lambda proc: log.append(("stop", proc)),
                           free=lambda port: log.append(("free", port)) or set(), port=lambda: 8765,
                           tell=said.append, sleep=lambda s: None)
    return launcher, log, said


def test_r_restarts_and_ctrl_c_stops():
    first, second = FakeProc([None]), FakeProc([None])
    launcher, log, said = _launcher(FakeKeys([False, False, True, False, KeyboardInterrupt]), [first, second])
    assert launcher.run() == 0
    assert log == [("free", 8765), ("start", True), ("stop", first),
                   ("free", 8765), ("start", False), ("stop", second)]   # 포트 정리 → 켜기, 브라우저는 처음만
    assert any("하드 리셋" in line for line in said)


def test_crashed_server_can_be_retried_with_r():
    crashed, healthy = FakeProc([1]), FakeProc([None])
    launcher, log, said = _launcher(FakeKeys([False, False, False, True, KeyboardInterrupt]), [crashed, healthy])
    assert launcher.run() == 0
    assert [entry for entry in log if entry[0] == "start"] == [("start", True), ("start", False)]
    assert sum("서버가 꺼졌습니다" in line for line in said) == 1          # 안내는 한 번만


def test_without_a_console_the_launcher_exits_with_the_servers_code():
    launcher, log, _ = _launcher(FakeKeys([], available=False), [FakeProc([None, None, 3])])
    assert launcher.run() == 3


def test_banner_shows_keys_and_addresses_but_no_secret_values(capsys):
    console.banner(provider="P-GPT", model="gpt-6-luna", ready=True, port=8765, addresses=["10.1.2.3"],
                   shared=True, code=True, launcher=True)
    out = capsys.readouterr().out
    assert "http://127.0.0.1:8765" in out and "http://10.1.2.3:8765" in out
    assert "Ctrl+C" in out and "다시 켜기" in out and "접속 코드" in out
    console.banner(provider="P-GPT", model="gpt-6-luna", ready=True, port=8765, addresses=[], shared=False, code=False)
    assert "다시 켜기" not in capsys.readouterr().out      # 실행기 없이 켰을 때는 R 안내를 하지 않는다
