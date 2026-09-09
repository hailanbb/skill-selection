# Skill 精选 (AI Agent Skills Selection)

个人及团队 AI Agent 核心 Skill 技能、MCP 服务与 Agent 配置精选库。包含自动化归档、数据提取、知识管理工具，以及按 Agent 区分的行为规范。

---

## 📂 仓库结构

```text
skill-selection/
├── README.md                   # 技能与 Agent 配置索引（本文件）
├── .gitignore
├── agent-configs/              # Agent 配置与行为规范（独立于 Skills）
│   └── codex/                  # OpenAI Codex 专用
│       ├── AGENTS.md           # 全局个人行为规范 v1.2
│       ├── README.md           # 安装、适用范围、验证与回滚说明
│       └── codex-quota-mode/    # Astra high + Luna medium 全局省额度开关
└── skills/                     # 技能集合目录
    ├── obsidian-整理/           # Obsidian 笔记库智能整理与自动归档技能
    │   ├── SKILL.md            # AI Agent 整理加工核心指令
    │   ├── README.md           # 首次运行引导、分层工作流说明
    │   └── references/
    │       └── obsidian_note_categories_template.md # 默认分类体系模板
    ├── 链接转存obs/             # 智能技术网页归档技能
    │   ├── SKILL.md            # AI Agent 指令手册与净化规则说明
    │   ├── README.md           # 本技能详细安装配置与可选 mcp 引导手册
    │   └── scripts/
    │       └── save_to_obsidian.py # 核心驱动脚本
    ├── douyin-xiaohongshu-obsidian-note/ # 抖音/小红书统一转 Obsidian 笔记
    │   ├── SKILL.md            # 双平台分流、取证、保存与清理
    │   ├── README.md           # 详细安装、首次配置与使用指南
    │   ├── agents/             # 可选客户端展示元数据
    │   ├── references/         # 浏览器流程、笔记格式与输入契约
    │   ├── scripts/            # 配置、媒体处理、去重、保存与安全清理
    │   └── tests/              # 中文路径、图像与发布流程测试
    ├── neat-freak/             # 洁癖收尾与项目规范审计技能
    │   ├── SKILL.md            # AI Agent 会话收尾整理与毕业机制指令
    │   └── README.md           # 首次运行引导、WPS 与路径 Clicklink 审计手册
    ├── sales-daily-report-skill-zh-v1/ # 销售日报整理与钉钉排版优化技能
    │   ├── SKILL.md            # AI Agent 日报收集与钉钉排版指令说明
    │   ├── README.md           # 安装配置、环境自检与工作流说明
    │   ├── scripts/
    │   └── tests/
    ├── hk-event-customer-allocation/ # 香港公益义诊活动客户均衡分配技能
    │   ├── SKILL.md            # 核心工作流与交互指令
    │   ├── README.md           # 详细安装、配置、算法与使用指南
    │   ├── agents/             # Agent 展示与调用元数据
    │   ├── references/         # 输入规范与分配方法
    │   ├── scripts/            # 分配、步行路线与 Excel 生成脚本
    │   └── tests/              # 分配引擎自动测试
    └── 转存至github/            # 动态沙盒式开源工具备份技能
        ├── SKILL.md            # AI Agent 首次Onboarding与沙盒转存指令
        └── README.md           # 首次运行交互自建与沙盒工作流指南
```

---

## 🧭 Agent 配置与行为规范 (Agent Configuration)

本类别收录按 Agent 区分的持久行为规范与配置模板，独立于下方的「精选技能索引」。请按适用 Agent 的说明安装。

| 配置名称 | 适用 Agent | 用途 | 文件与说明 |
| :--- | :--- | :--- | :--- |
| **Codex 全局 AGENTS.md · v1.2** | **OpenAI Codex 专用** | 中文协作、自主执行、批准边界、任务完成与 Windows/Unicode 可靠性规范。 | [规则文件](agent-configs/codex/AGENTS.md) · [安装与使用说明](agent-configs/codex/README.md) |
| **Codex 全局省额度开关 · v1.0** | **OpenAI Codex 专用 Skill** | 开启 Astra/high + Luna/medium 按需调度；关闭恢复原配置，保留其他改动。 | [安装与开关说明](agent-configs/codex/codex-quota-mode/README.md) · [技能指令](agent-configs/codex/codex-quota-mode/SKILL.md) |

这是个人配置模板，不是官方预设；其他 Agent 需要单独适配。Codex 安装请使用上方专用说明，不沿用下面的技能拷贝路径。

---

## 🛠️ 精选技能索引 (Skills Directory)

