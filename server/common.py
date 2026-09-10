"""공용 기반: 로거, 상수, 에러 수집, 경로·파일 읽기 (core 분리 전 core.py에서 그대로 이동)."""

import json
import logging
import os
import sys
from pathlib import Path

log = logging.getLogger("config-map")
if not log.handlers:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                        format="%(levelname)s %(name)s %(message)s")

EXCLUDE_DIRS = {"node_modules", ".git", "dist", "build", "target", ".venv",
                "venv", "__pycache__", ".next", ".nuxt", "out", "coverage"}
MD_NAMES = {"CLAUDE.md", "CLAUDE.local.md"}
# git이 추적하더라도 개인 설정으로 간주하는 파일명 (PRD: *.local.* 은 공유가 아니다)
LOCAL_NAMES = {"CLAUDE.local.md", "settings.local.json"}
KIND_DIRS = ("skills", "agents", "commands")
FM_KEYS = frozenset({"name", "description"})
# YAML 블록 스칼라 표시 (`|`, `>` 와 chomping 변형). 이 값이면 본문이 다음 줄에 있다.
BLOCK_SCALARS = frozenset({"|", "|-", "|+", ">", ">-", ">+"})

# ponytail: 파싱·권한 실패를 한 곳에 모으는 모듈 전역. scan()이 시작할 때 비운다.
# scan()이 잠금으로 직렬화되므로 전역 리스트로 충분. 동시 스캔이 필요해지면 인자 전달로 교체.
_errors: list = []

def _err(path, message: str) -> dict:
    """에러를 전역 목록에 남기고 같은 dict를 돌려준다."""
    e = {"path": _p(path), "error": message}
    _errors.append(e)
    log.warning("%s: %s", e["path"], message)
    return dict(e)


def errors() -> list:
    return list(_errors)


def _as_dict(value, path, label: str) -> dict | None:
    """JSON 최상위 타입 가드. dict면 그대로, None이면 조용히 None,
    그 외 타입이면 에러로 남기고 None (스캔은 계속한다)."""
    if value is None or isinstance(value, dict):
        return value
    _err(path, f"{label}: expected object, got {type(value).__name__}")
    return None


def _expand(path) -> Path:
    """선행 `~`를 home() 기준으로 편다. os.path.expanduser는 테스트 홈을 무시한다."""
    s = str(path)
    if s == "~":
        return home()
    if s[:2] in ("~/", "~\\"):
        return home() / s[2:]
    return Path(s)


def _p(path) -> str:
    """표시·비교용 경로 문자열. `~` 확장 → resolve → 슬래시."""
    return _expand(path).resolve().as_posix()


def home() -> Path:
    """Claude Code가 실제로 쓰는 홈. `.claude.json`이 있는 쪽을 택한다 (PRD §11.2)."""
    env = os.environ.get("CLAUDE_CONFIG_MAP_HOME")
    if env:
        return Path(env)
    h = Path.home()
    if (h / ".claude.json").exists():
        return h
    for key in ("USERPROFILE", "HOME"):
        v = os.environ.get(key)
        if v and (Path(v) / ".claude.json").exists():
            return Path(v)
    return h


def read_text(path) -> dict | None:
    """utf-8-sig로 읽고 원본 줄바꿈·BOM 메타를 함께 반환.

    없으면 None, 권한 등으로 못 읽으면 `{"path", "error"}`.
    """
    p = _expand(path)
    try:
        raw = p.read_bytes()
        st = p.stat()
    except (FileNotFoundError, NotADirectoryError, IsADirectoryError):
        return None
    except PermissionError as e:
        return _err(p, f"permission denied: {e}")
    except OSError as e:
        return _err(p, f"read failed: {e}")
    return {
        "text": raw.decode("utf-8-sig", errors="replace"),
        "crlf": b"\r\n" in raw,
        "bom": raw.startswith(b"\xef\xbb\xbf"),
        "mtime": st.st_mtime,
        "size": st.st_size,
    }


def parse_frontmatter(text: str) -> dict:
    """맨 앞 `---` 블록의 한 줄짜리 `key: value` 중 name/description만 뽑는다.

    # ponytail: YAML 파서 없음. 중첩·리스트·멀티라인 값과 그 외 키는 무시한다.
    """
    if not text:
        return {}
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    out = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return out
        if line[:1] in (" ", "\t", "#", "-", ""):
            continue
        key, sep, val = line.partition(":")
        k = key.strip()
        if not sep or k not in FM_KEYS:
            continue
        v = val.strip()
        if v in BLOCK_SCALARS:  # 멀티라인 값은 한 줄 파서 계약 밖 — 키 자체를 건너뛴다
            continue
        out[k] = v.strip("'\"")
    return {}  # 닫는 `---`가 없으면 frontmatter가 아니다


def _read_json(path) -> dict | None:
    """JSON 파일 읽기. 없으면 None, 못 읽거나 파싱 실패면 `error` 필드를 담은 dict."""
    meta = read_text(path)
    if meta is None:
        return None
    if "error" in meta:
        return meta
    try:
        data = json.loads(meta["text"])
    except ValueError as e:
        return _err(path, f"invalid json: {e}")
    return {"path": _p(path), "data": data, "mtime": meta["mtime"], "size": meta["size"]}
