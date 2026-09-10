---
description: Start the config-map server that shows every local Claude config in one browser view
allowed-tools: Bash
disable-model-invocation: true
---

# Config Map

Start a local server that shows this PC's Claude Code configuration (global CLAUDE.md, per-project rules, skills/agents/commands, hooks, plugins, MCP) in one browser view.

## Usage

```bash
# 1. Check the Python candidates in order. Stop at the first success.
python3 --version
python --version
py -3 --version

# 2. Start the server with the Python you found (run it with the Bash tool's run_in_background).
#    If python3 / python succeeded:
"python3" "${CLAUDE_PLUGIN_ROOT}/server/web_server.py"
#    If only py -3 succeeded (`-3` is a separate argument, not part of the executable name):
py -3 "${CLAUDE_PLUGIN_ROOT}/server/web_server.py"
```

## Notes

- The server script path is `${CLAUDE_PLUGIN_ROOT}/server/web_server.py`. If `CLAUDE_PLUGIN_ROOT` is empty, fall back to `~/.claude/plugins/cache/claude-config-map/config-map/*/server/web_server.py` and use the **highest version folder name**.
- `py` takes `-3` as a **separate argument**. Quoting it as one chunk (`"py -3"`) makes the executable name `py -3`, which fails.
- Try the Python executables in this order: `python3` → `python` → `py -3`. For each candidate, run `<candidate> --version` first and confirm the output is **Python 3.11 or newer**, then stop at the first success. (The Windows Store's fake `python` alias is filtered out by this check, because its `--version` either fails or only opens the install window.)
- If no candidate exists or all of them are older than 3.11, **print only the message below and stop.** Do not install anything and do not search additional paths.

  > config-map requires Python 3.11 or newer. Install it from https://www.python.org/downloads/ and run /config-map again in a new terminal.

- Start the server with the Bash tool's `run_in_background`. The URL appears on the first line of stdout, so show that URL to the user as is.
- If a server is already running, the script just opens the existing URL and exits immediately. Show the printed URL in that case too.
- Do not create shell script files (`.sh` / `.ps1`). Commands must work in both Git Bash and PowerShell, so quote paths and do not use `&&` / `||`.
- On Windows `CLAUDE_PLUGIN_ROOT` may be a backslash path. Do not convert it — quote it and pass it through as is.

### Example

```bash
python3 --version
# -> Python 3.12.4  (3.11 or newer, stop here)

"python3" "${CLAUDE_PLUGIN_ROOT}/server/web_server.py"
# -> http://127.0.0.1:8765
```

Show this URL to the user and stop.
