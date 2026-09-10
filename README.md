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

화면은 IDE형 4열이다 — 좌측 액티비티 바(파일·규칙·스킬·훅·MCP 뷰 전환), 탐색기 트리(전역·프로젝트·플러그인), 중앙 에디터(열린 파일 탭·줄번호 원문 또는 선택한 뷰), 우측 인스펙터(스캔 정보·속성·함께 적용되는 규칙·프로젝트 훅·재스캔/종료). 다크 기본, OS 라이트 테마를 따른다.

## 기능

- **조망** — 전역·프로젝트·플러그인 설정 트리, 원문 보기, 프로젝트에 적용되는 규칙 순서, 훅 흐름, MCP 서버 목록.
- **편집** — 원문 뷰에서 편집 버튼으로 텍스트 편집(`Ctrl+S` 저장). 플러그인 소속 파일은 읽기 전용이다. 팀 공유(git 추적) 파일은 편집 시 경고를 띄운다.
- **검증** — 저장 전에 규칙을 돌린다. 오류가 하나라도 있으면 저장하지 않는다(경고는 저장을 막지 않는다).

  | 규칙 | 수준 | 대상 | 내용 |
  |---|---|---|---|
  | V1 | 오류 | `*.json` | JSON 파싱 실패 (줄 번호 표시) |
  | V2 | 오류 | `SKILL.md`·`agents/*.md`·`commands/*.md` | frontmatter 필수 키(`name`·`description`) 누락 |
  | V3 | 오류 | `settings*.json` | 훅 `command` 의 스크립트 경로가 실존하지 않음 (환경변수가 섞인 경로는 건너뜀, 실행은 하지 않음) |
  | V4 | 오류 | 마크다운 | `@경로` import·상대 링크 대상이 실존하지 않음 |
  | V6 | 경고 | `settings*.json` | `*` 매처와 중복 발화하는 훅 |
  | V7 | — | 모든 저장 | 읽은 뒤 디스크에서 파일이 바뀌었으면 저장을 막고 다시 읽기를 요구 |

- **저장·백업** — 저장은 원자적으로 쓰고, 원본 줄바꿈(CRLF/LF)과 BOM을 그대로 보존한다. 쓰기 전 원본을 `~/.claude/config-map/backups/<경로 해시>/` 아래에 복사하며, 파일당 최근 10개만 남긴다.

스킬 on/off 토글은 이후 버전이다.

## 이 버전이 쓰는 파일

- **읽기** — 스캔 대상 전부: `~/.claude/` 아래 CLAUDE.md·rules·settings·skills·agents·commands·plugins, `~/.claude.json` 의 프로젝트 목록과 각 프로젝트의 `.claude/` 및 `CLAUDE.md`·`.mcp.json`.
- **쓰기** — 사용자가 UI에서 직접 저장한 파일, 그 파일의 백업(`~/.claude/config-map/backups/…`), 서버 접속 정보(`~/.claude/config-map/server.json`). 그 밖의 파일은 쓰지 않는다.

## 검증된 OS

| OS | 상태 | 47개 프로젝트 스캔 시간 |
|---|---|---|
| Windows 11 | 검증됨 (로컬 마켓플레이스 설치 → `/config-map` → 브라우저 5개 뷰) | 첫 스캔 3.4~4.6초, 재스캔 2.7~2.9초 (47개 프로젝트·3개 플러그인, 2026-09-10 실측) |
| macOS | 미검증 | — |
| Linux | 미검증 | — |

## 데이터 위치

사용자 데이터(서버 정보·백업)는 `~/.claude/config-map/` 아래에만 쓴다. 설정 파일은 사용자가 UI에서 저장할 때만 그 파일 자리에 쓴다. 플러그인 캐시(`~/.claude/plugins/cache/...`)에는 아무것도 쓰지 않는다 — 업데이트 시 통째로 교체되는 경로이기 때문이다.

## 팀원 안내

레포가 비공개인 동안은 마켓플레이스 등록 시 팀원마다 GitHub 인증이 필요하다.
