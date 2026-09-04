# Skill 精选 (AI Agent Skills Selection)

个人及团队 AI Agent 核心 Skill 技能与 MCP 服务精选库。包含开箱即用、高度确定性的自动化归档、数据提取与知识管理工具。

---

## 📂 仓库结构

```text
skill-selection/
├── README.md                   # 全局技能索引概览（本文件）
├── .gitignore
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
    ├── douyin-obsidian-note/   # 抖音视频转 Obsidian 图文学习笔记技能
    │   ├── SKILL.md            # 取证、关键帧筛选、发布与清理工作流
    │   ├── README.md           # 详细安装、首次配置与使用指南
    │   ├── agents/             # Agent 展示与调用元数据
    │   ├── references/         # 笔记格式、取证与关键帧选择规范
    │   └── scripts/            # 配置、抽帧、发布、验证与安全清理脚本
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

## 🛠️ 精选技能索引 (Skills Directory)

| 技能名称 | 核心功能 | 触发场景 | 详细说明 |
| :--- | :--- | :--- | :--- |
| **obsidian-整理** | 基于 AI 语义深度解析自动提取 Obsidian 笔记 Frontmatter 元数据，根据自定义分类规范自动对笔记进行一级和二级归档，保留原件备份，支持不符合分类标准之文件的拦截与提示。 | 整理笔记、整理收件箱、归档 Obsidian 笔记或进行分类整理。 | [👉 详细配置与使用指南](skills/obsidian-整理/README.md) |
| **链接转存obs** | 智能网页直抓、图片本地化防失效、广告/软文深度语义净化、自动中文归类到待阅收件箱，并自动同步 enquire-mcp 检索缓存。 | 提供 URL 链接并要求转存到 Obsidian 库。 | [👉 详细配置与使用指南](skills/链接转存obs/README.md) |
| **抖音转笔记** | 将单条抖音视频、分享文本或本地视频提炼成 Obsidian Markdown 学习笔记，智能选择并本地保存关键画面，自动生成属性、哈希图片名和库内相对链接，完成后安全清理视频、音频、转写及候选帧。 | 抖音转图文笔记、视频保存到 Obsidian、提炼视频知识、制作带关键截图的 Markdown 笔记。 | [👉 详细配置与使用指南](skills/douyin-obsidian-note/README.md) |
| **neat-freak** | 自动进行会话收尾整理与脑区物理清理。审计 Windows 路径 clicklinks 规范、WPS 表格排版及 Web UI 设计美学，防止文档规则与代码发生漂移。 | 会话结束收尾、要求同步文档、整理项目、或进行规范审计体检。 | [👉 详细配置与使用指南](skills/neat-freak/README.md) |
| **销售日报整理至钉钉** | 自动收集、整理 and 优化销售团队日报，支持环境自检与引导、请假/离职成员动态配置、人名高亮色彩与格式自定义，并在归档完成后自动将日报追加到本地“日报汇总.md”文件，最后彻底清理临时文件。 | 提交销售人员日报、要求整理日报、查看今日进度或进行配置修改。 | [👉 详细配置与使用指南](skills/sales-daily-report-skill-zh-v1/README.md) |
| **香港活动客户均衡分配** | 按销售小组名单人数、客户类型权重、加权工作量、步行距离与地理聚集度，相对均衡地分配活动附近客户；诊所类客户按 1.5 倍工作量计权，并在确认后生成四页签 Excel。 | 香港公益义诊活动客户分工、销售小组扫街分组、活动附近客户路线规划。 | [👉 详细配置与使用指南](skills/hk-event-customer-allocation/README.md) |
| **转存至github** | 将网络上第三方工具、Skill 或 MCP 的源码及说明，一键克隆、重构并整合保存到个人的 GitHub 统一工具库中。支持源链接中文自识别与智能翻译分流。 | 用户发送需要克隆、备份或收藏的第三方 AI 工具链接并要求保存到 GitHub 时。 | [👉 详细配置与使用指南](skills/转存至github/README.md) |

*(未来新增的 Skill 或 MCP 服务将持续罗列于上表中，并对应放置于 `skills/` 子目录下。)*

---

## ⚙️ 全局安装与使用说明

1. **技能拷贝**：
   从本仓库的 `skills/` 目录下将您需要的技能文件夹，复制到您 AI 客户端的全局配置目录中：
   * **全局技能路径**：`%USERPROFILE%/.gemini/config/skills/` (对于 Gemini/Antigravity 客户端)
   * **项目级路径**：您当前开发项目根目录下的 `.agents/skills/` 目录中。
2. **首次运行引导 (Onboarding)**：
   本仓库的所有技能均支持 **“开箱即用”** 的自检与自愈逻辑。AI 在首次触发技能时，会在后台自动检查并安装 Python 依赖包，并会通过聊天框友好地向您询问与此技能相关的本地路径配置，并在保存后实现永久记忆。

---

## Obsidian 整理技能更新

`obsidian-整理` 现采用安全的两阶段处理：先输出待处理清单与拟移动路径，只有在用户明确确认后才会写入。加工版先写入同目录临时文件，并通过 UTF-8、YAML、字段、别名和正文完整性校验后才提交；原文仅在加工版确认可读取后移动。

Wiki 首页使用原生 Obsidian Markdown 工作台：展示可追溯的资产统计、工作台入口、最近动态与健康状态；不依赖 CSS、主题或第三方插件，缺失数据会明确显示而不会编造。

