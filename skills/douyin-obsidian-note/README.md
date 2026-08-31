# 抖音转笔记（Douyin to Obsidian Note）

`douyin-obsidian-note` 是一个面向 Codex、Gemini、Claude Code 及其他兼容 Agent Skills 的抖音视频知识整理技能。它将单条抖音视频、分享文本或本地视频提炼成一篇适合长期学习和检索的 Obsidian Markdown 图文笔记，并把真正有解释价值的关键画面保存为本地图片。

它不是“逐字稿生成器”，也不是把视频机械切成几十张截图。它的目标是：

> 用最少但充分的文字和画面，让读者不重新播放视频也能理解核心观点、方法、案例和适用边界。

---

## 适合解决什么问题

- 把一条抖音知识视频整理成可复习的 Markdown 笔记。
- 把教程、营销、知识科普、操作演示或案例视频保存到 Obsidian。
- 从视频中选择 3–8 张真正关键的画面，嵌入对应知识段落。
- 自动生成适合检索的中文标题、文件名和图片目录。
- 按固定 Frontmatter 属性保存来源、作者、发布时间和封面。
- 在任务结束后清理下载视频、音频、ASR 转写和候选帧等临时材料。

以下场景不属于本技能的主要范围：

- 交付完整逐字稿、SRT/VTT 字幕或时间轴工程文件。
- 批量研究整个账号、话题、竞品或评论区。
- 下载和永久收藏原始抖音视频。
- 只做视频搬运，而不需要知识提炼和 Obsidian 归档。

