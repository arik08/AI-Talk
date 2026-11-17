"""서버를 켠다: python -m aitalk [--open] [--no-build]

.env의 AITALK_HOST와 AITALK_PORT를 따른다. 기본은 내 PC에서만 접속되는 127.0.0.1:8765이다.
AITALK_HOST=0.0.0.0으로 두면 같은 망의 다른 PC에서 http://내IP:포트 로 접속할 수 있다.
"""
from __future__ import annotations

import subprocess
import sys
import threading
import webbrowser

import uvicorn

from .config import ROOT, WEB_DIST, lan_addresses, settings


def ensure_web_built() -> None:
    """화면 소스가 빌드 결과보다 새로우면 다시 빌드한다. 바뀐 것이 없으면 건너뛰어 바로 켜진다."""
    web = ROOT / "apps" / "web"
    built = WEB_DIST / "index.html"
    if not (web / "node_modules").exists():
        if built.exists():
            return
        sys.exit("화면 패키지가 설치되어 있지 않습니다. installer.bat을 먼저 실행해 주세요.")
    sources = [p for p in (web / "src").rglob("*") if p.is_file()] + [web / "index.html", web / "package.json"]
    newest = max((p.stat().st_mtime for p in sources if p.exists()), default=0)
    if built.exists() and built.stat().st_mtime >= newest:
        return
    print("화면을 빌드합니다...")
    done = subprocess.run("npm run build", cwd=web, shell=True, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if done.returncode != 0:
        print((done.stdout or "")[-1500:], (done.stderr or "")[-1500:])
        if not built.exists():
            sys.exit("화면 빌드에 실패했습니다.")
        print("화면 빌드에 실패해 예전 화면으로 켭니다.")


def main() -> None:
    if "--no-build" not in sys.argv:
        ensure_web_built()
    host = settings.host
    port = settings.port
    shared = host not in ("127.0.0.1", "localhost", "::1")
    print(f"\nAI-Talk  (AI: {settings.provider})")
    print(f"  이 PC에서:   http://127.0.0.1:{port}")
    if shared:
        for ip in lan_addresses():
            print(f"  다른 PC에서: http://{ip}:{port}")
        if settings.get("AITALK_ACCESS_CODE"):
            print("  다른 PC에서 접속하면 접속 코드를 묻습니다 (.env의 AITALK_ACCESS_CODE).")
        else:
            print("  주의: 접속 코드가 없습니다. 같은 망의 누구나 이 주소로 들어와 내 AI 키로 토론을 돌릴 수 있습니다.")
            print("        .env에 AITALK_ACCESS_CODE=원하는코드 를 넣으면 코드를 아는 사람만 들어옵니다.")
        print("  처음 켤 때 Windows 방화벽이 물으면 '액세스 허용'을 눌러야 다른 PC에서 들어올 수 있습니다.")
    print("  끄려면 이 창에서 Ctrl+C를 누르세요.\n")
    if "--open" in sys.argv:
        threading.Timer(1.2, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()
    uvicorn.run("aitalk.app:app", host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
