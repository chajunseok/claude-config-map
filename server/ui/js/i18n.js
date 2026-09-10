// i18n — 한→영 사전 하나. 한국어 원문이 키다. 사전에 없으면 원문 그대로 (ko 모드는 무손실)
"use strict";
var LANG = (function(){
  try { var v = localStorage.getItem("cm.lang"); if(v === "ko" || v === "en") return v; } catch(e){}
  return (navigator.language || "").toLowerCase().indexOf("ko") === 0 ? "ko" : "en";
})();
var EN = {
  /* ---- 앱 ---- */
  "Claude 설정 지도": "Claude Config Map",
  "탐색기": "Explorer",
  "인스펙터": "Inspector",
  "상태": "Status",
  "사이드바": "Sidebar",
  "사이드바 전환": "Switch sidebar",
  "사이드바 목록": "Sidebar list",
  "언어 전환": "Switch language",
  "저장하지 않은 변경이 있습니다. 언어를 바꾸면 사라집니다. 계속할까요?":
    "You have unsaved changes. Switching language will discard them. Continue?",

  /* ---- 액티비티 바 / 뷰 ---- */
  "파일": "Files",
  "규칙": "Rules",
  "스킬": "Skills",
  "훅": "Hooks",
  "스킬·에이전트·커맨드": "Skills, agents & commands",
  "전역 · 프로젝트 · 플러그인 설정 파일 트리. 클릭하면 에디터에서 원문·편집":
    "Tree of global, project and plugin config files. Click to view and edit the source",
  "선택 프로젝트에 실제로 적용되는 CLAUDE.md 체인 — 적용 순서대로":
    "The CLAUDE.md chain that actually applies to the selected project — in apply order",
  "전역 · 이 프로젝트 · 플러그인의 스킬/에이전트/커맨드와 이 프로젝트에서의 ON/OFF":
    "Skills, agents and commands from global, this project and plugins, with ON/OFF for this project",
  "settings.json 훅을 이벤트별 매처 → 명령 순서로. 색은 출처(전역/프로젝트/플러그인)":
    "settings.json hooks by event, matcher then command. Color marks the origin (global/project/plugin)",
  "MCP 서버를 출처별로": "MCP servers grouped by origin",
  "적용 순서": "apply order",
  "ON/OFF 대상": "ON/OFF target",
  "세션 이벤트 순": "session event order",
  "전역 + 이 프로젝트": "global + this project",
  "전역 + 모든 프로젝트": "global + all projects",

  /* ---- 종류·범위·출처 라벨 (내부 값은 그대로, 표시만 번역) ---- */
  "에이전트": "Agent",
  "커맨드": "Command",
  "전역": "Global",
  "전역 rules": "Global rules",
  "전역 settings": "Global settings",
  "전역 skills": "Global skills",
  "전역 agents": "Global agents",
  "전역 commands": "Global commands",
  "프로젝트": "Project",
  "프로젝트 로컬": "Project local",
  "프로젝트 rules": "Project rules",
  "프로젝트 settings": "Project settings",
  "프로젝트 skills": "Project skills",
  "프로젝트 agents": "Project agents",
  "프로젝트 commands": "Project commands",
  "하위 폴더": "Subfolder",
  "플러그인": "Plugin",
  "플러그인 skills": "Plugin skills",
  "플러그인 commands": "Plugin commands",
  "이 프로젝트": "This project",
  "홈 디렉터리": "home directory",
  "드라이브 루트": "drive root",
  "상위 폴더 중복": "duplicate of a parent folder",
  "팀 설정": "team settings",
  "개인 설정": "personal settings",
  "전역 설정": "global settings",
  "플러그인 {n}": "Plugin {n}",
  "전역 · {n}": "Global · {n}",
  "플러그인 · {n}": "Plugin · {n}",
  "프로젝트 · {n}": "Project · {n}",
  "프로젝트 · {p} · {f}": "Project · {p} · {f}",
  "프로젝트 .mcp.json · {n}": "Project .mcp.json · {n}",
  "출처 미상": "unknown origin",
  "(출처 없음)": "(no origin)",
  "(이벤트 없음)": "(no event)",
  "(이름 없음)": "(no name)",
  "(제목 없음)": "(no title)",
  "(전체)": "(all)",
  "(명령 없음)": "(no command)",
  "설정 없음": "no config",

  /* ---- 토글 레벨 (LEVELS 값) ---- */
  "on (제한 없음)": "on (no restriction)",
  "name-only (이름만)": "name-only (name only)",
  "user-invocable-only (사용자 호출만)": "user-invocable-only (user calls only)",
  "off (사용 안 함)": "off (disabled)",

  /* ---- 공통 부품 ---- */
  "다시 시도": "Retry",
  "응답을 읽지 못했습니다": "Could not read the response",
  "팀 공유": "Shared",
  "개인": "Personal",
  "지연": "lazy",
  "지연 로드": "lazy load",
  "경로 없음": "path missing",
  "루트만": "root only",
  "일부만": "partial",
  "일부만 스캔": "partially scanned",
  "루트만 · {n}": "root only · {n}",
  "사유 미상": "reason unknown",
  "읽기 실패": "read failed",
  "충돌": "Conflicts",
  "중복": "duplicate",
  "skillOverrides OFF": "skillOverrides OFF",
  "플러그인 OFF": "Plugin OFF",
  "이 프로젝트에서 OFF": "OFF in this project",
  "CLAUDE.md 없음": "no CLAUDE.md",
  "{n} 하위 항목 펼치기": "Expand children of {n}",
  "{n} 하위 항목 접기": "Collapse children of {n}",

  /* ---- 툴바 ---- */
  "파일·프로젝트 검색": "Search files and projects",
  "제목으로 프로젝트 간 비교": "Compare projects by heading",
  "⇄ 비교": "⇄ Compare",
  "이름·설명 검색": "Search name and description",
  "이벤트·매처·명령 검색": "Search event, matcher, command",
  "서버 이름 검색": "Search server name",

  /* ---- 사이드바 본문 ---- */
  "{n} 프로젝트": "{n} projects",
  "{n} 파일": "{n} files",
  "규칙을 볼 프로젝트": "Project to show rules for",
  "파일 사이드바에서 프로젝트를 선택하세요.": "Select a project in the Files sidebar.",
  "경로가 존재하지 않는 프로젝트입니다.": "This project's path no longer exists.",
  "유효 규칙을 불러오지 못했습니다: {e}": "Could not load the effective rules: {e}",
  "불러오는 중…": "Loading…",
  "적용되는 규칙 파일이 없습니다.": "No rule files apply.",
  "전역과 프로젝트에 같은 제목 섹션": "same heading in both global and project",
  "이 프로젝트에서 사용": "Use in this project",
  "{n} — 이 프로젝트에서 사용": "{n} — use in this project",
  "이 프로젝트에서 플러그인 사용": "Use this plugin in this project",
  "{n} — 이 프로젝트에서 플러그인 사용": "{n} — use this plugin in this project",
  "프로젝트 미선택": "no project selected",
  "표시 {n} / 전체 {a}": "Showing {n} of {a}",
  "조건에 맞는 항목이 없습니다.": "Nothing matches the filter.",
  "표시할 훅이 없습니다.": "No hooks to show.",
  "표시할 MCP 서버가 없습니다.": "No MCP servers to show.",

  /* ---- 상태바 · 스캔 ---- */
  "스캔 중": "Scanning",
  "스캔 중…": "Scanning…",
  "재스캔": "Rescan",
  "설정을 다시 스캔": "Scan the configuration again",
  "종료": "Quit",
  "서버 종료": "Shut the server down",
  "스캔 {t}": "Scanned {t}",
  "스캔 -": "Scan -",
  "버전 미확인": "version unknown",
  "오류 {n}건": "{n} errors",
  "편집 중 · {n}": "Editing · {n}",
  "비교: {t} · {n}곳": "Compare: {t} · {n} places",
  "{n} / {a}": "{n} / {a}",
  "{s} · 아래가 위를 덮어씀": "{s} · later entries override earlier ones",
  "토글 저장 → {n}": "Toggles save to → {n}",
  "{f} · {n}줄": "{f} · {n} lines",
  "스캔에 실패했습니다: {e}": "Scan failed: {e}",
  "종료하지 못했습니다: {e}": "Could not shut down: {e}",
  "서버가 종료되었습니다": "The server has shut down",
  "재스캔 후 프로젝트가 사라져 선택을 해제했습니다: {p}":
    "The project disappeared after the rescan, so the selection was cleared: {p}",
  "재스캔 후 파일이 사라졌습니다: {p}": "The file disappeared after the rescan: {p}",

  /* ---- 서버 메시지 접두어 (tMsg) ---- */
  "JSON 파싱 실패": "JSON parse failed",
  "@import 대상이 없습니다": "@import target not found",
  "링크 대상이 없습니다": "Link target not found",
  "frontmatter 필수 키가 없습니다": "Missing required frontmatter keys",
  "최상위가 객체가 아닙니다": "Top level is not an object",
  "CLI 실행 실패": "Could not start the CLI",
  "CLI 통신 실패": "CLI communication failed",
  "CLI 오류": "CLI error",
  "CLI 응답을 해석하지 못했습니다": "Could not interpret the CLI response",
  "로그인이 필요합니다": "Login required",

  /* ---- 에디터 — 탭·경로 줄·원문 ---- */
  "비교: {t}": "Compare: {t}",
  "제목 비교": "Title comparison",
  "열린 파일 없음": "No open files",
  "{n} 닫기": "Close {n}",
  "읽기 전용 (플러그인)": "Read-only (plugin)",
  "편집": "Edit",
  "모두 접기": "Collapse all",
  "모두 펼치기": "Expand all",
  "팀 공유 · git": "Shared · git",
  "비교하지 못했습니다: {t}": "Could not compare: {t}",
  "파일을 불러오지 못했습니다: {p}": "Could not load the file: {p}",
  "왼쪽 목록에서 항목을 선택하세요 · 액티비티 바로 파일/규칙/스킬/훅/MCP 전환":
    "Pick an item in the list on the left · use the activity bar to switch between Files, Rules, Skills, Hooks and MCP",
  "불러오는 중… {p}": "Loading… {p}",
  "열린 파일이 없습니다.": "No file is open.",
  "… {n}줄": "… {n} lines",
  "{n} 접기·펼치기": "Collapse or expand {n}",
  "섹션 접기·펼치기": "Collapse or expand this section",
  "이 섹션 편집": "Edit this section",
  "제목 비교 · {t} · {n}곳": "Title comparison · {t} · {n} places",
  "같은 제목의 섹션이 없습니다.": "No section carries this heading.",
  "{p} — 이 줄로 이동": "{p} — go to this line",

  /* ---- 에디터 — 편집 모드 ---- */
  "문제 없음": "No problems",
  "{rule} · {line}행": "{rule} · line {line}",
  "저장하지 않은 변경이 있습니다. 버릴까요?": "You have unsaved changes. Discard them?",
  "검증": "Validate",
  "저장": "Save",
  "취소": "Cancel",
  "저장하지 않고 규칙 검사만 — JSON 문법, frontmatter name/description, 훅 스크립트·@import·링크 경로 실존, * 매처 중복. error는 저장 차단, warn은 안내":
    "Check the rules without saving — JSON syntax, frontmatter name/description, existence of hook scripts, @import and link targets, duplicate * matchers. Errors block saving; warnings are advisory",
  "검증 후 저장 (백업 생성). error가 있으면 저장되지 않음":
    "Validate, then save (a backup is written). Nothing is saved while there are errors",
  "편집 취소 (수정 내용 버림)": "Cancel editing (your changes are discarded)",
  "수정됨": "Modified",
  "변경 없음": "No changes",
  "섹션 편집 중: {t} (L{a}–L{b})": "Editing section: {t} (L{a}–L{b})",
  "git 추적 파일 — 커밋하면 팀 전체에 적용됨":
    "Tracked by git — committing applies it to the whole team",
  "{p} 편집": "Edit {p}",
  "다시 읽기": "Reload",
  "검증 중…": "Validating…",
  "검증하지 못했습니다: {e}": "Validation failed: {e}",
  "디스크에서 변경됨 — 다시 읽기 후 저장하세요.": "Changed on disk — reload before saving.",
  "섹션 본문이 비어 있습니다 — 섹션 삭제는 지원하지 않습니다.":
    "The section body is empty — deleting a section is not supported.",
  "저장 중…": "Saving…",
  "저장하지 못했습니다: {e}": "Save failed: {e}",
  "저장됨 · 백업 {p}": "Saved · backup {p}",
  "(경로 미상)": "(path unknown)",
  "검증 오류가 있어 저장하지 않았습니다.": "Not saved — there are validation errors.",
  "디스크에서 변경됨 — 다시 읽기 후 저장할 수 있습니다.":
    "Changed on disk — reload, then you can save.",
  "다시 읽는 중…": "Reloading…",
  "다시 읽지 못했습니다: {e}": "Reload failed: {e}",
  "디스크 내용을 다시 읽었습니다. 편집본은 그대로이며, 저장하면 덮어씁니다.":
    "Reloaded the file from disk. Your edits are untouched; saving will overwrite it.",
  "섹션 제목을 디스크에서 찾지 못해 전체 편집으로 전환했습니다 — 원래 줄 범위에 편집본을 넣었으니 확인 후 저장하세요.":
    "The section heading was not found on disk, so this switched to editing the whole file — your text was placed at the original line range; check it before saving.",

  /* ---- 편집 도우미 ---- */
  "Claude에게 수정 지시… (긴 문서는 섹션 편집 권장)":
    "Tell Claude what to change… (for a long document, edit one section)",
  "Claude 수정 지시": "Instruction for Claude",
  "모델": "Model",
  "기본 모델": "Default",
  "요청": "Request",
  "적용": "Apply",
  "버리기": "Discard",
  "요청 중… {n}초": "Requesting… {n}s",
  "제안 ({n}줄 변경)": "Proposal ({n} lines changed)",
  "제안을 본문에 적용했습니다.": "Applied the proposal to the document.",
  "제안을 버렸습니다.": "Discarded the proposal.",
  "수정 지시를 입력하세요.": "Enter an instruction first.",
  "요청하지 못했습니다: {e}": "Request failed: {e}",
  "Claude Code CLI 를 찾지 못했습니다 — 설치·로그인 후 다시 시도":
    "Could not find the Claude Code CLI — install it, log in, and try again",
  "이미 실행 중인 요청이 많습니다": "Too many requests are already running",
  "상태를 확인하지 못했습니다: {e}": "Could not check the status: {e}",
  "취소했습니다.": "Cancelled.",
  "요청이 실패했습니다.": "The request failed.",

  /* ---- 인스펙터 — 토글·경고 ---- */
  "Claude Code 버전 미확인 — 스킬 토글 지원 여부 확인 불가":
    "Claude Code version unknown — cannot tell whether skill toggles are supported",
  "Claude Code 스킬 토글 미지원 버전 — 토글해도 적용되지 않을 수 있음":
    "This Claude Code version does not support skill toggles — toggling may have no effect",
  "settings.local.json (개인, 기본)": "settings.local.json (personal, default)",
  "settings.json (팀 공유)": "settings.json (shared)",
  "토글 저장 대상 파일": "File that toggles are written to",
  "저장 대상": "Save to",
  "토글하지 못했습니다: {e}": "Toggle failed: {e}",
  "요청 실패": "request failed",
  "{n} 사용 범위": "Scope for {n}",
  "{n} — 이 프로젝트에서 사용 (인스펙터)": "{n} — use in this project (inspector)",
  "읽지 못했습니다: {e}": "Could not read it: {e}",

  /* ---- 인스펙터 — 섹션·항목 ---- */
  "스캔 오류": "Scan errors",
  "속성": "Properties",
  "범위": "Scope",
  "출처": "Source",
  "공유": "Sharing",
  "팀 공유 (git 추적)": "Shared (tracked by git)",
  "적재": "Loading",
  "지연 로드 (해당 폴더 작업 시)": "lazy (only while working in that folder)",
  "비교 제목": "Compared heading",
  "매치": "Matches",
  "{n}곳": "{n} places",
  "크기": "Size",
  "수정": "Modified",
  "줄바꿈": "Line endings",
  "있음": "yes",
  "없음": "no",
  "섹션": "Sections",
  "{n}개": "{n}",
  "본문": "Body",
  "불러오지 못함": "could not load",
  "항목": "Item",
  "종류": "Kind",
  "상태": "Status",
  "값 출처": "Value source",
  "기본값": "default",
  "설명 없음": "No description",
  "이 프로젝트에서": "In this project",
  "에이전트는 토글 대상이 아닙니다.": "Agents cannot be toggled.",
  "플러그인 단위 스위치는 스킬 사이드바의 그룹 헤더에서 켜고 끕니다.":
    "Plugin-level switches live in the group headers of the Skills sidebar.",
  "선택 프로젝트 경로 없음 — 토글 불가":
    "The selected project's path is missing — cannot toggle",
  "토글하려면 파일 사이드바에서 프로젝트를 선택하세요":
    "Select a project in the Files sidebar to toggle",

  /* ---- 인스펙터 — 훅·MCP·프로젝트 ---- */
  "이벤트": "Event",
  "매처": "Matcher",
  "명령": "Commands",
  "경고": "Warning",
  "* 매처와 중복 발화": "fires twice alongside the * matcher",
  "출처 파일은 열 수 없습니다 (플러그인)": "The source file cannot be opened (plugin)",
  "명령 없음": "No commands",
  "같은 이벤트의 다른 훅": "Other hooks on the same event",
  "없습니다.": "None.",
  "서버": "Server",
  "전송": "Transport",
  "환경변수": "Env vars",
  "설정": "Config",
  "이름": "Name",
  "경로": "Path",
  "스캔 범위": "Scan coverage",
  "전체": "Full",
  "완결성": "Completeness",
  "예": "yes",
  "아니오": "no",
  "이 프로젝트 토글": "Toggles in this project",
  "스킬 {s} · 플러그인 {p}": "skills {s} · plugins {p}",
  "함께 적용됨": "Applied together",
  "프로젝트를 선택하세요.": "Select a project.",
  "불러오지 못했습니다: {e}": "Could not load it: {e}",
  "  ← 현재": "  ← current",
  " · 지연": " · lazy",
  "불러오지 못했습니다.": "Could not load it.",
  "같은 제목의 섹션이 겹치지 않습니다.": "No heading appears in more than one file.",
  "이 프로젝트의 훅": "Hooks from this project",
  "이 프로젝트에서 등록한 훅이 없습니다.": "This project registers no hooks.",
  "안내": "Note",
  "사이드바에서 항목을 선택하세요.": "Select an item in the sidebar."
};
/* 서버 메시지용 패턴: [정규식(ko), 영문 템플릿]. $1… 로 캡처 치환 */
var MSG_PAT = [
  [/^시간 초과 \((\d+)초\)$/, "Timed out ($1 s)"],
  [/^CLI 응답을 해석하지 못했습니다 \(종료 코드 (-?\d+)\)$/,
   "Could not interpret the CLI response (exit code $1)"],
  [/^(.+?) 훅 명령의 파일이 없습니다: (.+)$/, "$1 hook command file not found: $2"],
  [/^(.+?): `\*` 매처와 구체 매처가 함께 있어 훅이 중복 발화합니다$/,
   "$1: both `*` and a specific matcher — hook fires twice"]
];
function t(s, vars){
  var r = (LANG === "en" && Object.prototype.hasOwnProperty.call(EN, s)) ? EN[s] : s;
  if(vars) for(var k in vars) r = r.split("{"+k+"}").join(String(vars[k]));
  return r;
}
function tMsg(s){                      // 서버가 만든 한국어 메시지 — 접두어/패턴 번역
  if(LANG !== "en" || !s) return s;
  if(Object.prototype.hasOwnProperty.call(EN, s)) return EN[s];
  var i = s.indexOf(": ");
  if(i > 0 && Object.prototype.hasOwnProperty.call(EN, s.slice(0, i))) return EN[s.slice(0, i)] + s.slice(i);
  for(var j = 0; j < MSG_PAT.length; j++){ if(MSG_PAT[j][0].test(s)) return s.replace(MSG_PAT[j][0], MSG_PAT[j][1]); }
  return s;                            // ponytail: 못 맞추면 원문. 서버 메시지가 늘면 여기에 추가
}
function setLang(v){ try { localStorage.setItem("cm.lang", v); } catch(e){} location.reload(); }
