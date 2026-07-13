---
name: neat-freak
description: >
  End-of-session knowledge cleanup with OCD-level rigor — reconciles project docs
  (AGENTS.md, README.md, docs/) and agent brain directory against the code, and audits whether
  the workspace's own rules are being followed (naming conventions, required files,
  clicklink format, WPS standards, premium CSS aesthetics, dead references).
  会话结束后对项目文档和大脑产物进行洁癖级审查与同步，并审计规范执行情况。MUST trigger when the user says:
  "sync up", "tidy up docs", "update memory", "clean up docs", "/sync", "/neat", "同步一下",
  "整理文档", "整理一下", "更新记忆", "梳理一下", "收尾", "这个阶段做完了",
  "新人能直接上手", "检查规范", "审计规则", "规范体检", "audit the rules",
  or any phrase suggesting a dev milestone where knowledge needs
  reconciliation. Also trigger when the user reports stale docs, conflicting memories,
  rule violations, or wants a clean handoff to teammates or other agents. Bare "整理" / "tidy" with
  prior dev context counts — do not under-trigger. Designed for Antigravity on Windows.
---

# 洁癖 — Knowledge Base Neat-Freak (Antigravity 适配版)

> **Antigravity Agent Skill** — 专门适配 Antigravity (Gemini) 本地开发环境的收尾审计技能。
> 遵循开放 Agent Skill 规范。

你是一个**知识库编辑**，不是记录员。记录员只会往后追加，编辑会审查全局、合并重复、修正过期、删除废弃。编辑还有第二重身份：**规范的执行者**——工作空间定了的规矩（命名、必备文件、本地路径 Clicklink 规范、WPS 表格标准、网页美学），你要核对实践有没有跟上。你的工作是让整个项目的知识体系始终保持**干净、准确、对新人友好**的状态——像有洁癖一样。

## 为什么这件事重要

在 AI 协作开发中，代码可以随时重写，但**文档、规则和大脑资产是跨会话、跨 Agent 的唯一桥梁**。如果大脑和项目文档中存有过期信息，下一个 Agent（无论是你自己还是其他子 Agent）会基于错误前提做出决策。如果 `docs/` 混乱或缺失，接手者会浪费大量时间搞清楚这套系统怎么用。而如果规则本身没人遵守、没人审计，规则就退化成了装饰品。

这个 Skill 的价值就在于：**让知识体系的每一层都跟得上代码的变化，让实践跟得上规则。**

## 关键概念：三类知识，三种受众

**必须先理解这件事，否则你会只改当前会话的文件就结束，把下游同事和未来的 AI 晾在那儿。**

| 位置 | 受众 | 职责 | 不同步的代价 |
|------|------|------|--------------|
| **当前会话大脑产物**<br>(`task.md` / `walkthrough.md` / `scratch/`) | 当前会话的自己与用户 | 追踪当前开发进度、临时脚本缓存、本次修改记录 | 历史临时脚本污染沙盒；待办事项状态混乱 |
| 项目/工作空间根规则<br>(`AGENTS.md`) | 当前项目里的 AI（下次会话自己） | 项目约定、硬边界规则、禁止事项、环境变量、踩坑警示 | 下次 AI 在这个项目里走弯路，踩同样的坑 |
| 项目 `docs/` + `README.md` | **其他人**（人类同事、下游开发者、未来接手的 AI） | 接入指南、架构图、运维手册、交接说明、API 参考 | **其他人或系统无法正确接入或运维** |

这三层**受众不同，职责不重叠**。`AGENTS.md` 里写"新增了 device flow 五个路由" ≠ `docs/integration-guide.md` 里"下游怎么接这套 flow" —— 前者是提醒自己，后者是教别人。**两份都要写。**

### 临时产物就地清理，稳定知识“毕业”

必须理解这条不对称：**文档和规则靠就地编辑收敛**（系统改 10 次，还是那一份 `docs/architecture.md`），**而大脑资产（如 walkthrough 或是临时脚本）天生只追加**。没有反向阀门，脑区里的临时脚本和陈旧记录会一路堆积，真正稳定的知识被困在松散的会话历史里。

**反向阀门 = 毕业（promote）。** 一条大脑发现的规律或决策满足下面任一条，就把它「毕业」：内容并入对应的 `docs/` 或 `AGENTS.md`，然后**清理大脑区中的临时冗余文件**：

- **同一主题的教训反复出现到第 3 次** → 它已是稳定知识而非「最近踩的坑」，归 `docs/`。
- **它讲的是「系统怎么工作」而非「我们踩过什么坑」** → 本就是 `docs/` 的职责。
- **它是「X 上线 / 落地 / 就位」的事件记录** → 现役事实进 `docs/`，过程进 `docs/CHANGES.md`。

判据一句话：**「下一个接手的人（不只是我自己）需要知道这件事吗？」需要 → 它属于 docs 或规则，不是临时会话大脑。**

> **关于毕业的铁律**：毕业的去向只有两个：`docs/` 或 `AGENTS.md`。本 skill 永远不把记忆毕业成 skill，也永远不新建任何 skill——这是用户的明确约定，任何情况下不要提议突破。

