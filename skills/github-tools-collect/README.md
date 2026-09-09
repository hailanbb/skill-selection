# GitHub 工具收藏 · 通用 Agent 技能

把 GitHub 软件链接整理为中文介绍、安装使用指南、分类索引与版本来源记录；按需要保存固定提交的源码快照。适合文件传输、效率办公、系统维护、媒体处理、开发工具等普通软件收藏。

技能发布在 `skill-selection`；收藏结果写入**你指定的工具仓库**，两者独立。通用包没有预设 GitHub 账号，也不会把内容默认推送给作者。

## 📂 技能结构

```text
github-tools-collect/
├── SKILL.md                       # 跨客户端工作流
├── README.md                      # 本使用说明
├── config.example.json            # 本地目标配置示例，无账号或凭据
├── .gitignore                     # 排除个人配置和缓存
├── agents/openai.yaml             # 可选 Codex 展示信息
├── references/
│   ├── collection-policy.md       # 收录、版本、许可和更新规范
│   └── catalog-format.md          # 目录、字段与首次建库约定
└── scripts/
    ├── catalog.py                 # 只读检查与索引生成
    └── test_catalog.py            # 核验脚本测试
```

## 第一阶段：安装与首次配置

### 按 Agent 能力安装

| 使用方式 | 安装或加载方法 |
| :--- | :--- |
| 支持文件夹技能的 Agent | 整体复制本目录到该客户端文档规定的技能目录，重新加载后检查是否识别 `github-tools-collect` |
| Codex | 复制到 `$CODEX_HOME/skills/github-tools-collect`；未设置 CODEX_HOME 时通常为 `~/.codex/skills/github-tools-collect` |
| 支持读取文件但没有技能机制 | 明确要求 Agent 读取本目录的 SKILL.md，并按需读取 references；无需处理 agents/openai.yaml |
| 只能聊天、无法访问本地文件 | 提供 SKILL.md 和相关规范内容，可生成指南与清单草稿；无法直接保存、验证或发布文件 |

不同客户端的扫描路径和调用语法可能不同，以实际版本文档为准；本技能不依赖统一的 `$技能名` 语法，也不要求专用 MCP。自动选择能力取决于客户端，无法仅靠文件拷贝保证每个客户端自动发现。

### 必要能力

- **阅读来源**：GitHub CLI、GitHub API/连接器或浏览器，任选能完成当前操作的方式。
- **编辑产物**：可读写文件的工作区，或具备文件提交能力的连接器。
- **源码快照**：Git/归档能力、逐文件摘要与来源核验能力；本技能不会自动安装运行环境。
- **脚本校验**：Python 3.10+，仅标准库，没有额外 Python 包依赖。可按平台使用 `python`、`python3` 或 `py -3`，先确认版本。
- **发布**：现有 GitHub 登录及目标仓库权限。无权限时交付本地成果，不索取或保存 Token。

首次告诉 Agent 目标仓库即可，例如 `your-account/tools`。想长期记住时，将 `config.example.json` 复制为本地 `config.json`，把 `target_repository` 改为自己的 `owner/repo`。文件可选，不必为了缺少配置重复提问。不要提交个人配置或凭据。

## 第二阶段：日常使用

以下自然语言可用于不同 Agent；把源链接和目标替换成自己的值：

```text
按 github-tools-collect 技能，将 https://github.com/localsend/localsend 收藏到 your-account/tools。
按 github-tools-collect 技能，更新工具库中的 LocalSend 到最新正式版。
按 github-tools-collect 技能，只检查来源清单、首页索引与源码摘要，不修改文件。
按 github-tools-collect 技能，收藏这个链接，只整理中文指南，不保存源码：<GitHub 链接>。
按 github-tools-collect 技能，准备收藏草稿，暂不推送 GitHub。
```

支持 `$技能名` 的客户端也可以使用 `$github-tools-collect`。明确要求发布到指定仓库时按该范围执行；“准备草稿”不触发发布。新建仓库尚未明确公开或私有时先询问。

### 校验命令

在技能目录运行（目标库路径独立于技能目录）：

```shell
python scripts/catalog.py check /path/to/your-tools
python scripts/catalog.py render /path/to/your-tools
python scripts/test_catalog.py
```

Windows 示例：`py -3 scripts/catalog.py check "D:\我的工具库"`。`check` 只读；`render` 仅更新首页标记内的索引，保留其余正文。

## 验证范围与常见问题

- **重复收藏**：返回已存在条目；明确更新才修改快照。重名来源使用不同 slug。
- **没有 Python**：可进行文档与清单人工核验，须说明未运行自动校验；不能据此声称源码完整性通过。
- **目标库没有规范或脚本**：包内带有规范、数据契约与脚本，不依赖作者的工具库；按契约初始化或适配既有布局。
- **无法推送**：保留本地成果，说明缺失权限或能力；不显示“已发布”。
- **能否证明软件可用**：不能。摘要检查验证文件，软件实测和安全评估是独立工作。

已验证：校验脚本的 8 项测试，以及既有 LocalSend 收藏库的实际摘要与索引检查。工作流按标准文件、命令与能力适配设计；未在每一种第三方 Agent 客户端中做端到端实测。
