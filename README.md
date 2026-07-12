# Skill 精选 (AI Agent Skills Selection)

个人及团队 AI Agent 核心 Skill 技能与 MCP 服务精选库。包含开箱即用、高度确定性的自动化归档、数据提取与知识管理工具。

---

## 📂 仓库结构

```text
skill-selection/
├── README.md                   # 全局技能索引概览（本文件）
├── .gitignore
└── skills/                     # 技能集合目录
    └── 链接转存obs/             # 智能技术网页归档技能
        ├── SKILL.md            # AI Agent 指令手册与净化规则说明
        ├── README.md           # 本技能详细安装配置与可选 mcp 引导手册
        └── scripts/
            └── save_to_obsidian.py # 核心驱动脚本
```

---

## 🛠️ 精选技能索引 (Skills Directory)

| 技能名称 | 核心功能 | 触发场景 | 详细说明 |
| :--- | :--- | :--- | :--- |
| **链接转存obs** | 智能网页直抓、图片本地化防失效、广告/软文深度语义净化、自动中文归类到待阅收件箱，并自动同步 enquire-mcp 检索缓存。 | 提供 URL 链接并要求转存到 Obsidian 库。 | [👉 详细配置与使用指南](skills/链接转存obs/README.md) |

*(未来新增的 Skill 或 MCP 服务将持续罗列于上表中，并对应放置于 `skills/` 子目录下。)*

---

## ⚙️ 全局安装与使用说明

1. **技能拷贝**：
   从本仓库的 `skills/` 目录下将您需要的技能文件夹，复制到您 AI 客户端的全局配置目录中：
   * **全局技能路径**：`%USERPROFILE%/.gemini/config/skills/` (对于 Gemini/Antigravity 客户端)
   * **项目级路径**：您当前开发项目根目录下的 `.agents/skills/` 目录中。
2. **首次运行引导 (Onboarding)**：
   本仓库的所有技能均支持 **“开箱即用”** 的自检与自愈逻辑。AI 在首次触发技能时，会在后台自动检查并安装 Python 依赖包，并会通过聊天框友好地向您询问与此技能相关的本地路径配置，并在保存后实现永久记忆。