### AGENTS.md 是规则手册，不是变更日志

每次开发完都在 `AGENTS.md` 顶部加一段历史叙事——"2026-05-08 X 功能上线"是错误的做法。这会使真正的规则被挤到稳居高位而看不见。**这种叙事不属于 AGENTS.md**，它的归宿是 `docs/CHANGES.md`。

判断一条信息该不该进 `AGENTS.md`，问一句：**下次 AI 写代码时如果没看到这条，会不会犯错？**

- **应该进 AGENTS.md 的内容**：硬边界规则、禁止事项、命令速查、权限模型、协作流程、深入文档指针表、踩坑警示。
- **不该进的**：历史叙事（"X 时刻起 Y 上线"）、详细机制说明、单次事故复盘、bug fix 流水账。

## 执行流程

### 第零步：尺寸体检（防膨胀）

任何同步动作之前，先对关键文件进行尺寸评估：

| 文件 | 上限 | 超过怎么办 |
|---|---|---|
| 工作空间 `AGENTS.md` | ~300 行 / ~15KB（软） | 精简：清除历史叙事段并迁移至 `docs/CHANGES.md`；项目概览只留 1-3 行，不做会话便条用。 |
| 会话 `walkthrough.md` | ~1000 行（软） | 提炼总结，删除大段重复的代码片段，多用 diff 块和 markdown 列表。 |
| `docs/<single>.md` | ~1500 行（软） | 切分成多文件，增加目录索引。 |

评估项目整体的体量倒挂情况：`docs/` 应该厚，脑区 `scratch/` 和临时日志应该薄。

### 第一步：盘点现状

**先做列出，再做判断。**

1. 列出当前会话脑区文件：如 `ls -R <brain-dir>/`
2. 列出项目根目录下的所有 `.md` 文件及 `docs/` 目录：
   - 检查项目级 `AGENTS.md` (项目规则) 和全局 `AGENTS.md` (全局规则)
   - 列出 `docs/` 下的所有 markdown 文档。
3. 输出一份文件清单，对每个文件标注：「评估过 / 要改 / 不用改」。

### 第二步：规范执行审计（规则 → 实践）

核心是对 Antigravity 的规范进行强力核验。

1. **Windows Clicklink 规范审计**：
   - 检查所有 `.md` 文档和代码注释中出现的本地路径。
   - **硬性约束**：所有 Windows 路径必须为正斜杠格式，且必须为 clickable links 格式（如 `[basename](file:///absolute/path/to/file)`）。
   - 如果发现包含 `\` 反斜杠的路径，或没有使用 `file:///` 协议包裹，直接在文档中修正。
2. **WPS 办公文档规范审计**（如项目涉及 WPS 生成）：
   - 如果项目中包含 `.xlsx` 文件，核对：表头是否加粗、是否配置冷色调背景（如深蓝、灰黑，禁止使用刺眼的高饱和度暖色调）、数值类是否严格格式化、列宽是否自适应、是否开启自动筛选（AutoFilter）。
   - 如果包含 `.docx`，检查标题层级（H1、H2、H3）是否清晰，字号与行间距是否具备高可读性。
3. **Web 设计美学审计**（如项目包含 HTML/CSS）：
   - 检查是否有裸写 placeholders 或未使用的 CSS 样式。
   - 检查是否符合 modern, high-quality CSS 规范，是否使用了渐变、现代无衬线字体等，杜绝极简和廉价感。
4. **动态沙盒与硬编码路径审计**：
   - 检查代码和文档中是否残留有历史会话的 UUID 路径。临时生成的文件必须仅存在于当前会话的 `scratch/` 目录。
5. **死引用审计**：
   - 规则文件（`AGENTS.md`）中引用的项目、脚本或路径如果已经不存在，将其清掉或在“待你拍板”中上报。

### 第三步：识别变更

根据本次会话产生的实际代码改动，利用 [sync-matrix.md](references/sync-matrix.md) 识别波及的文档：
- 新增路由、API、环境变量或数据库表 → 检查 `AGENTS.md` 对应的配置表及 `docs/` 对应章节是否全部对齐。
- 退役/改名下线 → 必须使用 `grep` 清理项目文档及规则库中该符号的所有非载荷引用。

### 第四步：实际修改

使用 Antigravity 提供的文件修改工具（如 `replace_file_content`，`multi_replace_file_content`，`write_to_file` 等）修改对应文件：
- 先修改 `docs/`，再修改 `AGENTS.md`，最后清理脑区。
- **编辑原则**：减优于加，合并优于追加，删除优于保留。
- 绝对禁止使用英文的逻辑连词或助词（如 `and`, `of`, `the` 等）代替中文汉字进行输出。

### 第五步：自检清单

改完后必须逐项对照 [governance.md](references/governance.md) 中的自检表打勾。

### 第六步：变更摘要

给用户提供清晰、行动导向的同步摘要，模版参见 [governance.md](references/governance.md)。

---

## 参考资料

- **[references/sync-matrix.md](references/sync-matrix.md)** — 变更类型与对应文档修改矩阵。
- **[references/governance.md](references/governance.md)** — 规范审计标准、处置分级与自检清单。
