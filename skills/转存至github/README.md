# 转存至 GitHub 技能使用说明 (Save AI Tools to GitHub Guide)

本技能用于实现第三方开源工具、AI 专属技能、MCP 服务的一键克隆与重构整合，并推送到用户个人的 GitHub 收藏仓库中。该技能完全基于临时沙盒化运行，零本地绝对路径依赖。

---

## 🛠️ 第一阶段：首次初始化配置与自检 (Onboarding & Doctor)

当本技能被触发时，AI Agent 必须首先确保远程 GitHub 推送的目标位置已配置就绪。

### 1. 运行自愈配置 (Onboarding)
AI Agent 会在首次运行该技能时，自测当前技能目录下是否存在 `config.json` 配置文件。
* **如果配置不存在**，AI Agent 会执行以下步骤：
  * **自动探测**：在终端运行 `git remote get-url origin`。如果当前所在的工作区已关联远程 Git（例如在 `ai-tools` 项目下），AI 代理会在聊天中自动询问您是否将其作为转存的 GitHub 收藏仓库。
  * **交互询问**：如果未能自动获取关联仓库，或者您选择“否”，AI 代理会在对话框中提出以下问题：
    > **您的远程 GitHub 工具收藏仓库推送地址 (Git URL) 是什么？** (例如：`https://github.com/username/ai-tools.git`)
  * **持久化**：AI 代理将您提供的 URL 链接写入技能目录下的 `config.json` 进行保存，实现一次配置，后续永久免问。

### 2. 授权自检与诊断
在每次执行搬运任务前，AI Agent 会在后台运行自检：
```bash
# 临时消除可能冲突的环境变量，检测 gh 授权
$env:GITHUB_TOKEN=""; gh auth status
```
* 如果您的 GitHub CLI 登录身份失效，AI 代理会主动引导您运行 `gh auth login` 重新完成授权绑定，确保有对目标仓库的 Git Push 权限。

---

## 🚀 第二阶段：核心执行工作流 (Workflow)

当自检通过后，AI Agent 接收到需要转存的项目链接，将在会话临时目录（即 `scratch/` 动态文件夹）下安全开展以下自动化流程：

### 步骤 1：临时双端沙盒克隆
AI Agent 在 `scratch/` 下创建 `temp_source/`（用于源工具）和 `temp_target/`（用于您的个人收藏库）两个临时文件夹，并在后台自动执行克隆：
```bash
git clone <源项目链接> scratch/temp_source
git clone <github_remote_url> scratch/temp_target
```

### 步骤 2：精简源码搬运
在 `scratch/temp_target/tools/` 下为新收录的工具创建专属子目录，自动复制所有源码和配置文件，并排除 `.git`、`.github` 和原始 `README.md`，彻底规避嵌套冲突。

### 步骤 3：源说明中文检测与“两阶段”重塑
在编写新工具的 `README.md` 时，AI 代理将执行智能语言检测分流：
* **如果原项目自带中文说明**：
  * **分支执行**：最小干预，尊重原作。AI 代理将直接采用并整合这些原生的中文说明，保留作者的原生专业词汇，仅对其大纲结构调整为“两阶段自愈与工作流规范”。
* **如果原项目纯英文/无任何自带中文**：
  * **分支执行**：全自动翻译本地化。AI 代理会在后台将英文技术指南、参数列表、自检命令翻译并润色为高质量的简体中文，并按照“两阶段结构”规范进行排版。
  * **排版格式规范**：说明文档统一要求包含“第一阶段环境自检”、“第二阶段核心命令与工作流”，且剔除一切无关的去广告原则等宣称。

### 步骤 4：主索引更新
AI 自动编辑 `scratch/temp_target/README.md`，将新收录的工具行（包括：中文翻译后的核心功能与触发场景、指向 `tools/工具名/README.md` 的相对跳转链接）追加至主索引表格中。

### 步骤 5：提交与远程推送
进入临时沙盒 `scratch/temp_target/` 下执行自动提交与远程推送：
```bash
git add .
git commit -m "Merge source code and restructure README for <工具名>"
$env:GITHUB_TOKEN=""; git push origin main
```

### 步骤 6：物理清理
推送成功后，AI 代理必须立即安全物理清除沙盒中的 `scratch/temp_source` 与 `scratch/temp_target` 临时文件夹，确保您的本地环境不残留任何临时缓存。
