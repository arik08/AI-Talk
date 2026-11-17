"""서버를 켠다: python -m aitalk [--open]

.env의 AITALK_HOST와 AITALK_PORT를 따른다. 기본은 내 PC에서만 접속되는 127.0.0.1:8765이다.
AITALK_HOST=0.0.0.0으로 두면 같은 망의 다른 PC에서 http://내IP:포트 로 접속할 수 있다.
"""
from __future__ import annotations

import sys
import threading
import webbrowser

import uvicorn

from .config import lan_addresses, settings


def main() -> None:
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
