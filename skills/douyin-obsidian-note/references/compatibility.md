# 客户端兼容性

## 兼容基线

本技能遵循开放 Agent Skills 目录格式：技能根目录包含 `SKILL.md`，可选执行文件位于 `scripts/`，按需说明位于 `references/`。核心流程不读取 Codex 专属配置，也不要求客户端识别 `agents/openai.yaml`。

为兼容只接受最小 Frontmatter 的严格客户端，`SKILL.md` 顶部只使用各实现共同支持的 `name` 和 `description`；Python、外部二进制、网络与权限要求写在正文和本文件中。不要为了某个客户端把专属字段加入核心 Frontmatter。

已按以下公开规范设计：

- Agent Skills 规范：`https://agentskills.io/specification`
- Google Antigravity Skills 文档：`https://antigravity.google/docs/skills`
- Google Antigravity Skills 教程：`https://codelabs.developers.google.com/getting-started-with-antigravity-skills`

## 安装位置

| 客户端 | 全局范围 | 项目/工作区范围 |
|---|---|---|
| Antigravity 2.11.0 IDE | `~/.gemini/config/skills/douyin-obsidian-note/` | `<workspace>/.agents/skills/douyin-obsidian-note/` |
| Antigravity CLI | 优先按当前客户端文档使用 `~/.gemini/antigravity-cli/skills/douyin-obsidian-note/` | `<workspace>/.agents/skills/douyin-obsidian-note/`；旧版可兼容 `.agent/skills/` |
| Codex | `~/.codex/skills/douyin-obsidian-note/` | `<workspace>/.agents/skills/douyin-obsidian-note/` |
| 其他 Agent Skills 客户端 | 复制到客户端声明的全局 skills 根目录 | 通常为 `<workspace>/.agents/skills/douyin-obsidian-note/`，以客户端文档为准 |

Windows 中的 `~` 表示当前用户目录，例如 `C:\Users\用户名`。复制整个技能目录，不要只复制 `SKILL.md`。

## 运行能力

客户端需要能够：

1. 读取技能根目录中的相对资源。
2. 执行本地 Python 3.10+ 脚本。
3. 在处理远程链接时允许网络访问。
4. 在实际抽帧时调用 `ffmpeg` 和 `ffprobe`。
5. 在通过链接提取公开元数据时调用 `yt-dlp`。

如果客户端只能读取说明、不能执行本地脚本，它仍可理解工作流，但不能保证配置、发布、校验、哈希命名和安全清理行为一致。

## 命令解析

- 客户端必须从已加载 `SKILL.md` 的位置确定技能根目录，不依赖会话当前目录。
- Windows 可使用 `python` 或 `py -3`；macOS/Linux 通常使用 `python3`。使用哪个启动器由客户端环境决定。
- 向脚本传递绝对路径或由客户端可靠解析的路径。包含中文、空格、`&` 或 `$` 的值必须作为单独参数传递。
- 不把命令再包装进 `powershell -Command "..."`、`sh -c "..."` 或其他嵌套 Shell 字符串。
- `extract_metadata.py --background` 会用当前 Python 解释器直接创建 worker：Windows 使用新进程组和无窗口标志，POSIX 使用新会话；两者都明确设置 `shell=False`。

## 能保证与不能保证的范围

仓库可以验证开放格式、脚本行为、路径传参和 Windows/macOS/Linux 的 Python 兼容性。客户端是否允许网络、后台子进程、读取用户目录或调用外部二进制，仍由其沙箱和授权策略决定；受限时应向用户说明缺少的能力，不能绕过客户端权限。
