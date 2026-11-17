# AI-Talk

주제를 던지면 AI 참가자들이 실제 토론처럼 말을 주고받는 프로그램입니다. 내 PC에서 혼자 씁니다.

설계와 현재 상태는 [docs/design.md](docs/design.md)에 있습니다.

## 처음 한 번

Python 3.13과 Node.js가 필요합니다.

1. `install.bat`을 실행합니다. 파이썬 패키지와 화면 패키지를 설치하고 화면을 빌드합니다.
2. `.env`를 열어 값을 채웁니다 (`.env.example` 참고).

| `AITALK_PROVIDER` | 쓰는 곳 | 필요한 값 |
|---|---|---|
| `claude` | 집 | `ANTHROPIC_API_KEY` |
| `pgpt` | 회사 OA망 | `PGPT_API_KEY`, `PGPT_EMPNO` |
| `mock` | 화면만 확인 | 없음. AI를 부르지 않습니다 |

## 실행

`run.bat`을 실행하면 브라우저에서 http://127.0.0.1:8765 가 열립니다.

## 회사에서 P-GPT를 처음 쓸 때

P-GPT 쪽은 집에서 실행해 보지 못했습니다. 먼저 점검 스크립트를 돌려 주세요.

```bash
python scripts/check_pgpt.py
```

끝에 나오는 표에서 "안 됨"인 항목이 있으면 그 표를 그대로 전달해 주세요.

## 개발

```bash
python -m pytest apps/server/tests -q
```

화면을 고치면서 볼 때는 서버(8765)를 띄운 채로 `apps/web`에서 `npm run dev`를 실행하고 http://127.0.0.1:5180 을 엽니다.

## 폴더

| 폴더 | 내용 |
|---|---|
| `apps/server` | FastAPI 서버, 토론 엔진, 프로바이더(Claude, P-GPT, mock) |
| `apps/web` | 화면 (Vite + TypeScript, Lucide) |
| `presets` | 기본 인물 |
| `data` | 페르소나 보관함과 토론 기록 (git 제외) |
| `scripts` | P-GPT 점검 스크립트 |