如果需要完整字幕、评论研究或批量账号分析，可配合 [Rimagination/dy-note](https://github.com/Rimagination/dy-note) 使用；本技能聚焦最终的 Obsidian 图文笔记发布环节。

---

## 核心特点

### 1. 笔记优先，不堆原始材料

ASR 转写、页面简介和候选画面只是内部证据。最终 Obsidian 库只保留：

- 一篇提炼后的 `.md` 笔记。
- 笔记实际引用的关键图片。

不会把原始视频、音频、逐字稿、ASR JSON、候选截图或时间轴复制进 Obsidian。

### 2. 关键画面由内容决定

技能先抽取少量候选帧，再由 Agent 结合视频内容和相邻文本判断哪些画面值得保留。优先选择：

- 核心概念、图表、菜单或操作界面。
- 方法步骤、前后对比或最终结果。
- 仅靠声音无法理解的画面信息。
- 能准确代表主题的清晰封面帧。

黑屏、片头、二维码、广告、重复构图、模糊过渡帧和无关人物画面会被排除。

### 3. 适配 Obsidian 的稳定文件结构

- 图片使用 Obsidian 库根目录相对链接。
- 正文使用 `![[路径/图片.jpg]]` wiki 嵌入格式。
- 图片以内容哈希命名，避免中文路径冲突和重复文件。
- 笔记、图片目录和 Frontmatter 均使用 UTF-8 无 BOM。

### 4. 首次配置后永久复用

第一次处理视频前，Agent 会询问：

1. Markdown 笔记保存目录。
2. 图片保存目录。

配置成功后保存到用户配置目录，后续任务不再重复询问。更换 Obsidian 库或原路径失效时才重新配置。

### 5. 不覆盖已有笔记

- 同一 URL 已经存在：停止并提示已有笔记，不覆盖、不复制。
- 标题相同但来源 URL 不同：自动追加短哈希，避免同名冲突。
- 图片内容相同：复用相同哈希文件，不重复保存。

### 6. 受保护的临时文件清理

本技能使用带专用标记的临时运行目录。清理脚本只会删除同时满足以下条件的目录：

- 目录名以 `douyin-obsidian-note-` 开头。
- 目录内存在匹配的运行标记文件。
- 标记中记录的绝对路径与待清理目录完全一致。

用户提供的本地视频、Obsidian 笔记和已发布图片不会被清理。

---

## 目录结构

```text
douyin-obsidian-note/
├── SKILL.md                         # Agent 核心工作流、触发条件与硬性约束
├── README.md                        # 本使用说明
├── agents/
│   └── openai.yaml                 # 技能展示名、简介和默认调用提示
├── references/
│   ├── note-format.md              # Frontmatter、正文结构和图片占位符规范
│   └── workflow.md                 # 取证路线、关键帧筛选与写作闸门
└── scripts/
    ├── common.py                   # 配置、标题清理、路径安全与验证公共函数
    ├── configure.py                # 首次配置和配置状态检查
    ├── run_workspace.py            # 创建及安全清理临时运行目录
    ├── extract_metadata.py         # 安全提取 yt-dlp 元数据，支持无嵌套 PowerShell 的后台模式
    ├── extract_keyframes.py        # 从本地视频抽取候选帧或指定时间帧
    ├── publish_note.py             # 图片归档、Frontmatter 生成和笔记发布
    └── validate_note.py            # 校验属性、图片链接、编码和禁用内容
```

---

## 运行要求

### 必需条件

- Python 3.10 或更高版本。
- 一个有效的 Obsidian 库，库根目录中存在 `.obsidian`。
- 笔记目录和图片目录位于同一个 Obsidian 库中。
- Agent 能读取用户提供的抖音链接、分享文本或本地视频。

### 按需条件

| 功能 | 需要的组件 | 说明 |
|---|---|---|
| 从本地视频抽帧 | `ffmpeg` 与 `ffprobe` | `extract_keyframes.py` 会调用两者 |
| 从链接提取公开元数据 | `yt-dlp` | `extract_metadata.py` 使用参数数组执行，避免 PowerShell 后台转义问题 |
| 图片统一转为 640px JPEG | Pillow 或 `ffmpeg` | 优先使用 Pillow；两者都没有时保留原格式并使用 `_0` 后缀 |
| 从视频语音获得文本 | 可用的 ASR 工具 | 可复用本机 `dy-note`、Qwen3-ASR、Whisper 或宿主 Agent 已有能力 |
| 从抖音链接获得视频/页面内容 | 已授权浏览器会话或宿主工具 | 不读取或导出 Cookie、token 和签名链接 |

本技能没有绑定某个容易失效的抖音下载接口。链接解析、浏览器登录态和 ASR 由宿主 Agent 或现有 `dy-note` 能力提供；本技能负责把证据稳定地整理和发布到 Obsidian。

---

## 安装方式

### Codex 全局安装

把整个目录复制到：

```text
%USERPROFILE%\.codex\skills\douyin-obsidian-note\
```

PowerShell 示例：

```powershell
$source = "D:\下载\skill-selection\skills\douyin-obsidian-note"
$target = "$env:USERPROFILE\.codex\skills\douyin-obsidian-note"
Copy-Item -LiteralPath $source -Destination $target -Recurse
```

### Gemini / Antigravity 全局安装

复制到：

```text
%USERPROFILE%\.gemini\config\skills\douyin-obsidian-note\
```

### 项目级安装

复制到项目根目录：

```text
<项目目录>\.agents\skills\douyin-obsidian-note\
```

安装时必须保留整个目录，不要只复制 `SKILL.md`。脚本、参考文件和 `agents/openai.yaml` 都属于技能的一部分。

---

## 如何触发

推荐显式调用：

```text
使用 $douyin-obsidian-note 把这个抖音视频整理成图文笔记并保存到 Obsidian：
https://www.douyin.com/video/...
```

也可以直接描述需求：

```text
把这条抖音视频提炼成带关键截图的 Obsidian 学习笔记。
```

```text
把这个本地视频整理成图文笔记，关键步骤要配图：D:\Videos\demo.mp4
```

```text
将下面的抖音分享文本转成 Obsidian 图文笔记：……
```

自动触发关键词包括：抖音转图文笔记、视频保存到 Obsidian、抖音知识整理、关键帧笔记、视频提炼成 Markdown 等。

---

## 第一次使用：配置 Obsidian 路径

### 1. 检查配置

将 `$skillRoot` 替换为实际安装目录：

```powershell
$skillRoot = "$env:USERPROFILE\.codex\skills\douyin-obsidian-note"
python "$skillRoot\scripts\configure.py" --status
```

首次运行会返回：

```json
{
  "configured": false,
  "config_path": ".../.config/douyin-obsidian-note/config.json",
  "config": null
}
```

此时 Agent 会暂停处理视频，并让用户输入两个绝对路径。

示例：

```text
笔记目录：E:\hailan\01 待阅收件箱\抖音笔记
图片目录：E:\hailan\98 cloudflareR2\01 待阅收件箱\抖音笔记
```

两个路径都必须位于同一个 Obsidian 库下。脚本会向上查找 `.obsidian`，自动确定库根目录。

### 2. 保存配置

```powershell
python "$skillRoot\scripts\configure.py" `
  --note-dir "E:\hailan\01 待阅收件箱\抖音笔记" `
  --image-dir "E:\hailan\98 cloudflareR2\01 待阅收件箱\抖音笔记" `
  --create-dirs
```

配置默认保存在：

```text
~/.config/douyin-obsidian-note/config.json
```

如需为测试、多个库或不同 Agent 指定其他配置文件，可设置：

```powershell
$env:DOUYIN_OBSIDIAN_NOTE_CONFIG = "D:\Config\douyin-note.json"
```

配置文件只保存本地路径，不保存 Cookie、账号、token 或视频地址。

---

## 完整工作流程

日常使用时只需要向 Agent 提供视频或链接，以下步骤由 Agent 自动执行。底层命令主要用于理解、调试或手工恢复。

### 步骤 1：创建临时运行目录

```powershell
python "$skillRoot\scripts\run_workspace.py" create
```

示例返回：

```json
{
  "created": true,
  "run_dir": "C:\\Users\\user\\AppData\\Local\\Temp\\douyin-obsidian-note-abc123"
}
```

本次任务的下载视频、音频、ASR 转写、元数据和候选帧全部写入该目录。

### 步骤 2：取得最小充分证据

证据使用顺序：

1. 用户已经提供的本地视频、字幕或转写。
2. 抖音页面可见的标题、作者、发布时间、简介和独立字幕。
3. 本机已有 `dy-note`、Qwen3-ASR、Whisper 或其他 ASR。
4. 关键帧和必要的画面文字识别。

页面简介不等于字幕；ASR 也无法证明焊在视频画面里的文字、价格、动作和操作界面。涉及视觉事实时必须查看画面。

如果配合 `dy-note`，务必把它的 `--out-dir` 指向步骤 1 创建的临时目录。它输出的转写和元数据仅用于理解视频，不复制到 Obsidian。

通过 `yt-dlp` 获取公开元数据时，使用内置助手：

```powershell
$sourceUrl = "https://www.douyin.com/video/..."
python "$skillRoot\scripts\extract_metadata.py" `
  --url $sourceUrl `
  --output "<临时目录>\metadata.json"
```

需要后台运行时直接增加 `--background`：

```powershell
python "$skillRoot\scripts\extract_metadata.py" `
  --url $sourceUrl `
  --output "<临时目录>\metadata.json" `
  --background
```

返回结果包含 PID、状态文件和日志文件。轮询状态文件，状态会从 `starting`/`running` 进入 `succeeded` 或 `failed`；仅在 `succeeded` 后读取 `metadata.json`。不要把命令包装为双引号中的 `powershell -Command`，也不要在嵌套命令字符串中引用 `$env:...`；父 PowerShell 会提前展开变量，路径中的空格、`&` 和引号也可能被再次解析。助手直接传递参数数组，不经过 Shell 二次解释。

元数据文件只保留标题、作者、发布时间、时长、统计值和规范页面 URL 等白名单字段。`yt-dlp` 返回的格式直链、Cookie、请求头和签名视频 URL 不会写入磁盘。

### 步骤 3：抽取候选画面

均匀抽取 16 张候选帧：

```powershell
python "$skillRoot\scripts\extract_keyframes.py" `
  --video "<临时目录>\video.mp4" `
  --out-dir "<临时目录>\candidates" `
  --auto-count 16
```

如果已从章节或转写定位到关键时间，可以精确抽帧：

```powershell
python "$skillRoot\scripts\extract_keyframes.py" `
  --video "<临时目录>\video.mp4" `
  --out-dir "<临时目录>\selected" `
  --at 00:00:03.5 `
  --at 00:00:27 `
  --at 00:01:12
```

Agent 会逐张查看候选画面，通常保留 3–8 张。短视频信息量低时可以更少，高密度长视频也不应超过实际需要。

### 步骤 4：撰写正文草稿

草稿不写 YAML Frontmatter，只写笔记正文。图片位置使用占位符：

```markdown
# 为什么让顾客思考反而更难成交

> 好文案的作用，是降低理解和决策成本，让用户快速看见价值。

## 两套决策系统

日常消费经常由直觉、经验和情绪推动；复杂分析会消耗更多注意力。

{{image:1|画面展示系统 1 与系统 2 的区别}}

## 核心方法

把抽象参数翻译成具体场景、当下痛点和可感知结果。

## 适用边界

医疗、金融和大额购买仍应提供完整证据与理性比较。
```

`{{image:1}}` 对应发布命令中 `--images` 的第一张图片。可写说明，也可以省略：

```markdown
{{image:2}}
```

最终笔记不包含完整逐字稿、全文转录、实践清单、自检清单、自测题或大段时间轴证据。

### 步骤 5：发布到 Obsidian

```powershell
python "$skillRoot\scripts\publish_note.py" `
  --draft "<临时目录>\draft.md" `
  --title "为什么让顾客思考反而更难成交" `
  --source-url "https://www.douyin.com/video/..." `
  --author "老丁有异见" `
  --publish-time "2026-08-30 10:00:00" `
  --images "<临时目录>\selected\frame-01.jpg" "<临时目录>\selected\frame-02.jpg"
```

发布脚本会自动完成：

1. 清理并缩短笔记文件名。
2. 建立以智能标题命名的图片子目录。
3. 将图片缩放为宽度不超过 640 像素的 JPEG。
4. 按图片最终内容计算 MD5 哈希。
5. 生成 `<32位哈希>_640.jpg` 文件名。
6. 替换正文图片占位符为 Obsidian wiki 嵌入。
7. 生成 YAML Frontmatter。
8. 在验证通过后原子写入笔记，避免半成品文件。

### 步骤 6：验证最终笔记

```powershell
python "$skillRoot\scripts\validate_note.py" "<最终笔记.md>"
```

验证范围包括：

- 文件是否为 UTF-8 无 BOM。
- 八个 Frontmatter 属性是否齐全。
- 是否仍有未替换图片占位符。
- 所有图片是否位于同一 Obsidian 库且真实存在。
- `cover` 是否指向本地图片。
- 是否包含 `file:///`、视频/音频链接或普通 Markdown 图片语法。
- 是否出现被禁止的逐字稿或清单章节。
- 是否像按时间戳堆积的完整转录。

### 步骤 7：清理临时材料

无论任务成功、失败或中断，最后都运行：

```powershell
python "$skillRoot\scripts\run_workspace.py" cleanup --path "<本次临时目录>"
```

清理完成后，最终只留下 Obsidian 中已发布的 Markdown 和关键图片。

---

## 最终笔记格式

Frontmatter 字段参考常见 Obsidian 剪藏属性：

```yaml
---
title: "为什么让顾客思考反而更难成交"
category: "video"
url: "https://www.douyin.com/video/..."
origin: "抖音"
cover: "98 cloudflareR2/01 待阅收件箱/抖音笔记/为什么让顾客思考反而更难成交/9b18e942a0f118eba7754c6cf6f15a8d_640.jpg"
author: "老丁有异见"
publishTime: "2026-08-30 10:00:00"
createTime: "2026-08-31 09:30:00"
---
```

属性含义：

| 属性 | 说明 |
|---|---|
| `title` | 自然、准确、便于检索的展示标题 |
| `category` | 默认 `video`，可在发布时修改 |
| `url` | 原始抖音来源 URL |
| `origin` | 默认 `抖音` |
| `cover` | 第一张关键图片的库内相对路径 |
| `author` | 视频作者；未知时为空字符串，不编造 |
| `publishTime` | 视频发布时间；未知时为空字符串 |
| `createTime` | 笔记生成时的本地时间 |

正文通常由以下内容组成，但不会机械套模板：

- 一句话摘要或结论。
- 2–6 个核心观点、方法、步骤、案例或对比章节。
- 放在对应段落后的关键画面。
- 必要的适用边界、风险或证据限制。
- 简短来源说明。

---

## 文件命名规则

### 笔记文件名

展示标题可以保留自然标点，但物理文件名会：

- 保留中文、英文字母、数字、连字符和下划线。
- 删除空格、引号、冒号、问号和 Windows 非法字符。
- 默认限制长度，避免超长路径。
- 空标题回退为 `抖音图文笔记`。
- Windows 保留名称会自动加 `笔记_` 前缀。

示例：

```text
为什么让顾客“思考”，反而更难成交？
↓
为什么让顾客思考反而更难成交.md
```

### 图片文件名

正常转换后的图片：

```text
9b18e942a0f118eba7754c6cf6f15a8d_640.jpg
```

当 Pillow 与 `ffmpeg` 都不可用、只能保留原始文件时：

```text
9b18e942a0f118eba7754c6cf6f15a8d_0.png
```

### 输出结构示例

```text
ObsidianVault/
├── .obsidian/
├── 01 待阅收件箱/
│   └── 抖音笔记/
│       └── 为什么让顾客思考反而更难成交.md
└── 98 cloudflareR2/
    └── 01 待阅收件箱/
        └── 抖音笔记/
            └── 为什么让顾客思考反而更难成交/
                ├── 9b18e942a0f118eba7754c6cf6f15a8d_640.jpg
                └── 48ad94f38ab3a77df23ea94a4a841b7d_640.jpg
```

---

## 脚本速查

| 脚本 | 主要命令 | 用途 |
|---|---|---|
| `configure.py` | `--status` | 检查是否已配置 Obsidian 路径 |
| `configure.py` | `--note-dir ... --image-dir ...` | 保存笔记与图片目录 |
| `run_workspace.py` | `create` | 创建带保护标记的临时运行目录 |
| `run_workspace.py` | `status --path ...` | 检查目录是否为合法运行目录 |
| `run_workspace.py` | `cleanup --path ...` | 安全清理本次临时目录 |
| `extract_metadata.py` | `--url ... --output ...` | 前台安全提取白名单元数据 |
| `extract_metadata.py` | `--url ... --output ... --background` | 无嵌套 PowerShell 的后台元数据任务 |
| `extract_keyframes.py` | `--auto-count 16` | 均匀抽取候选帧 |
| `extract_keyframes.py` | `--at HH:MM:SS` | 按指定时间抽取关键帧 |
| `publish_note.py` | `--draft ... --images ...` | 发布笔记和本地图片 |
| `validate_note.py` | `<笔记.md>` | 验证最终格式、链接与安全约束 |

---

## 安全与隐私

- 不读取、导出、保存或打印 Cookie、token、浏览器存储和抖音签名 URL。
- 只使用用户已经授权的浏览器会话或用户主动提供的本地文件。
- 配置文件只包含本地路径。
- 视频、音频、ASR 和候选帧不进入 Obsidian，也不提交到 GitHub。
- 清理仅针对带匹配标记的专用临时目录。
- 不删除用户提供的原始本地视频。
- 不覆盖已有笔记；同一来源需要更新时，应由用户明确决定如何处理旧笔记。

---

## 常见问题

### 为什么第一次使用时不立即处理视频？

技能必须先知道笔记和图片保存在哪里，并确认两个目录属于同一个 Obsidian 库。这样才能生成稳定的相对图片链接，避免文件散落。

### 为什么要求图片目录位于同一个 Obsidian 库？

Obsidian 的 wiki 嵌入通常基于库内相对路径。图片位于库外时，不同设备和同步工具很难稳定解析。

### 为什么不保存完整逐字稿？

这个技能的产品目标是学习笔记，而不是字幕资料库。逐字稿会显著增加噪声、重复和检索负担。ASR 只作为内部证据，最终保留提炼后的观点、方法、例子和边界。

### 为什么关键图片不是越多越好？

大量相似截图会让笔记变长，却不增加理解。技能优先保留能够证明核心概念、步骤、对比或结果的画面，通常 3–8 张已经足够。

### 提示找不到 `ffmpeg` 或 `ffprobe` 怎么办？

安装 FFmpeg，并确认 `ffmpeg`、`ffprobe` 可以在终端直接运行。安装依赖属于系统变更，应由用户确认后再执行。

### 有视频但没有可用文字怎么办？

可使用本机已有的 `dy-note`、Qwen3-ASR、Whisper 或其他 ASR。若语音识别和画面都不可用，技能会停止，不根据标题或简介编造笔记。

### 提示 “A note for this source already exists” 怎么办？

说明该 URL 已经发布过。技能默认不覆盖旧笔记。可以直接使用已有笔记，或在明确需要更新时手工备份/重命名旧文件后重新执行。

### 发布失败后图片会不会残留？

发布脚本会跟踪本次新创建的图片；在笔记尚未成功写入时发生错误，会删除本次新增图片。已存在并被复用的哈希图片不会误删。

### 中文路径会不会乱码？

脚本显式使用 UTF-8 读写 JSON 和 Markdown，已按 Windows 中文路径验证。终端若显示乱码，不代表文件字节损坏；应使用 UTF-8 方式重新读取并验证实际文件。

### 可以保存到多个 Obsidian 库吗？

默认配置对应一个库。需要切换时重新运行 `configure.py`，或通过 `DOUYIN_OBSIDIAN_NOTE_CONFIG` 为不同库指定独立配置文件。

---

## 验证状态

当前版本已经完成以下验证：

- 技能目录、YAML Frontmatter 和 `agents/openai.yaml` 通过技能结构校验。
- 所有文本文件通过 UTF-8 无 BOM 检查。
- Python 脚本通过语法解析。
- 使用包含中文、空格的 Windows Obsidian 路径完成端到端发布测试。
- 验证 Frontmatter 八个属性、中文文件名、图片哈希命名和 wiki 嵌入路径。
- 验证同名不同来源自动加短哈希。
- 验证同一 URL 重复发布会停止且不覆盖。
- 验证禁用的逐字稿/清单章节会被阻止。
- 验证临时清理会删除本次视频文件，并拒绝删除未带标记的普通目录。
- 验证测试依赖、模拟库、测试草稿和 Python 缓存均已清理。
- 验证 `yt-dlp` 前台与后台命令均使用参数数组，不经过嵌套 PowerShell；含中文、空格、`&` 和字面量 `$env:` 的输入不会被二次展开。
- 验证元数据输出会排除格式直链、Cookie、请求头和签名视频 URL。

---

## 项目来源与设计说明

本技能的取证与证据分层思路参考开源项目 [Rimagination/dy-note](https://github.com/Rimagination/dy-note)。本仓库版本专门收敛为“单条抖音视频 → 关键画面学习笔记 → Obsidian”的通用 Agent 工作流，重点补充了首次路径配置、Obsidian 属性、哈希图片命名、防覆盖发布和受保护临时清理。

如果希望扩展批量账号研究、评论洞察、完整字幕资产或话题分析，请直接使用上游 `dy-note` 的完整能力；如果只想把一条视频沉淀成容易阅读和复习的 Obsidian 图文笔记，使用本技能即可。
