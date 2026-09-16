<h1 align="center">claude-config-map</h1>

<p align="center">
  <strong>在一个页面中查看本机所有 Claude Code 配置，并安全地修改。</strong><br />
  <code>CLAUDE.md</code> · rules · <code>settings.json</code> · skills · agents · commands · hooks · plugins · MCP 服务器
</p>

<p align="center">
  <strong>Language:</strong>
  <a href="README.md">English</a> |
  <a href="README.ko.md">한국어</a> |
  <a href="README.zh-CN.md">简体中文</a>
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
  <a href="#快速开始">快速开始</a> · <a href="#功能">功能</a> · <a href="docs/guide.md">使用指南（英文）</a>
</p>

<p align="center">
  <img src="docs/img/01-files.png" alt="claude-config-map：资源管理器、编辑器和检查器集中在一个浏览器页面" width="100%" />
</p>

## 为什么需要它

Claude Code 的配置分散在很多地方：全局的 `~/.claude/CLAUDE.md` 和 `rules/`、每个项目及子目录中的 `CLAUDE.md`、`settings.json` / `settings.local.json`、`.mcp.json`、skill / agent / command 目录，以及各个插件带来的内容。项目和插件一多，简单的问题也变得难以回答：

- 在**这个**项目里，实际生效的是哪些 `CLAUDE.md`？顺序是什么？
- 这个 hook 是从哪里来的？会不会被触发两次？
- 同一个章节是否同时定义在全局**和**项目中？
- 现在开启了哪些 skill 和插件？写在哪个配置文件里？

**claude-config-map** 会扫描以上所有内容，在浏览器中以 IDE 风格展示，并内置编辑、校验、备份和开关功能。

## 快速开始

> [!IMPORTANT]
> 需要 `PATH` 中有 **Python 3.11+**。插件不自带 Python。

在 Claude Code 会话中执行：

```
/plugin marketplace add chajunseok/claude-config-map
/plugin install config-map@claude-config-map
```

然后在**新的**会话中执行：

```
/config-map
```

浏览器会打开 `http://127.0.0.1:8765`，就这么简单。

<details>
<summary>不通过插件直接运行</summary>

```bash
git clone https://github.com/chajunseok/claude-config-map.git
cd claude-config-map
python server/web_server.py            # --port 9000, --no-browser
```

</details>

## 功能

| | |
|---|---|
| **生效规则链**：按生效顺序列出 Claude Code 在项目中读取的 `CLAUDE.md`，同一章节标题出现在多处时标记 `⚠ conflict`。 | ![Rules 视图](docs/img/02-rules.png) |
| **Skill 与插件开关**：按项目开启/关闭 skill、command 以及整个插件。将 `skillOverrides` / `enabledPlugins` 写入你选择的个人或团队配置文件。 | ![Skills 视图](docs/img/03-skills.png) |
| **Hooks 一览**：汇总全局、项目和插件中的所有 hook，按会话事件分组；当 `*` matcher 导致重复触发时给出警告。 | ![Hooks 视图](docs/img/04-hooks.png) |
| **按来源查看 MCP 服务器**：全局、项目 `.mcp.json` 和插件中的服务器集中在一个列表，并可查看每个服务器的配置 JSON。 | ![MCP 视图](docs/img/05-mcp.png) |
| **安全编辑**：保存前校验（frontmatter、JSON、缺失的 hook 脚本、失效的 `@import`），拒绝覆盖磁盘上已被修改的文件，每个文件保留 10 份备份，保留 CRLF/LF 与 BOM。可以只修改一个章节而不影响其余内容。 | ![编辑模式](docs/img/06-edit.png) |
| **跨项目对比**：将全局配置和所有项目中标题相同的章节并排显示。 | ![对比标签页](docs/img/07-compare.png) |

另外还有：可选的**编辑助手**（调用本机已安装的 `claude` CLI 生成修改建议，以 diff 形式预览后再应用）、韩文/英文界面、深色与浅色主题。

## 安全设计

- **仅限本地。** 只绑定 `127.0.0.1`，拒绝跨源请求，不发起任何外部网络请求。无遥测。
- **零依赖。** 服务端只用 Python 标准库，浏览器端为原生 JS，无构建步骤，无 CDN。
- **读取优先。** 只写入你明确保存或切换的文件，并在写入前备份。插件缓存为只读。
- **编辑助手为可选功能。** 以禁用工具的方式运行 `claude -p`，只有在你使用时，文档内容才会通过你自己的账号发送给 Anthropic。

详情：[Security](docs/guide.md#security) · [Files this tool reads and writes](docs/guide.md#files-this-tool-reads-and-writes)

## 环境要求

- **Python 3.11+**（不自带；缺失时 `/config-map` 会给出提示）
- **Claude Code** 建议 2.1.199+（更早版本仍可查看和编辑）
- 较新版本的 Chrome、Edge 或 Firefox
- 登录 Claude Code CLI（仅编辑助手需要）

已在 Windows 11 上验证。macOS 和 Linux 理论上可用，但尚未实测。遇到问题请[提交 Issue](https://github.com/chajunseok/claude-config-map/issues)，意见和反馈欢迎发到 [Discussions](https://github.com/chajunseok/claude-config-map/discussions)。

## 文档

完整的[使用指南](docs/guide.md)（英文）涵盖界面布局、各侧边栏、校验规则（V1–V7）、开关行为、HTTP API、故障排查和已知限制。

## 参与贡献

欢迎提交 [Issue](https://github.com/chajunseok/claude-config-map/issues)、在 [Discussions](https://github.com/chajunseok/claude-config-map/discussions) 交流或发起 Pull Request。开始方式：

```bash
python -m unittest discover -s server/tests
CLAUDE_CONFIG_MAP_HOME=/path/to/fixture-home python server/web_server.py --no-browser --port 8802
```

第二条命令会使用隔离的 home 目录运行，不会改动你的真实配置。项目结构和约定请参阅 [Development](docs/guide.md#development)。

如果这个工具帮你省去了翻找配置文件的时间，点个 ⭐ 能帮助更多 Claude Code 用户发现它。

<p align="center">
  <a href="https://www.star-history.com/#chajunseok/claude-config-map&Date">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=chajunseok/claude-config-map&type=Date&theme=dark" />
      <img src="https://api.star-history.com/svg?repos=chajunseok/claude-config-map&type=Date" alt="Star history 图表" width="600" />
    </picture>
  </a>
</p>

## 许可证

[MIT](LICENSE) © junseok.cha
