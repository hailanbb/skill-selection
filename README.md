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
  2. 首次运行任意抓取指令时，AI 会在聊天中主动向您询问本地的 Obsidian 库物理路径及图片存放偏好，完成初始化配置并持久化保存。

---

## 📖 第三方依赖组件与配套 MCP/Skill 安装指南

为了充分发挥本技能的自动化与混合检索威力，推荐您安装并配置以下配套的第三方环境和 MCP 扩展服务。

### 1. 基础 Python 环境与依赖 (强制要求)
本技能底层的数据抓取与 HTML 转换驱动基于 Python。
* **依赖库安装**：
  在您的本地终端运行以下命令，以安装解析网页和转换 Markdown 所需的 Python 库：
  ```bash
  pip install beautifulsoup4 markdownify lxml
  ```
  *(注：AI 在首次触发此技能进行自检时，若发现缺失上述库，也会尝试自动为您在终端执行安装。)*

### 2. Enquire-MCP (本地混合检索服务 - 强烈推荐)
**Enquire-MCP** 是专为 Obsidian 设计的 Model Context Protocol 混合检索服务器。配置它后，本技能在每次转存文章完毕时，都将**在后台自动触发全文分词与向量 embeddings 的实时刷新**，使得新保存的文章立即可被您的 AI Agent 检索问答。

* **第一步：全局安装 CLI 服务**（需要本地已安装 Node.js/NPM 环境）：
  ```bash
  npm install -g @oomkapwn/enquire-mcp
  ```
* **第二步：在 AI 客户端中注册配置**：
  打开您 AI 客户端（如 Cursor、Windsurf 或 Gemini/Antigravity）的全局配置文件 `mcp_config.json`，在 `"mcpServers"` 节点下，加入以下配置：
  ```json
  "enquire-mcp": {
    "command": "node",
    "args": [
      "C:\\\\Users\\\\您的用户名\\\\AppData\\\\Roaming\\\\npm\\\\node_modules\\\\@oomkapwn\\\\enquire-mcp\\\\dist\\\\index.js",
      "serve",
      "--vault",
      "您的Obsidian库绝对路径(使用正斜杠或双反斜杠)",
      "--persistent-index",
      "--enable-reranker",
      "--use-hnsw"
    ]
  }
  ```
  *(注：当您首次使用“链接转存obs”技能并配置好 Obsidian 路径后，AI 也可以在征得您同意的情况下，自动修改您的 `mcp_config.json` 完成上述注册。)*

### 3. AnySearch (网页抓取与搜索技能 - 微信防爬降级源)
**AnySearch** 是一个支持 14 个动态网页提取代理的全球搜索与抓取技能。当微信公众号服务器对您的本地 IP 实施了物理阻断（触发滑块验证码）时，AnySearch 技能将作为**第一优先备选的代理降级源**去抓取文章，大幅度提升转存成功率。

* **安装说明**：
  1. 请到 [AnySearch GitHub 项目] 或精选库中获取 `anysearch-skill`。
  2. 将其以文件夹的形式复制存放在您的全局配置 `config/skills/` 目录下（保持与 `链接转存obs` 为兄弟目录关系即可，脚本会自动检测其存在）。
  3. *(可选)* 可在其 `SKILL.md` 中配置 `ANYSEARCH_API_KEY` 以获得更高的请求额度。

### 4. Firecrawl-MCP (高级爬取与无头浏览器渲染 MCP - 备用降级源)
**Firecrawl** 是强大的网页爬取工具。如果在极其严格的封锁下，以上所有工具均失败，Firecrawl 的云端无头渲染代理是最后的穿透利器。

* **注册与配置**：
  1. 前往 [Firecrawl 官网](https://www.firecrawl.dev) 注册一个免费账户以获取您的 API 密钥（格式为 `fc-...`）。
  2. 打开您客户端的 `mcp_config.json` 文件，在 `"mcpServers"` 下加入以下配置：
     ```json
     "firecrawl-mcp": {
       "command": "npx",
       "args": ["-y", "firecrawl-mcp"],
       "env": {
         "FIRECRAWL_API_KEY": "您的FIRECRAWL_API_KEY"
       }
     }
     ```
  3. 配置好后，AI Agent 将自动能够在直连报错时调用 Firecrawl 进行高级穿透爬取。
"""
with open(os.path.join(dest_repo_dir, "README.md"), 'w', encoding='utf-8') as f:
    f.write(readme_content)

print("README.md updated successfully with detailed guides!")
