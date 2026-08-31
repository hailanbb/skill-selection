# 取证与关键帧流程

## 取证路由

流程借鉴 `https://github.com/Rimagination/dy-note` 的证据分层，但只为最终图文笔记收集最小充分材料。

按以下顺序复用：

1. 用户提供的本地视频、SRT/VTT/TXT 或已有 ASR 结果。
2. 页面可见的标题、作者、发布时间、简介和独立字幕轨。
3. 本机已安装的 `dy-note` 脚本或其他本地 ASR；中文优先适合中文的本地模型。
4. 视频关键帧与必要的画面文字识别。

页面简介不是字幕，ASR 也无法读取焊在画面里的字幕、贴纸、价格或操作界面。依赖画面的结论必须查看所选帧；高风险事实另外使用权威来源核验。

所有下载、音频、转写、候选帧和辅助 JSON 都写入 `run_workspace.py create` 返回的目录。不要在工作区或 Obsidian 库中散落中间文件。

## yt-dlp 元数据

需要通过 `yt-dlp` 获取标题、作者、发布时间等元数据时，使用技能自带助手。前台执行：

```powershell
python scripts/extract_metadata.py --url $sourceUrl --output "$runDir\metadata.json"
```

确实需要后台执行时：

```powershell
python scripts/extract_metadata.py --url $sourceUrl --output "$runDir\metadata.json" --background
```

后台命令返回 PID、状态文件和日志文件。轮询状态文件，状态会从 `starting`/`running` 进入 `succeeded` 或 `failed`；只有 `succeeded` 后才读取输出，`failed` 时查看临时日志并报告 `yt-dlp` 的实际错误。状态、日志和元数据都必须留在本次临时目录，最终随运行目录清理。

不要使用以下易损模式：

```powershell
# 错误示例：父 PowerShell 会提前展开或丢失嵌套字符串中的 $env:...
Start-Process powershell -ArgumentList '-Command', "yt-dlp ... $env:SOME_PATH ..."
```

助手通过参数数组直接启动 `yt-dlp` 或 Python 子进程，不使用嵌套 `powershell -Command`、字符串拼接或 `shell=True`，因此 URL、中文路径、空格、`&` 和环境变量展开不会跨两层 PowerShell 重新解释。它只持久化白名单元数据，不保存格式直链、Cookie、HTTP 请求头或带签名的视频 URL。

如果调用上游 `dy-note`：

- 把 `--out-dir` 指向本次临时目录下的子目录。
- 优先复用本机现有安装或缓存，不重复安装 ASR 环境。
- 只读取其转写、片段和元数据来写笔记；不要把原始包归档到 Obsidian。
- 不在日志或笔记中保存 Cookie、token、签名视频 URL 或浏览器存储。

## 候选帧

先均匀抽取 12–24 个候选帧：

```powershell
python scripts/extract_keyframes.py --video "<临时视频>" --out-dir "<临时目录>\candidates" --auto-count 16
```

已从转写或章节定位到关键时刻时，可直接指定时间：

```powershell
python scripts/extract_keyframes.py --video "<临时视频>" --out-dir "<临时目录>\selected" --at 00:00:03.5 --at 00:00:27 --at 00:01:12
```

逐张查看候选帧，结合相邻转写/章节选择最终画面。优先级从高到低：

1. 直接展示核心概念、步骤、菜单、表格、操作界面或结果对比。
2. 能补足仅靠声音无法理解的关键视觉信息。
3. 对应笔记中明确讨论的案例、动作或物体。
4. 可作为封面且能准确代表主题的清晰画面。

排除：黑屏、片头片尾、二维码/广告、重复构图、字幕被遮挡、严重运动模糊、与笔记无关的情绪帧。相邻帧表达相同信息时只保留更清晰的一张。

## 写作闸门

动笔前确认：

- 核心结论能由字幕/ASR、页面元数据或画面支持。
- 每个视觉描述都能指向一张实际查看过的帧。
- 专有名词、人名、数字和价格没有仅凭 ASR 猜测。
- 笔记可以不依赖完整逐字稿独立读懂。

证据不足时缩小结论，不补故事。视频内容本身包含明显违法、危险或误导操作时，遵循宿主 Agent 的安全规则。
