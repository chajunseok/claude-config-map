"""claude-config-map 스캔 로직 (F1, F2). 읽기 전용 — 파일을 쓰지 않는다."""

import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("config-map")
if not log.handlers:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                        format="%(levelname)s %(name)s %(message)s")

EXCLUDE_DIRS = {"node_modules", ".git", "dist", "build", "target", ".venv",
                "venv", "__pycache__", ".next", ".nuxt", "out", "coverage"}
MD_NAMES = {"CLAUDE.md", "CLAUDE.local.md"}
KIND_DIRS = ("skills", "agents", "commands")


def _p(path) -> str:
    """표시·비교용 경로 문자열. resolve 후 슬래시."""
    return Path(path).resolve().as_posix()


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
    """utf-8-sig로 읽고 원본 줄바꿈·BOM 메타를 함께 반환. 없으면 None."""
    p = Path(path)
    try:
        raw = p.read_bytes()
    except (FileNotFoundError, NotADirectoryError, IsADirectoryError, PermissionError):
        return None
    st = p.stat()
    return {
        "text": raw.decode("utf-8-sig", errors="replace"),
        "crlf": b"\r\n" in raw,
        "bom": raw.startswith(b"\xef\xbb\xbf"),
        "mtime": st.st_mtime,
        "size": st.st_size,
    }


