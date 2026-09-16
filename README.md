<h1 align="center">claude-config-map</h1>

<p align="center">
  <strong>See every Claude Code setting on your machine in one place, and edit it safely.</strong><br />
  <code>CLAUDE.md</code> · rules · <code>settings.json</code> · skills · agents · commands · hooks · plugins · MCP servers
</p>

<p align="center">
  <strong>Language:</strong>
  <a href="README.md">English</a> |
  <a href="README.ko.md">한국어</a>
</p>

<p align="center">
  <a href="https://github.com/chajunseok/claude-config-map/tags"><img src="https://img.shields.io/github/v/tag/chajunseok/claude-config-map?label=version&sort=semver&color=D97757" alt="Version" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="MIT license" /></a>
  <a href="https://docs.anthropic.com/en/docs/claude-code/plugins"><img src="https://img.shields.io/badge/Claude%20Code-plugin-D97757?logo=anthropic&logoColor=white" alt="Claude Code plugin" /></a>
  <a href="https://github.com/chajunseok/claude-config-map/stargazers"><img src="https://img.shields.io/github/stars/chajunseok/claude-config-map?style=flat&logo=github" alt="Stars" /></a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/-Python%203.11+-3776AB?logo=python&logoColor=white" alt="Python 3.11+" />
  <img src="https://img.shields.io/badge/-JavaScript-F7DF1E?logo=javascript&logoColor=black" alt="JavaScript" />
  <img src="https://img.shields.io/badge/-HTML5-E34F26?logo=html5&logoColor=white" alt="HTML5" />
  <img src="https://img.shields.io/badge/-CSS-663399?logo=css&logoColor=white" alt="CSS" />
  <img src="https://img.shields.io/badge/dependencies-0-brightgreen" alt="Zero dependencies" />
</p>

<p align="center">
  <a href="#quick-start">Quick start</a> · <a href="#features">Features</a> · <a href="docs/guide.md">Guide</a>
</p>

<p align="center">
  <img src="docs/img/01-files.png" alt="claude-config-map: explorer, editor and inspector in one browser view" width="100%" />
</p>

## Why

Claude Code reads its configuration from a lot of places: the global `~/.claude/CLAUDE.md` and `rules/`, a `CLAUDE.md` in every project and subfolder, `settings.json` / `settings.local.json`, `.mcp.json`, skill, agent and command folders, and whatever your plugins bring along. Once you have a few projects and plugins, simple questions get hard:

- Which `CLAUDE.md` files actually apply in **this** project, and in what order?
- Where did this hook come from, and does it fire twice?
- Is the same section defined globally **and** in the project?
- Which skills and plugins are on right now, and in which settings file?

**claude-config-map** scans all of it and lays it out IDE-style in your browser, with editing, validation, backups and ON/OFF toggles built in.

## Quick start

> [!IMPORTANT]
> Requires **Python 3.11+** on `PATH`. The plugin does not bundle Python.

In a Claude Code session:

```
/plugin marketplace add chajunseok/claude-config-map
/plugin install config-map@claude-config-map
```

Then, in a **new** session:

```
/config-map
```

Your browser opens at `http://127.0.0.1:8765`. That's it.

<details>
<summary>Run without the plugin</summary>

```bash
git clone https://github.com/chajunseok/claude-config-map.git
cd claude-config-map
python server/web_server.py            # --port 9000, --no-browser
```

</details>

## Features

| | |
|---|---|
| **Effective rule chain**: the `CLAUDE.md` files Claude Code reads in a project, in the order they apply, with `⚠ conflict` when the same section title exists in more than one place. | ![Rules view](docs/img/02-rules.png) |
| **Skill & plugin toggles**: switch skills, commands and whole plugins ON/OFF per project. Writes `skillOverrides` / `enabledPlugins` to the personal or team settings file you pick. | ![Skills view](docs/img/03-skills.png) |
| **Hooks at a glance**: every hook from global, project and plugin settings, grouped by session event, with a warning when a `*` matcher makes one fire twice. | ![Hooks view](docs/img/04-hooks.png) |
| **MCP servers by source**: global, per-project `.mcp.json` and plugin servers in one list, with the config JSON of each one. | ![MCP view](docs/img/05-mcp.png) |
| **Safe editing**: validates before saving (frontmatter, JSON, missing hook scripts, broken `@imports`), refuses to overwrite a file changed on disk, keeps 10 backups per file, preserves CRLF/LF and BOM. Edit one section without touching the rest. | ![Edit mode](docs/img/06-edit.png) |
| **Cross-project compare**: put a section with the same title from your global config and every project side by side. | ![Compare tab](docs/img/07-compare.png) |

Also included: an optional **edit assistant** that asks your installed `claude` CLI for a revision and shows it as a diff before applying it, a Korean/English UI, and dark and light themes.

## Safe by design

- **Local only.** Binds to `127.0.0.1`, rejects cross-origin requests, and makes no outbound network calls. No telemetry.
- **Zero dependencies.** Python standard library on the server, vanilla JS in the browser, no build step, no CDN.
- **Read-first.** It writes only what you explicitly save or toggle, and backs it up first. The plugin cache is read-only.
- **Edit assistant is opt-in.** It runs `claude -p` with tools disabled, so the document text goes to Anthropic through your own account only when you use it.

Details: [Security](docs/guide.md#security) · [Files this tool reads and writes](docs/guide.md#files-this-tool-reads-and-writes)

## Requirements

- **Python 3.11+** (not bundled; `/config-map` tells you if it is missing)
- **Claude Code** 2.1.199+ recommended (older versions can still view and edit)
- A recent Chrome, Edge or Firefox
- Claude Code CLI login, only for the edit assistant

Tested on Windows 11. macOS and Linux should work but have not been measured yet. Reports are welcome.

## Documentation

The full [guide](docs/guide.md) covers the layout, each sidebar, validation rules (V1–V7), toggle behavior, the HTTP API, troubleshooting and known limits.

## Contributing

Issues and pull requests are welcome. To start:

```bash
python -m unittest discover -s server/tests
CLAUDE_CONFIG_MAP_HOME=/path/to/fixture-home python server/web_server.py --no-browser --port 8802
```

The second command runs against an isolated home so your real config stays untouched. See [Development](docs/guide.md#development) for the project layout and conventions.

If this tool saves you some digging, a ⭐ helps other Claude Code users find it.

<p align="center">
  <a href="https://www.star-history.com/#chajunseok/claude-config-map&Date">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=chajunseok/claude-config-map&type=Date&theme=dark" />
      <img src="https://api.star-history.com/svg?repos=chajunseok/claude-config-map&type=Date" alt="Star history chart" width="600" />
    </picture>
  </a>
</p>

## License

[MIT](LICENSE) © junseok.cha
