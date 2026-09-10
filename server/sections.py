"""F8 섹션: 헤딩 파서, 충돌 탐지, 제목 비교, 줄 범위 치환."""

import re

from common import _p, read_text
from edit import save

# --- F8 섹션 (헤딩 파서·충돌·비교·범위 치환) --------------------------------

# 줄 시작 `#`{1..6} + 공백 + 제목. 들여쓴 `#`는 헤딩이 아니다.
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
# 펜스는 들여쓰기 0~3칸 + ``` 또는 ~~~ 이상
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")

# ponytail: setext 헤딩(`===`/`---` 밑줄)과 들여쓴 코드블록은 인식하지 않는다. 필요 시 추가.


def _logical_lines(text: str) -> list:
    """CRLF 정규화 후 논리 줄. 줄 범위 규약의 유일한 기준."""
    return (text or "").replace("\r\n", "\n").split("\n")


def _headings(lines: list) -> list:
    """[(index, level, title)] — 펜스 코드블록 안은 건너뛴다."""
    out, fence = [], None  # fence: (문자, 길이)
    for i, line in enumerate(lines):
        m = _FENCE.match(line)
        if m:
            tok = m.group(1)
            if fence is None:
                fence = (tok[0], len(tok))
                continue
            # 닫는 펜스: 같은 문자·같은 길이 이상·그 문자 외에는 없는 줄
            if tok[0] == fence[0] and len(tok) >= fence[1] and set(line.strip()) == {tok[0]}:
                fence = None
            continue
        if fence is not None:  # 미닫힘 펜스면 파일 끝까지 코드로 본다
            continue
        h = _HEADING.match(line)
        if h:
            out.append((i, len(h.group(1)), h.group(2).strip().rstrip("#").strip()))
    return out


def parse_sections(text: str) -> list:
    """[{"level","title","start","end"}] 문서 순. start 포함·end 제외의 0-based 논리 줄.

    섹션은 헤딩 줄부터 자기 레벨 이하(≤)의 다음 헤딩 직전까지.
    첫 헤딩 앞에 내용이 있으면 `level:0, title:""` 전문(preamble) 섹션이 앞에 붙는다.
    """
    lines = _logical_lines(text)
    heads = _headings(lines)
    if not heads and not (text or "").strip():
        return []
    out = []
    first = heads[0][0] if heads else len(lines)
    if first > 0:
        out.append({"level": 0, "title": "", "start": 0, "end": first})
    for n, (i, level, title) in enumerate(heads):
        end = len(lines)
        for j, lvl, _t in heads[n + 1:]:
            if lvl <= level:
                end = j
                break
        out.append({"level": level, "title": title, "start": i, "end": end})
    return out


def section_conflicts(files: list) -> list:
    """같은 제목 섹션이 서로 다른 파일에 있으면 충돌 (V5, warn).

    files: `[{"path", "scope", "sections": [...]}]` (effective_rules 순서).
    반환 `[{"title", "where": [{"path","scope","start","end"}]}]`.
    같은 파일 안의 중복과 preamble(level 0)·빈 제목은 충돌이 아니다.
    """
    by: dict = {}
    for f in files or []:
        for s in f.get("sections") or []:
            if not s.get("level") or not s.get("title"):
                continue
            by.setdefault(s["title"], []).append(
                {"path": f.get("path"), "scope": f.get("scope"),
                 "start": s["start"], "end": s["end"]})
    return [{"title": t, "where": w} for t, w in by.items()
            if len({e["path"] for e in w}) > 1]


def _compare_targets(scan: dict) -> list:
    """[(project 이름|None, path, scope)] — 전역 → 프로젝트 순, effective_rules와 같은 scope 값."""
    out = []
    g = (scan or {}).get("global") or {}
    if g.get("claude_md"):
        out.append((None, g["claude_md"]["path"], "global"))
    for e in g.get("rules") or []:
        out.append((None, e["path"], "global-rules"))
    for p in (scan or {}).get("projects") or []:
        name = p.get("name") or p.get("path")
        for e in p.get("claude_md") or []:
            if e.get("scope") == "subdir":
                scope = "subdir"
            else:
                scope = "project-local" if e.get("name") == "CLAUDE.local.md" else "project"
            out.append((name, e["path"], scope))
        for e in p.get("rules") or []:
            out.append((name, e["path"], "project-rules"))
    return out


def compare_sections(scan: dict, title: str) -> list:
    """스캔 결과 전체에서 제목이 완전히 일치하는 섹션을 모은다 (대소문자 구분).

    반환 `[{"project"(전역이면 None), "path", "scope", "start", "end", "text"}]`.
    읽기 실패는 건너뛴다(read_text가 errors()에 남긴다).
    """
    t = (title or "").strip()
    if not t:
        return []
    out = []
    for project, path, scope in _compare_targets(scan):
        meta = read_text(path)
        if not meta or "text" not in meta:
            continue
        lines = _logical_lines(meta["text"])
        for s in parse_sections(meta["text"]):
            if s["level"] and s["title"] == t:
                out.append({"project": project, "path": path, "scope": scope,
                            "start": s["start"], "end": s["end"],
                            "text": "\n".join(lines[s["start"]:s["end"]])})
    return out


def replace_range(path, start: int, end: int, new_text: str, expected_mtime=None) -> dict:
    """`lines[start:end]`를 new_text로 갈아끼우고 save()에 전문을 넘긴다.

    - 범위가 `0 <= start <= end <= 줄 수`가 아니면 `{"bad_range": True}` (파일은 그대로).
    - 나머지 반환은 save()와 같고, 성공하면 `"sections"`가 붙는다.
    - 검증·V7·백업·CRLF/BOM 보존은 전부 save()가 한다.

    # ponytail: new_text가 빈 문자열이면 삭제가 아니라 빈 줄 1개가 된다. 섹션 삭제는 범위 밖 —
    # 엔드포인트가 빈 문자열을 400으로 거른다.
    """
    meta = read_text(path)
    if meta is None:
        raise FileNotFoundError(_p(path))
    if "text" not in meta:
        raise OSError(meta.get("error", "read failed"))
    lines = _logical_lines(meta["text"])
    if not (0 <= start <= end <= len(lines)):
        return {"bad_range": True}
    lines[start:end] = new_text.replace("\r\n", "\n").rstrip("\n").split("\n")
    full = "\n".join(lines)
    r = save(path, full, expected_mtime)
    if "mtime" in r and not r.get("conflict"):  # 쓰기가 실제로 일어났을 때만
        r["sections"] = parse_sections(full)
    return r
