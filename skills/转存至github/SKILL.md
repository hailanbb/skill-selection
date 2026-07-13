---
name: 转存至github
description: 用于将互联网上发现的第三方 AI 工具、Skill 或 MCP 服务的源码及文档，一键克隆、精简重构并整合保存到用户的 GitHub 统一收藏仓库（ai-tools）中。
---

# 👁️ 转存第三方 AI 工具至 GitHub 技能使用指南 (Save AI Tools to GitHub)

本技能用于将网络上的第三方开源工具、AI 专属技能、MCP 服务的源代码与文档，一键克隆、重构并整合归档到用户的 GitHub 统一收藏仓库（默认推送至远程的 `ai-tools` 仓库）中。

---

## 🛠️ 第一阶段：首次初始化配置与自检 (Onboarding & Doctor)

当本技能首次被触发时，AI Agent 必须首先确保本技能所绑定的远程 GitHub 收藏仓库地址已配置完毕。

### 1. 首次使用交互配置 (Onboarding)
AI Agent 启动时，必须检查本技能目录（即当前 `SKILL.md` 所在文件夹）下是否存在 `config.json` 文件。
* **如果 `config.json` 不存在**：说明这是首次运行。AI Agent 应当执行以下自愈探测及配置流程：
  
  #### 🔍 智能自动探测（优先）：
  AI Agent 在当前终端中运行以下命令以检测当前目录是否已绑定 Git 远程仓库：
  ```bash
  git remote get-url origin
  ```
  * **如果成功获取到远程 Git URL**（如 `https://github.com/username/repo-name.git`）：
    AI Agent 应当在聊天窗口中询问用户：
    > “我检测到您当前的工作目录已关联远程 Git 仓库：`<获取到的Git URL>`。
    > 您是否希望将该远程仓库，作为您转存第三方 AI 工具的目标收藏库？ (是/否)”
    
    * **如果用户选择“是”**：AI Agent 自动将获取到的 URL 作为 `github_remote_url`，写入配置文件，完成初始化。
    * **如果用户选择“否”**（或未检测到 Git 关联）：进入下方的**手动配置流程**。

  #### 💬 手动交互配置流程：
  AI Agent 必须在聊天窗口中向用户提出以下唯一问题以获取相关配置：
  > **您的远程 GitHub 工具收藏仓库推送地址 (Git URL) 是什么？** (例如：`https://github.com/username/ai-tools.git` 或者是 `git@github.com:...`)
  
  AI Agent 拿到用户的输入后，必须在本技能目录下，物理创建或写入 `config.json` 配置文件。
  * **配置文件格式**：
    ```json
    {
      "github_remote_url": "<用户输入的远程Git推送链接>"
    }
    ```

---

### 2. 运行环境与授权自检
每次执行转存时，AI Agent 必须首先读取并验证 `config.json` 中的 `github_remote_url` 参数，并在终端执行以下自检：
1. **远程授权验证**：
   ```bash
   # 临时清除可能冲突的环境变量，校验 GitHub CLI 授权身份
   $env:GITHUB_TOKEN=""; gh auth status
   ```
   * *如果授权失效*：暂停执行，并引导用户运行 `gh auth login` 重新完成 GitHub 身份登录。

---

## 🚀 第二阶段：核心执行工作流 (Workflow)

自检成功后，AI Agent 将使用**“动态临时沙盒”**在当前会话的 `scratch/` 临时目录下完成全套克隆、文件拷贝、文档重塑与推送工作：

### 步骤 1：克隆双端仓库至临时沙盒
1. 在当前会话的 `scratch/` 目录下创建两个临时目录：
   * `scratch/temp_source/`（用于存放第三方工具源文件）
   * `scratch/temp_target/`（用于存放您个人的收藏仓库）
2. 在终端中执行以下命令进行克隆：
   ```bash
   # 1. 克隆源仓库
   git clone <源项目Git链接> scratch/temp_source
   # 2. 克隆您的 GitHub 个人收藏仓库
   git clone <github_remote_url> scratch/temp_target
   ```

### 步骤 1.5：防重与冲突校验
1. **源链接防重校验**：
   * 检查个人收藏仓库根目录下是否存在 `scratch/temp_target/imported_sources.json` 清单文件。
   * 如果该文件存在，读取并解析其 JSON 内容（包含 `imported_urls` 字典）。
   * 将当前待转存的 `<源项目Git链接>` 进行标准化处理（转为全小写，去除结尾的 `.git` 以及末尾的多余斜杠 `/`）。
   * 对比 `imported_sources.json` 中已记录的所有 URL 的标准化形式。如果该源项目链接已被记录：
     * **处理行为**：立即停止执行，并在聊天窗口中向用户反馈：“该工具源项目链接已于 `<imported_at>` 转存过，保存在 `tools/<tool_name>/` 目录中。为避免重复，本次操作已自动终止。”
2. **同名目录冲突校验**：
   * 检查 `scratch/temp_target/tools/<工具名>/` 目录是否已经存在。
   * 如果目录已存在，但上一步的源链接校验未触发（即同一个工具名，但是不同的源项目链接）：
     * **处理行为**：立即停止执行，并在聊天窗口中提示用户：“检测到目标仓库中已存在同名工具目录 `tools/<工具名>/`。为避免文件冲突与覆盖，本次操作已自动终止。请指定不同的工具名以继续。”