| 技能名称 | 核心功能 | 触发场景 | 详细说明 |
| :--- | :--- | :--- | :--- |
| **obsidian-整理** | 基于 AI 语义深度解析自动提取 Obsidian 笔记 Frontmatter 元数据，根据自定义分类规范自动对笔记进行一级和二级归档，保留原件备份，支持不符合分类标准之文件的拦截与提示。 | 整理笔记、整理收件箱、归档 Obsidian 笔记或进行分类整理。 | [👉 详细配置与使用指南](skills/obsidian-整理/README.md) |
| **链接转存obs** | 智能网页直抓、图片本地化防失效、广告/软文深度语义净化、自动中文归类到待阅收件箱，并自动同步 enquire-mcp 检索缓存。 | 提供 URL 链接并要求转存到 Obsidian 库。 | [👉 详细配置与使用指南](skills/链接转存obs/README.md) |
| **抖音/小红书转笔记** | 一个技能识别抖音单条视频与小红书图文、LIVE、视频链接，提炼为带本地真实图片的 Obsidian Markdown 学习笔记；共用首次路径配置，按平台与来源去重，完成或失败后安全清理视频、音频、转写和候选帧。不采集主页或收藏夹。 | 抖音或小红书转图文笔记、短视频知识提炼、单条链接保存到 Obsidian。 | [👉 详细配置与使用指南](skills/douyin-xiaohongshu-obsidian-note/README.md) |
| **neat-freak** | 自动进行会话收尾整理与脑区物理清理。审计 Windows 路径 clicklinks 规范、WPS 表格排版及 Web UI 设计美学，防止文档规则与代码发生漂移。 | 会话结束收尾、要求同步文档、整理项目、或进行规范审计体检。 | [👉 详细配置与使用指南](skills/neat-freak/README.md) |
| **销售日报整理至钉钉** | 自动收集、整理 and 优化销售团队日报，支持环境自检与引导、请假/离职成员动态配置、人名高亮色彩与格式自定义，并在归档完成后自动将日报追加到本地“日报汇总.md”文件，最后彻底清理临时文件。 | 提交销售人员日报、要求整理日报、查看今日进度或进行配置修改。 | [👉 详细配置与使用指南](skills/sales-daily-report-skill-zh-v1/README.md) |
| **香港活动客户均衡分配** | 按销售小组名单人数、客户类型权重、加权工作量、步行距离与地理聚集度，相对均衡地分配活动附近客户；诊所类客户按 1.5 倍工作量计权，并在确认后生成四页签 Excel。 | 香港公益义诊活动客户分工、销售小组扫街分组、活动附近客户路线规划。 | [👉 详细配置与使用指南](skills/hk-event-customer-allocation/README.md) |
| **转存至github** | 将网络上第三方工具、Skill 或 MCP 的源码及说明，一键克隆、重构并整合保存到个人的 GitHub 统一工具库中。支持源链接中文自识别与智能翻译分流。 | 用户发送需要克隆、备份或收藏的第三方 AI 工具链接并要求保存到 GitHub 时。 | [👉 详细配置与使用指南](skills/转存至github/README.md) |

*(未来新增的 Skill 或 MCP 服务将持续罗列于上表中，并对应放置于 `skills/` 子目录下。)*

---

## ⚙️ 技能安装与使用说明

以下仅适用于 Skills；Codex 全局规则请查看 [Codex 专用安装说明](agent-configs/codex/README.md)。

1. **技能拷贝**：
   从本仓库的 `skills/` 目录下将您需要的技能文件夹，复制到您 AI 客户端的全局配置目录中：
   * **全局技能路径**：`%USERPROFILE%/.gemini/config/skills/` (对于 Gemini/Antigravity 客户端)
   * **项目级路径**：您当前开发项目根目录下的 `.agents/skills/` 目录中。
2. **首次运行引导 (Onboarding)**：
   各技能会按各自说明检查依赖与首次路径配置；是否需要安装依赖、是否能自动安装，以技能文档及当前客户端权限为准。抖音/小红书统一转笔记不会自动更改全局环境，会先询问笔记与图片目录并保存独立的本机配置。

---

## Obsidian 整理技能更新

`obsidian-整理` 现采用安全的两阶段处理：先输出待处理清单与拟移动路径，只有在用户明确确认后才会写入。加工版先写入同目录临时文件，并通过 UTF-8、YAML、字段、别名和正文完整性校验后才提交；原文仅在加工版确认可读取后移动。

Wiki 首页使用原生 Obsidian Markdown 工作台：展示可追溯的资产统计、工作台入口、最近动态与健康状态；不依赖 CSS、主题或第三方插件，缺失数据会明确显示而不会编造。

2026-09-07：新增 [Wiki 内容质量门禁](skills/obsidian-整理/README.md#内容质量门禁2026-09-07) 与 Windows/Linux 回归测试。按原文路径唯一映射核验覆盖，拦截占位摘要、元数据遗漏、解析失败和重复来源；“有页面”不再等同于“编译完成”。只读巡检不写文件，用户确认后才修复并刷新首页、索引和日志。自动检查不替代语义复核和事实核验。

