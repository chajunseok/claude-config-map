"""claude-config-map 스캔 로직 (F1, F2). 읽기 전용 — 파일을 쓰지 않는다."""

import concurrent.futures
import json
import logging
import os
import shutil
import subprocess
import sys
import threading
from datetime import datetime, timezone
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

# ponytail: 스캔 공개 함수 전체를 감싸는 단일 전역 락. 동시 스캔은 직렬화된다.
# RLock인 이유: scan()이 잡은 채로 scan_global/scan_projects/... 를 다시 부른다.
# 병렬 스캔 처리량이 필요해지면 _errors를 인자로 넘기고 락을 없앤다.
_SCAN_LOCK = threading.RLock()

_UNSET = object()


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


# ponytail: 디렉터리 개수 상한. 거대 경로는 coverage=root-only로 먼저 걸러지므로
# 이 예산은 남은 정상 프로젝트에 대한 안전망이다. 초과하면 즉시 순회를 끊는다.
DIR_BUDGET = 20000


def iter_md(root, names=MD_NAMES, exclude=EXCLUDE_DIRS, max_depth: int = 8,
            budget: int | None = None) -> list:
    """root 아래에서 이름이 names인 파일 경로 목록. 제외 디렉터리는 진입 자체를 막는다."""
    return _walk_md(root, names, exclude, max_depth, budget)[0]


def _walk_md(root, names=MD_NAMES, exclude=EXCLUDE_DIRS, max_depth: int = 8,
             budget: int | None = None):
    """iter_md와 같되 (파일 목록, 상한 초과 여부, 접근 실패 여부)를 돌려준다."""
    if budget is None:
        budget = DIR_BUDGET
    root = _expand(root)
    if not root.is_dir():
        return [], False, False
    root_str = str(root.resolve())
    found = []
    seen = 0
    truncated = False
    incomplete = False

    def on_error(e):
        # os.walk의 onerror는 메인 스레드에서 동기 호출되므로 _err()를 그대로 쓴다
        nonlocal incomplete
        incomplete = True
        _err(getattr(e, "filename", None) or root_str, f"walk failed: {e}")

    for dirpath, dirs, files in os.walk(root_str, onerror=on_error):
        seen += 1
        if seen > budget:
            truncated = True
            break
        if dirpath[len(root_str):].count(os.sep) >= max_depth:
            dirs[:] = []
        else:
            dirs[:] = [d for d in dirs if d not in exclude]
        for f in files:
            if f in names:
                found.append(Path(dirpath) / f)
    if truncated:
        log.info("scan truncated at %d dirs: %s", budget, root_str)
    return found, truncated, incomplete


def _file_entry(path, shared: bool = False, frontmatter: bool = False) -> dict | None:
    p = Path(path)
    try:
        st = p.stat()
    except FileNotFoundError:  # 스캔 도중 사라진 파일은 결과에서 뺀다
        return None
    e = {"path": _p(p), "name": p.name, "size": st.st_size,
         "mtime": st.st_mtime, "shared": shared}
    if frontmatter:
        meta = read_text(p)
        fm = parse_frontmatter(meta["text"]) if meta and "text" in meta else {}
        e["name_meta"] = fm.get("name")
        e["description"] = fm.get("description")
    return e


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


def _scan_kind_dirs(base: Path, shared_set=None) -> dict:
    """{skills,agents,commands} 아래 md 파일을 frontmatter 요약과 함께 모은다."""
    out = {}
    for kind in KIND_DIRS:
        d = base / kind
        items = []
        if d.is_dir():
            for f in sorted(d.rglob("*.md")):
                # 제외 판정은 base 기준 상대 경로로만 (절대 경로에 build/ 같은 조상이 있어도 무관)
                if not f.is_file() or any(part in EXCLUDE_DIRS
                                          for part in f.relative_to(d).parts):
                    continue
                e = _file_entry(f, _shared(f, shared_set), frontmatter=True)
                if e is not None:
                    items.append(e)
        out[kind] = items
    return out


def _shared(path, shared_set) -> bool:
    # *.local.* 은 git 추적 여부와 무관하게 개인 설정
    if Path(path).name in LOCAL_NAMES:
        return False
    return bool(shared_set) and _p(path) in shared_set


def scan_global() -> dict:
    with _SCAN_LOCK:  # _err() 접근 직렬화. scan() 안에서는 RLock 재진입으로 통과
        return _scan_global()


