---
description: 로컬 Claude 설정 전체를 브라우저에서 조망하는 config-map 서버를 띄운다
allowed-tools: Bash
disable-model-invocation: true
---

# Config Map

이 PC의 Claude Code 설정(전역 CLAUDE.md, 프로젝트별 규칙, 스킬·에이전트·커맨드, 훅, 플러그인, MCP)을 한 화면에서 보는 로컬 서버를 띄운다.

## Usage

```bash
# 1. Python 후보를 순서대로 검사한다. 첫 성공에서 멈춘다.
python3 --version
python --version
py -3 --version

# 2. 찾은 Python으로 서버를 띄운다 (Bash 도구의 run_in_background 로 실행).
"<찾은 python>" "${CLAUDE_PLUGIN_ROOT}/server/web_server.py"
```

## Notes

- 서버 스크립트 경로는 `${CLAUDE_PLUGIN_ROOT}/server/web_server.py` 다. `CLAUDE_PLUGIN_ROOT` 가 비어 있으면 폴백으로 `~/.claude/plugins/cache/claude-config-map/config-map/*/server/web_server.py` 중 **버전 폴더명이 가장 큰 것**을 쓴다.
- Python 실행 파일은 `python3` → `python` → `py -3` 순서로 시도한다. 각 후보마다 먼저 `<후보> --version` 을 실행해 출력이 **Python 3.11 이상**인지 확인하고, 첫 성공 후보에서 멈춘다. (Windows Store의 가짜 `python` 별칭은 `--version` 이 실패하거나 설치 창만 열므로 이 검사로 걸러진다.)
- 어느 후보도 없거나 전부 3.11 미만이면 **아래 문구만 출력하고 끝낸다.** 자동 설치나 추가 경로 탐색은 하지 않는다.

  > config-map은 Python 3.11 이상이 필요합니다. https://www.python.org/downloads/ 에서 설치한 뒤 새 터미널에서 /config-map 을 다시 실행하세요.

- 서버는 Bash 도구의 `run_in_background` 로 실행한다. stdout 첫 줄에 URL이 나오므로 그 URL을 사용자에게 그대로 보여준다.
- 서버가 이미 떠 있으면 스크립트가 기존 URL만 열고 바로 종료한다. 그 경우에도 출력된 URL을 그대로 보여준다.
- 셸 스크립트 파일(`.sh` / `.ps1`)은 만들지 않는다. 명령은 Git Bash와 PowerShell 양쪽에서 동작하도록 경로를 따옴표로 감싸고 `&&` / `||` 는 쓰지 않는다.
- Windows에서 `CLAUDE_PLUGIN_ROOT` 는 역슬래시 경로일 수 있다. 변환하지 말고 따옴표로 감싸 그대로 넘긴다.

### 예시

```bash
python3 --version
# -> Python 3.12.4  (3.11 이상, 여기서 멈춘다)

"python3" "${CLAUDE_PLUGIN_ROOT}/server/web_server.py"
# -> http://127.0.0.1:8765
```

이 URL을 사용자에게 안내하고 끝낸다.
