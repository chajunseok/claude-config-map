# claude-config-map

PC 안에 흩어진 Claude Code 설정(전역 CLAUDE.md, 프로젝트별 규칙, 스킬·에이전트·커맨드, 훅, 플러그인, MCP)을 한 화면에서 조망하는 로컬 도구다.

## 설치

Claude Code 세션에서 아래 두 줄을 실행한다.

```
/plugin marketplace add chajunseok/claude-config-map
/plugin install config-map@claude-config-map
```

## 요구사항

- **Python 3.11 이상 (필수)**. 플러그인은 Python을 동봉하지 않으므로 PC에 미리 설치되어 있어야 한다. 없으면 `/config-map` 이 설치 안내 문구만 출력하고 끝난다. [python.org/downloads](https://www.python.org/downloads/)
- Claude Code **2.1.199 이상 권장**. 미만이어도 조망 기능은 동작한다.
- 표준 라이브러리만 쓴다. 추가 패키지 설치 없음.

## 사용법

```
/config-map
```

브라우저가 열리고 URL이 대화에 표시된다. 서버가 이미 떠 있으면 기존 URL을 그대로 연다. 종료는 UI의 종료 버튼.

## 현재 범위

**v0.1.0 — 읽기 전용.** 스캔, 조망, 훅 흐름도까지다. 저장·검증·토글(스킬 on/off)은 이후 버전이다. 어떤 설정 파일도 이 버전은 쓰지 않는다.

## 검증된 OS

| OS | 상태 | 47개 프로젝트 스캔 시간 |
|---|---|---|
| Windows 11 | 검증됨 | 측정 예정 |
| macOS | 미검증 | — |
| Linux | 미검증 | — |

## 데이터 위치

사용자 데이터는 `~/.claude/config-map/` 아래에만 쓴다. 플러그인 캐시(`~/.claude/plugins/cache/...`)에는 아무것도 쓰지 않는다 — 업데이트 시 통째로 교체되는 경로이기 때문이다.

## 팀원 안내

레포가 비공개인 동안은 마켓플레이스 등록 시 팀원마다 GitHub 인증이 필요하다.