def _scan_global() -> dict:
    h = home()
    c = h / ".claude"
    g = {"root": _p(c), "claude_md": None, "rules": [], "settings": {}}

    md = c / "CLAUDE.md"
    if md.is_file():
        g["claude_md"] = _file_entry(md)

    rules = c / "rules"
    if rules.is_dir():
        g["rules"] = [e for f in sorted(rules.rglob("*.md")) if f.is_file()
                      if (e := _file_entry(f)) is not None]

    for name in ("settings.json", "settings.local.json"):
        r = _read_json(c / name)
        if r is not None:
            g["settings"][name] = r

    g.update(_scan_kind_dirs(c))
    return g


def scan_project(path, coverage: str = "full", coverage_reason: str | None = None,
                 tracked=_UNSET) -> dict:
    with _SCAN_LOCK:
        return _scan_project(path, coverage, coverage_reason, tracked)


def _scan_project(path, coverage: str = "full", coverage_reason: str | None = None,
                  tracked=_UNSET) -> dict:
    p = _expand(path)
    if not p.is_dir():
        return {"path": _p(p), "exists": False}

    shared_set = _git_tracked(p) if tracked is _UNSET else tracked
    proj = {"path": _p(p), "exists": True, "name": p.name, "coverage": coverage,
            "git": shared_set is not None, "rules": [], "settings": {}}
    if coverage_reason:
        proj["coverage_reason"] = coverage_reason

    if coverage == "root-only":
        # 다른 프로젝트의 조상·드라이브 루트·홈은 재귀하지 않는다 (C7)
        md_paths = [p / n for n in sorted(MD_NAMES) if (p / n).is_file()]
        proj["truncated"] = False
        proj["incomplete"] = False
    else:
        md_paths, proj["truncated"], proj["incomplete"] = _walk_md(p)

    files = [e for f in md_paths if (e := _file_entry(f, _shared(f, shared_set))) is not None]
    root_posix = _p(p)
    for e in files:
        rel = e["path"][len(root_posix):].lstrip("/")
        e["scope"] = "root" if "/" not in rel else "subdir"
    proj["claude_md"] = sorted(files, key=lambda e: e["path"])

    rules = p / ".claude" / "rules"
    if rules.is_dir():
        proj["rules"] = [e for f in sorted(rules.rglob("*.md")) if f.is_file()
                         if (e := _file_entry(f, _shared(f, shared_set))) is not None]

    for name in ("settings.json", "settings.local.json"):
        r = _read_json(p / ".claude" / name)
        if r is not None:
            r["shared"] = _shared(p / ".claude" / name, shared_set)
            proj["settings"][name] = r

    proj.update(_scan_kind_dirs(p / ".claude", shared_set))

    mcp = _read_json(p / ".mcp.json")
    proj["mcp_json"] = mcp

    for e in proj["claude_md"]:
        e["imports"] = _imports(e["path"])
    return proj


def _imports(md_path) -> list:
    """CLAUDE.md 본문의 `@경로` import 1단계. 실존 여부만 기록.

    상대 경로는 그 CLAUDE.md의 부모 디렉터리 기준으로 해석한다.

    # ponytail: 줄 시작 `@` 토큰만 본다. 중첩 import는 따라가지 않는다 (PRD S5).
    """
    meta = read_text(md_path)
    if not meta or "text" not in meta:
        return []
    out = []
    for line in meta["text"].splitlines():
        s = line.strip()
        if not s.startswith("@") or len(s) < 2:
            continue
        token = s[1:].split()[0]
        target = _expand(token)
        if not target.is_absolute():
            target = _expand(md_path).parent / token
        out.append({"from": _p(md_path), "raw": token,
                    "path": _p(target), "exists": target.exists()})
    return out


def _git_tracked(root: Path) -> set | None:
    """git 추적 파일 절대경로 집합. git이 없거나 실패·타임아웃이면 None."""
    try:
        r = subprocess.run(["git", "-C", str(root), "ls-files", "-z"],
                           capture_output=True, text=True, timeout=2,
                           encoding="utf-8", errors="replace")
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    # 파일마다 resolve하면 수천 번의 stat이 된다. root만 한 번 풀고 문자열로 붙인다.
    base = _p(root).rstrip("/")
    # -z: core.quotepath 인용을 피하려면 NUL 구분이 필수 (비ASCII 경로)
    return {f"{base}/{n}" for n in r.stdout.split("\0") if n.strip()}


def _coverage_of(key: str, all_keys: set, home_key: str):
    """거대 루트 판정. (coverage, reason)."""
    if key == home_key:
        return "root-only", "home"
    anchor = Path(key).anchor.replace("\\", "/")
    if anchor and anchor.rstrip("/") == key.rstrip("/"):
        return "root-only", "drive-root"
    prefix = key.rstrip("/") + "/"
    if any(other != key and other.startswith(prefix) for other in all_keys):
        return "root-only", "ancestor"
    return "full", None


