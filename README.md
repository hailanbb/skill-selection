# Skill 精选 (AI Agent Skills Selection)

个人及团队 AI Agent 核心 Skill 技能与 MCP 服务精选库。包含开箱即用、高度确定性的自动化归档、数据提取与知识管理工具。

---

## 📂 仓库结构

```text
skill-selection/
├── README.md                   # 全局技能索引概览（本文件）
├── .gitignore
└── skills/                     # 技能集合目录
    ├── 链接转存obs/             # 智能技术网页归档技能
    │   ├── SKILL.md            # AI Agent 指令手册与净化规则说明
    │   ├── README.md           # 本技能详细安装配置与可选 mcp 引导手册
    │   └── scripts/
    │       └── save_to_obsidian.py # 核心驱动脚本
    ├── sales-daily-report-skill-zh-v1/ # 销售日报整理与钉钉排版优化技能
    │   ├── SKILL.md            # AI Agent 日报收集与钉钉排版指令说明
    │   ├── README.md           # 安装配置、环境自检与工作流说明
    │   ├── scripts/
    │   └── tests/
    └── 转存至github/            # 动态沙盒式开源工具备份技能
        ├── SKILL.md            # AI Agent 首次Onboarding与沙盒转存指令
        └── README.md           # 首次运行交互自建与沙盒工作流指南
```

---

## 🛠️ 精选技能索引 (Skills Directory)

| 技能名称 | 核心功能 | 触发场景 | 详细说明 |
| :--- | :--- | :--- | :--- |
| **链接转存obs** | 智能网页直抓、图片本地化防失效、广告/软文深度语义净化、自动中文归类到待阅收件箱，并自动同步 enquire-mcp 检索缓存。 | 提供 URL 链接并要求转存到 Obsidian 库。 | [👉 详细配置与使用指南](skills/链接转存obs/README.md) |
| **销售日报整理至钉钉** | 自动收集、整理和优化销售团队日报，支持环境自检与引导、请假/离职成员动态配置、人名高亮色彩与格式自定义，并在归档完成后自动将日报追加到本地“日报汇总.md”文件，最后彻底清理临时文件。 | 提交销售人员日报、要求整理日报、查看今日进度或进行配置修改。 | [👉 详细配置与使用指南](skills/sales-daily-report-skill-zh-v1/README.md) |
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
