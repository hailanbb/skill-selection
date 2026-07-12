# Skill 精选 (AI Agent Skills Selection)

个人及团队 AI Agent 核心 Skill 技能精选库。包含开箱即用、高度确定性的自动化归档与知识管理工具，旨在重塑工作流，保护注意力。

---

## 📂 项目结构

```text
skill-selection/
├── README.md
├── .gitignore
└── skills/                     # 技能集合目录
    └── 链接转存obs/             # 微信及网页技术文章智能归档技能
        ├── SKILL.md            # AI Agent 指令手册与净化规则说明
        └── scripts/
            └── save_to_obsidian.py # 核心驱动脚本（依赖自检、直连爬取、图片本地化）
```

---

## 🛠️ 精选技能列表

### 1. 链接转存obs (Save Link to Obsidian)
* **核心功能**：一键智能抓取网页/微信公众号技术文章，通过 AI 语义进行深度净化（去广告与推广软文），自动下载正文全部图片至全局“图片附件”夹实现防失效归档，智能分类写入 Obsidian 待阅收件箱，并自动同步 Enquire-MCP 全文与语义向量检索索引。
* **适用场景**：用户输入网页技术链接并要求归档、收录至 Obsidian 的场景。
* **使用说明**：
  1. 将 `skills/链接转存obs` 文件夹拷贝至您的全局技能配置目录（如 `%USERPROFILE%/.gemini/config/skills/` 或者是项目级的 `.agents/skills/`）中。
  2. 首次运行任意抓取指令时，AI 会在聊天中主动向您询问本地的 Obsidian 库物理路径及图片存放偏好，完成初始化配置。
  3. AI 会自动在后台自检 Python 环境依赖并协助完成安装，实现真正的开箱即用。