### 步骤 2：源码搬运与精简
1. 在 `scratch/temp_target/` 的 `tools/` 目录下为新工具创建专属子目录：`scratch/temp_target/tools/<工具名>/`。
2. 运行命令将源文件复制过去：
   ```powershell
   # 排除 .git, .github 和原始 README.md 等文件以防止嵌套冲突，执行物理迁移
   Get-ChildItem -Path scratch/temp_source/ -Exclude .git, .github, README.md | Copy-Item -Destination scratch/temp_target/tools/<工具名>/ -Recurse -Force
   ```

### 步骤 3：源说明自带中文识别与重构
在重写 `scratch/temp_target/tools/<工具名>/README.md` 前，AI Agent **必须首先智能识别源链接的说明是否自带中文**：

#### 🔍 语言智能识别与分流机制：
1. **自带中文说明检测**：
   AI Agent 必须检查克隆到本地的 `scratch/temp_source/` 目录：
   * 检查默认 `README.md` 是否包含大量中文字符。
   * 检索源目录中是否存在其它命名中含有中文标识的说明文档（如 `README_zh.md`、`README_zh_CN.md`、`README_cn.md` 等，或者在 `docs/` 下存在中文文档）。
2. **基于检测结果的分流执行**：
   * **分支 A：自带原生中文说明**
     * **原则**：最小干预，尊重原作。AI Agent 应当**直接采用并合并这些原生中文说明**。
     * **操作**：直接以此原生中文说明为蓝本，保留原作者的专业词汇和句式，仅对其段落大纲进行调整，使其符合本项目的“两阶段”自愈与工作流排版。
   * **分支 B：无任何自带中文说明（纯英文或其他语言）**
     * **原则**：本地化翻译重塑。
     * **操作**：AI Agent 必须在脑内自动将其技术细节、指令参数、诊断步骤和逻辑架构翻译并润色为高质量的简体中文，同样按照“两阶段结构”进行格式排版。
     * **质量要求**：严格禁止生硬的机器翻译腔，且绝对禁止使用英文助词替代中文汉字（如“的”、“和”等）。

#### 📄 说明文档“两阶段结构”排版规范：
重塑后的 README 必须统一按以下结构排版：
1. **第一阶段：环境自检与首次初始化引导**：
   * 详细描述如何运行该工具的诊断体检命令（如 `doctor` 命令）。
   * 说明当环境依赖缺失（如传统依赖包、Node.js 运行环境等）时，AI Agent 该如何自动执行修复或安装。
   * 说明在首次运行时，如何进行交互式的本地凭证（如 Cookie、Token）的自愈与初始化配置。
2. **第二阶段：核心执行工作流**：
   * 详细列出工具的路由机制、功能优先级。
   * 给出核心的命令手册、运行参数以及卸载方法。

### 步骤 4：主索引更新与中文化填报
打开 `scratch/temp_target/README.md`，在**“🛠️ 收藏工具索引”**表格中，新增一行该工具的索引信息。
* **语言规范**：表格中所有的填报项，包括工具名称、核心功能和触发场景，**必须一律总结、精炼并翻译为中文**（即便原仓库是英文）：
  * 逻辑分类（如：网页检索、MCP服务、技能指令等）
  * 工具名称
  * 核心功能简述（中文）
  * 触发场景简述（中文）
  * 详细说明的相对链接：格式统一为 `[👉 详细配置与使用指南](tools/<工具名>/README.md)`

### 步骤 5：提交与远程推送
1. **记录已转存清单**：
   * 在执行 Git 提交前，更新或创建个人收藏仓库根目录下的 `scratch/temp_target/imported_sources.json` 文件。
   * 将当前的 `<源项目Git链接>`（保留原始格式）作为键添加至 `imported_urls` 字典，并填充对应的值，包含当前转存的 `tool_name` 设为 `<工具名>` 和 `imported_at` 设为当前 ISO 8601 时间戳（如当前本地时间）。
   * 结构示例：
     ```json
     {
       "imported_urls": {
         "<源项目Git链接>": {
           "tool_name": "<工具名>",
           "imported_at": "2026-07-13T10:37:52+08:00"
         }
       }
     }
     ```
2. **执行 Git 提交与推送**：
   * 进入临时目录 `scratch/temp_target/` 中，将新生成或更新后的 `imported_sources.json` 以及其它修改全部添加、提交并推送到远程仓库：
     ```bash
     git add .
     git commit -m "Merge source code, update imported_sources.json and restructure README for <工具名> into tools directory"
     # 清理环境变量干扰，推送至主分支
     $env:GITHUB_TOKEN=""; git push origin main
     ```

### 步骤 6：沙盒物理清理
推送成功后，必须立即物理销毁沙盒中的临时副本，确保本地空间干净：
```powershell
Remove-Item -Recurse -Force scratch/temp_source
Remove-Item -Recurse -Force scratch/temp_target
```
最后，向用户汇报远程 GitHub 仓库的最新在线查阅地址。