def scan_projects(cfg=None) -> list:
    with _SCAN_LOCK:  # _as_dict/_err를 부르므로 여기도 잠금 안이어야 한다
        return _scan_projects(cfg)


def _scan_projects(cfg=None) -> list:
    if cfg is None:
        cfg = _read_json(home() / ".claude.json")
    if not cfg or "data" not in cfg:
        return []
    root = _as_dict(cfg["data"], cfg.get("path"), "root")
    projects = _as_dict(root.get("projects"), cfg.get("path"), "projects") if root else None
    if not projects:
        return []
    keys = {raw: _p(raw) for raw in projects}
    all_keys = set(keys.values())
    home_key = _p(home())
    plan = []
    for raw, key in keys.items():
        cov, reason = _coverage_of(key, all_keys, home_key)
        plan.append((_expand(raw), cov, reason))

    # ponytail: git ls-files가 스캔 시간의 대부분(순차 47회 = 15초). subprocess뿐이라
    # 스레드로 겹쳐 돌린다. 워커 8개 고정 — 프로젝트 수가 수백이 되면 그때 조정한다.
    roots = [root for root, _, _ in plan if root.is_dir()]
    tracked = {}
    if roots:
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
            for root, res in zip(roots, ex.map(_git_tracked, roots)):
                tracked[root] = res

    return [scan_project(r, cov, reason, tracked.get(r))
            for r, cov, reason in plan]


def scan_plugins() -> list:
    with _SCAN_LOCK:
        return _scan_plugins()


def _scan_plugins() -> list:
    h = home()
    installed = _read_json(h / ".claude" / "plugins" / "installed_plugins.json")
    if not installed or "data" not in installed:
        return []
    path = installed.get("path")
    data = _as_dict(installed["data"], path, "root")
    plugins = _as_dict(data.get("plugins"), path, "plugins") if data else None
    out = []
    for key, entries in (plugins or {}).items():
        for entry in entries if isinstance(entries, list) else [entries]:
            e = _as_dict(entry, path, f"plugins.{key}")
            if e is None:
                continue
            out.append(_scan_plugin(key, e))
    return out


def _scan_plugin(key: str, entry: dict) -> dict:
    install = (entry or {}).get("installPath") or ""
    if not str(install).strip():
        return {"name": key, "exists": False}
    root = _expand(install)
    p = {"key": key, "version": entry.get("version"), "scope": entry.get("scope"),
         "path": _p(root), "exists": root.is_dir(),
         "manifest": None, "skills": [], "commands": [], "hooks": None,
         "mcp_servers": {}}
    if not p["exists"]:
        return p

    manifest = _read_json(root / ".claude-plugin" / "plugin.json")
    p["manifest"] = manifest
    mpath = (manifest or {}).get("path")
    data = _as_dict((manifest or {}).get("data"), mpath, "plugin.json") or {}
    p["name"] = data.get("name") or key.split("@")[0]
    p["description"] = data.get("description")
    p["mcp_servers"] = _as_dict(data.get("mcpServers"), mpath, "mcpServers") or {}

    skills = root / "skills"
    if skills.is_dir():
        for sk in sorted(skills.iterdir()):
            f = sk / "SKILL.md"
            if f.is_file():
                e = _file_entry(f, frontmatter=True)
                if e is not None:
                    p["skills"].append(e)

    commands = root / "commands"
    if commands.is_dir():
        p["commands"] = [e for f in sorted(commands.rglob("*")) if f.is_file()
                         if (e := _file_entry(f, frontmatter=(f.suffix == ".md"))) is not None]

    hooks_ref = data.get("hooks")
    if isinstance(hooks_ref, str):
        hf = _read_json(root / hooks_ref)
        if hf is not None:
            hd = hf.get("data")
            # 플러그인 훅 파일은 {"hooks": {...}} 로 감싸는 형태와 평면 형태가 모두 있다
            hf["hooks"] = hd.get("hooks", hd) if isinstance(hd, dict) else None
            p["hooks"] = hf
    elif isinstance(hooks_ref, dict):
        p["hooks"] = {"path": p["path"], "hooks": hooks_ref}
    return p


def scan_mcp(cfg=None) -> list:
    with _SCAN_LOCK:
        return _scan_mcp(cfg)