def parse_frontmatter(text: str) -> dict:
    """맨 앞 `---` 블록의 한 줄짜리 `key: value`만 뽑는다.

    # ponytail: YAML 파서 없음. 중첩·리스트·멀티라인 값은 무시한다.
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
        if not sep or not key.strip():
            continue
        out[key.strip()] = val.strip().strip("'\"")
    return {}  # 닫는 `---`가 없으면 frontmatter가 아니다


# ponytail: 디렉터리 개수 상한. `C:/`나 홈처럼 거대한 경로가 프로젝트로 등록돼 있으면
# 제외 목록·깊이 상한만으로는 분 단위가 된다. 초과분은 버리고 truncated로 표시한다.
# 정확도가 필요해지면 프로젝트별 상한을 UI에서 올리는 쪽으로 확장한다.
DIR_BUDGET = 20000


def iter_md(root, names=MD_NAMES, exclude=EXCLUDE_DIRS, max_depth: int = 8,
            budget: int = DIR_BUDGET) -> list:
    """root 아래에서 이름이 names인 파일 경로 목록. 제외 디렉터리는 진입 자체를 막는다."""
    return _walk_md(root, names, exclude, max_depth, budget)[0]


def _walk_md(root, names=MD_NAMES, exclude=EXCLUDE_DIRS, max_depth: int = 8,
             budget: int = DIR_BUDGET):
    """iter_md와 같되 (파일 목록, 상한 초과 여부)를 돌려준다."""
    root = Path(root)
    if not root.is_dir():
        return [], False
    base = len(root.resolve().parts)
    found = []
    seen = 0
    truncated = False
    for dirpath, dirs, files in os.walk(root):
        seen += 1
        if seen > budget:
            truncated = True
            dirs[:] = []
            continue
        if len(Path(dirpath).resolve().parts) - base >= max_depth:
            dirs[:] = []
        else:
            # 점으로 시작하는 디렉터리는 캐시·툴 폴더라 CLAUDE.md가 없다. `.claude`만 예외
            dirs[:] = [d for d in dirs
                       if d not in exclude and (not d.startswith(".") or d == ".claude")]
        for f in files:
            if f in names:
                found.append(Path(dirpath) / f)
    if truncated:
        log.info("scan truncated at %d dirs: %s", budget, _p(root))
    return found, truncated


def _file_entry(path, shared: bool = False, frontmatter: bool = False) -> dict:
    p = Path(path)
    st = p.stat()
    e = {"path": _p(p), "name": p.name, "size": st.st_size,
         "mtime": st.st_mtime, "shared": shared}
    if frontmatter:
        meta = read_text(p)
        fm = parse_frontmatter(meta["text"]) if meta else {}
        e["name_meta"] = fm.get("name")
        e["description"] = fm.get("description")
    return e


def _read_json(path) -> dict | None:
    """JSON 파일 읽기. 없으면 None, 파싱 실패면 `error` 필드만 담은 dict."""
    meta = read_text(path)
    if meta is None:
        return None
    try:
        data = json.loads(meta["text"]) if meta["text"].strip() else {}
    except ValueError as e:
        return {"path": _p(path), "error": str(e)}
    return {"path": _p(path), "data": data, "mtime": meta["mtime"], "size": meta["size"]}


def _scan_kind_dirs(base: Path, shared_set=None) -> dict:
    """{skills,agents,commands} 아래 md 파일을 frontmatter 요약과 함께 모은다."""
    out = {}
    for kind in KIND_DIRS:
        d = base / kind
        items = []
        if d.is_dir():
            for f in sorted(d.rglob("*.md")):
                if any(part in EXCLUDE_DIRS for part in f.parts):
                    continue
                items.append(_file_entry(f, _shared(f, shared_set), frontmatter=True))
        out[kind] = items
    return out


def _shared(path, shared_set) -> bool:
    return bool(shared_set) and _p(path) in shared_set


def scan_global() -> dict:
    h = home()
    c = h / ".claude"
    g = {"root": _p(c), "claude_md": None, "rules": [], "settings": {}}

    md = c / "CLAUDE.md"
    if md.is_file():
        g["claude_md"] = _file_entry(md)

    rules = c / "rules"
    if rules.is_dir():
        g["rules"] = [_file_entry(f) for f in sorted(rules.rglob("*.md"))]

    for name in ("settings.json", "settings.local.json"):
        r = _read_json(c / name)
        if r is not None:
            g["settings"][name] = r

    g.update(_scan_kind_dirs(c))
    return g


def scan_project(path) -> dict:
    p = Path(path)
    if not p.is_dir():
        return {"path": _p(p), "exists": False}

    shared_set = _git_tracked(p)
    proj = {"path": _p(p), "exists": True, "name": p.name,
            "git": shared_set is not None, "rules": [], "settings": {}, "imports": []}

    md_paths, proj["truncated"] = _walk_md(p)
    files = [_file_entry(f, _shared(f, shared_set)) for f in md_paths]
    root_posix = _p(p)
    for e in files:
        rel = e["path"][len(root_posix):].lstrip("/")
        e["scope"] = "root" if "/" not in rel else "subdir"
    proj["claude_md"] = sorted(files, key=lambda e: e["path"])

    rules = p / ".claude" / "rules"
    if rules.is_dir():
        proj["rules"] = [_file_entry(f, _shared(f, shared_set))
                         for f in sorted(rules.rglob("*.md"))]

    for name in ("settings.json", "settings.local.json"):
        r = _read_json(p / ".claude" / name)
        if r is not None:
            r["shared"] = _shared(p / ".claude" / name, shared_set)
            proj["settings"][name] = r

    proj.update(_scan_kind_dirs(p / ".claude", shared_set))

    mcp = _read_json(p / ".mcp.json")
    proj["mcp_json"] = mcp

    for e in proj["claude_md"]:
        if e["scope"] == "root":
            proj["imports"] += _imports(e["path"], p)
    return proj


def _imports(md_path, project_root: Path) -> list:
    """CLAUDE.md 본문의 `@경로` import 1단계. 실존 여부만 기록.

    # ponytail: 줄 시작 `@` 토큰만 본다. 중첩 import는 따라가지 않는다 (PRD S5).
    """
    meta = read_text(md_path)
    if not meta:
        return []
    out = []
    for line in meta["text"].splitlines():
        s = line.strip()
        if not s.startswith("@") or len(s) < 2:
            continue
        token = s[1:].split()[0]
        target = Path(os.path.expanduser(token))
        if not target.is_absolute():
            target = project_root / token
        out.append({"from": _p(md_path), "raw": token,
                    "path": _p(target), "exists": target.exists()})
    return out


def _git_tracked(root: Path) -> set | None:
    """git 추적 파일 절대경로 집합. git이 없거나 실패·타임아웃이면 None."""
    try:
        r = subprocess.run(["git", "-C", str(root), "ls-files"],
                           capture_output=True, text=True, timeout=2,
                           encoding="utf-8", errors="replace")
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    return {_p(root / line) for line in r.stdout.splitlines() if line.strip()}


def scan_projects() -> list:
    data = _read_json(home() / ".claude.json")
    if not data or "data" not in data:
        return []
    projects = data["data"].get("projects")
    if not isinstance(projects, dict):
        return []
    return [scan_project(path) for path in projects]


def scan_plugins() -> list:
    h = home()
    installed = _read_json(h / ".claude" / "plugins" / "installed_plugins.json")
    if not installed or "data" not in installed:
        return []
    out = []
    for key, entries in (installed["data"].get("plugins") or {}).items():
        for entry in entries if isinstance(entries, list) else [entries]:
            out.append(_scan_plugin(key, entry))
    return out


def _scan_plugin(key: str, entry: dict) -> dict:
    root = Path(entry.get("installPath", ""))
    p = {"key": key, "version": entry.get("version"), "scope": entry.get("scope"),
         "path": _p(root) if str(root) else None, "exists": root.is_dir(),
         "manifest": None, "skills": [], "commands": [], "hooks": None,
         "mcp_servers": {}}
    if not p["exists"]:
        return p

    manifest = _read_json(root / ".claude-plugin" / "plugin.json")
    p["manifest"] = manifest
    data = (manifest or {}).get("data") or {}
    p["name"] = data.get("name") or key.split("@")[0]
    p["description"] = data.get("description")
    p["mcp_servers"] = data.get("mcpServers") or {}

    skills = root / "skills"
    if skills.is_dir():
        for sk in sorted(skills.iterdir()):
            f = sk / "SKILL.md"
            if f.is_file():
                p["skills"].append(_file_entry(f, frontmatter=True))

    commands = root / "commands"
    if commands.is_dir():
        p["commands"] = [_file_entry(f) for f in sorted(commands.rglob("*")) if f.is_file()]

    hooks_ref = data.get("hooks")
    if isinstance(hooks_ref, str):
        hf = _read_json(root / hooks_ref.lstrip("./"))
        if hf is not None:
            hd = hf.get("data")
            # 플러그인 훅 파일은 {"hooks": {...}} 로 감싸는 형태와 평면 형태가 모두 있다
            hf["hooks"] = hd.get("hooks", hd) if isinstance(hd, dict) else None
            p["hooks"] = hf
    elif isinstance(hooks_ref, dict):
        p["hooks"] = {"path": p["path"], "hooks": hooks_ref}
    return p


def scan_mcp() -> list:
    data = _read_json(home() / ".claude.json")
    if not data or "data" not in data:
        return []
    d = data["data"]
    out = []
    for name, cfg in (d.get("mcpServers") or {}).items():
        out.append({"name": name, "source": "global", "config": cfg})
    for path, pd in (d.get("projects") or {}).items():
        if not isinstance(pd, dict):
            continue
        for name, cfg in (pd.get("mcpServers") or {}).items():
            out.append({"name": name, "source": f"project:{_p(path)}", "config": cfg})
    return out


def effective_rules(project: dict) -> list:
    """F2 순서로 적용되는 규칙 파일 목록. project는 scan_project 결과."""
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
    try:
        r = subprocess.run(["claude", "--version"], capture_output=True, text=True,
                           timeout=3, encoding="utf-8", errors="replace")
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() or None if r.returncode == 0 else None


def scan() -> dict:
    h = home()
    log.info("scanning %s", _p(h))
    g = scan_global()
    projects = scan_projects()
    plugins = scan_plugins()

    sources = []
    for name, s in g["settings"].items():
        if "data" in s:
            sources.append({"source": "global", "hooks": s["data"].get("hooks")})
    for proj in projects:
        for name, s in (proj.get("settings") or {}).items():
            if "data" in s:
                sources.append({"source": f"project:{proj['path']}",
                                "hooks": s["data"].get("hooks")})
    for pl in plugins:
        if pl.get("hooks"):
            sources.append({"source": f"plugin:{pl.get('name', pl['key'])}",
                            "hooks": pl["hooks"].get("hooks")})

    return {
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "home": _p(h),
        "claude_version": _claude_version(),
        "global": g,
        "projects": projects,
        "plugins": plugins,
        "mcp": scan_mcp(),
        "hooks": hook_flows(sources),
    }
