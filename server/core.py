"""파사드: common/scan/edit/sections를 재수출해 기존 `core.X` 참조를 그대로 유지한다.

실제 구현은 common.py(공용), scan.py(F1·F2), edit.py(F4·F5·F7), sections.py(F8)에 있다.
"""

from common import *  # noqa: F401,F403
from scan import *  # noqa: F401,F403
from edit import *  # noqa: F401,F403
from sections import *  # noqa: F401,F403

# star import가 건너뛰는 밑줄 이름 (테스트·내부 호출이 `core._x`로 참조한다)
from common import (  # noqa: F401
    _as_dict, _err, _errors, _expand, _p, _read_json)
from scan import (  # noqa: F401
    _SCAN_LOCK, _UNSET, _claude_version, _coverage_of, _effective_rules, _file_entry,
    _git_tracked, _imports, _imports_of_text, _scan, _scan_global, _scan_kind_dirs,
    _scan_mcp, _scan_plugin, _scan_plugins, _scan_project, _scan_projects, _shared,
    _walk_md)
from edit import (  # noqa: F401
    _REL_LINK, _backup, _command_path, _issue, _md_kind, _settings_base, _v3, _v4, _v6,
    _write_atomic)
from sections import (  # noqa: F401
    _FENCE, _HEADING, _compare_targets, _headings, _logical_lines)