def _scan_mcp(cfg=None) -> list:
    if cfg is None:
        cfg = _read_json(home() / ".claude.json")
    if not cfg or "data" not in cfg:
        return []
    cpath = cfg.get("path")
    d = _as_dict(cfg["data"], cpath, "root")
    if d is None:
        return []
    out = []
    for name, cfgv in (_as_dict(d.get("mcpServers"), cpath, "mcpServers") or {}).items():
        out.append({"name": name, "source": "global", "config": cfgv})
    for path, pd in (_as_dict(d.get("projects"), cpath, "projects") or {}).items():
        pd = _as_dict(pd, cpath, f"projects.{path}")
        if pd is None:
            continue
        for name, cfgv in (_as_dict(pd.get("mcpServers"), cpath,
                                    f"projects.{path}.mcpServers") or {}).items():
            out.append({"name": name, "source": f"project:{_p(path)}", "config": cfgv})
    return out


def effective_rules(project: dict) -> list:
    """F2 순서로 적용되는 규칙 파일 목록. project는 scan_project 결과."""
    with _SCAN_LOCK:
        return _effective_rules(project)


def _effective_rules(project: dict) -> list:
    g = scan_global()
    out = []

    def add(entry, scope, lazy=False):
        out.append({"path": entry["path"], "scope": scope, "lazy": lazy,
                    "shared": entry.get("shared", False)})

    if g["claude_md"]:
        add(g["claude_md"], "global")
    for e in g["rules"]:
        add(e, "global-rules")
    if not project.get("exists"):
        return out

    root = [e for e in project.get("claude_md", []) if e["scope"] == "root"]
    for e in root:
        if e["name"] == "CLAUDE.md":
            add(e, "project")
    for e in root:
        if e["name"] == "CLAUDE.local.md":
            add(e, "project-local")
    for e in project.get("rules", []):
        add(e, "project-rules")
    for e in project.get("claude_md", []):
        if e["scope"] == "subdir":
            add(e, "subdir", lazy=True)
    return out


def hook_flows(sources: list) -> list:
    """[{source, hooks}] → 이벤트별 평탄 목록. 형식이 다르면 조용히 건너뛴다."""
    flows = []
    for src in sources or []:
        hooks = (src or {}).get("hooks")
        if not isinstance(hooks, dict):
            continue
        for event, groups in hooks.items():
            if not isinstance(groups, list):
                continue
            for group in groups:
                if not isinstance(group, dict):
                    continue
                cmds = [h.get("command") for h in group.get("hooks") or []
                        if isinstance(h, dict) and h.get("command")]
                if not cmds:
                    continue
                flows.append({"event": event, "matcher": group.get("matcher") or "*",
                              "commands": cmds, "source": src.get("source", "unknown")})

    # V6: 같은 이벤트에 `*`와 구체 매처가 공존하면 중복 발화
    for event in {f["event"] for f in flows}:
        same = [f for f in flows if f["event"] == event]
        matchers = {f["matcher"] for f in same}
        if "*" in matchers and len(matchers) > 1:
            for f in same:
                f["warn"] = "duplicate-star"
    return flows


def _claude_version() -> str | None:
    # Windows npm 설치본은 claude.cmd라 ["claude", ...]가 FileNotFoundError (S1)
    exe = shutil.which("claude")
    if not exe:
        return None
    try:
        r = subprocess.run([exe, "--version"], capture_output=True, text=True,
                           timeout=3, encoding="utf-8", errors="replace")
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() or None if r.returncode == 0 else None


def scan() -> dict:
    with _SCAN_LOCK:
        return _scan()


def _scan() -> dict:
    _errors.clear()
    h = home()
    log.info("scanning %s", _p(h))
    cfg = _read_json(h / ".claude.json")  # projects·mcp가 같은 파일을 공유 (C1)
    g = scan_global()
    projects = scan_projects(cfg)
    plugins = scan_plugins()
    mcp = scan_mcp(cfg)

    sources = []
    for name, s in g["settings"].items():
        if "data" in s:
            sources.append({"source": f"global:{name}", "hooks": s["data"].get("hooks")})
    for proj in projects:
        for name, s in (proj.get("settings") or {}).items():
            if "data" in s:
                sources.append({"source": f"project:{proj['path']}:{name}",
                                "hooks": s["data"].get("hooks")})
    for pl in plugins:
        if pl.get("hooks"):
            sources.append({"source": f"plugin:{pl.get('name', pl.get('key'))}",
                            "hooks": pl["hooks"].get("hooks")})

    return {
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "home": _p(h),
        "claude_version": _claude_version(),
        "global": g,
        "projects": projects,
        "plugins": plugins,
        "mcp": mcp,
        "hooks": hook_flows(sources),
        "errors": errors(),
    }
