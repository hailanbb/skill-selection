# 脚本输入与取证契约

辅助程序不直接调用大模型，不自动登录小红书。Agent 负责合法获取材料、实际看图/视频和写学习摘要；脚本负责路径、文件、去重、图像解码和归档校验。以下命令里的 `python` 均应替换为当前环境验证过的 Python 3.10+；以技能目录为工作目录，或把脚本换成绝对路径。

## 1. 工作区与取图

```text
python -X utf8 scripts/run_workspace.py create
```

读取 JSON 中 `run_dir`，以下 `RUN` 均指该实际绝对路径，不是 shell 环境变量。Agent 把已观察的 CDN 地址写入工作区 `asset-request.json`：

```json
{"url":"https://实际已观察的平台CDN主机/实际资源路径","platform":"xiaohongshu","kind":"image","filename":"page-01.jpg"}
```

```text
python -X utf8 scripts/fetch_asset.py --request "RUN/asset-request.json" --run-dir "RUN"
python -X utf8 scripts/extract_keyframes.py --run-dir "RUN" --video "RUN/source.mp4" --out-dir "RUN/frames" --auto-count 16
python -X utf8 scripts/extract_keyframes.py --run-dir "RUN" --video "RUN/source.mp4" --out-dir "RUN/selected" --at 00:12 --at 01:05
```

抖音确实需要 yt-dlp 白名单元数据时可执行：

```text
python -X utf8 scripts/extract_metadata.py --run-dir "RUN" --url "抖音具体视频URL" --output "RUN/metadata.json"
python -X utf8 scripts/extract_metadata.py --run-dir "RUN" --url "抖音具体视频URL" --output "RUN/metadata.json" --background
```

后台模式直接启动 Python worker，不嵌套 PowerShell；轮询返回的状态文件，只有 `succeeded` 才读取元数据。状态、日志和输出仍须位于 RUN 并随最后清理。小红书不默认使用此助手。

URL 示例是占位结构，不能执行。`platform` 取 `douyin` 或 `xiaohongshu`，并须与已观察地址相符。下载器只做单资源有界下载：图片 50 MiB、视频 512 MiB，上限之外改用获授权的客户端保存；不回显 CDN 签名，不读取 Cookie，遇非平台 CDN 重定向/非公开 IP/登录页/已存在目标就停止。必须核验字节内容与实际画面，不能以下载成功当取证完成。图片只接受真实静态 JPEG/PNG/WebP；动画需要先提取代表性静帧并查看。候选帧不自动进入笔记。

## 2. evidence.json

在同一工作区创建以下 UTF-8 对象；日期未知用空字符串。所有例子为虚构：

```json
{
  "source_url": "https://www.xiaohongshu.com/explore/0123456789abcdef01234567",
  "title": "番茄盆栽的浇水判断与光照安排",
  "author": "示例作者",
  "publish_time": "",
  "media_type": "gallery",
  "content_basis": "text_and_images",
  "gallery_coverage": {"expected_count": 2, "reviewed_positions": [1, 2]},
  "limitations": [],
  "assets": [
    {"path": "page-01.jpg", "role": "image", "position": 1, "inspected": true, "caption": "原帖第 1 图：观察土壤状态的判断位置。"},
    {"path": "page-02.jpg", "role": "image", "position": 2, "inspected": true, "caption": "原帖第 2 图：不同摆放位置的光照对比。"}
  ]
}
```

`source_url` 须为已确认的抖音单条视频或小红书具体笔记 URL，最终归档会规范化并去掉签名。不要把账户收藏 URL、主页、短链或图片 CDN URL当来源。抖音只使用 `media_type: "video"`；小红书可用 gallery/video/mixed。

视频改为 `media_type: "video"`，添加 `video_reviewed_to_end: true` 和实际核实的 `video_duration_seconds`（例如 `138`）；`content_basis` 选 `subtitles_and_frames`、`asr_and_frames` 或 `visual_only`。帧的 asset 使用 `role: "frame"` 和 `timestamp_seconds: 12.5`，不使用图文页码，且必须小于视频时长。`mixed` 需同时满足图文覆盖和视频查看，入选素材同时包含 image 与 frame。时间戳必须真实对应本次视频，不能填估计值。

`assets` 是**最终入选**图片，图文 `reviewed_positions` 是**实际已看**页码；两者可以不等长。路径必须在带安全标记的本次工作区内，外部素材先复制而不是移动。`inspected` 只是取证记录，Agent 必须先实际查看。有限覆盖时 `limitations` 写缺失原因，待用户接受局部笔记后才发布。

## 3. draft.md 与发布

草稿只写正文，不写 YAML，不用现成图片链接。序号按 `assets` 的顺序从 1 开始：

```markdown
# 番茄盆栽的浇水判断与光照安排

这篇笔记根据原帖说明整理……（此处必须替换为有依据的摘要）

## 判断浇水时机

具体判断方式及条件……

{{image:1}}

## 安排光照位置

具体说明与限制……

{{image:2}}
```

```text
python -X utf8 scripts/publish_note.py --manifest "RUN/evidence.json" --draft "RUN/draft.md" --run-dir "RUN"
python -X utf8 scripts/validate_note.py --note "发布返回的绝对笔记路径"
python -X utf8 scripts/run_workspace.py cleanup --path "RUN"
```

每张入选图片必须有占位符；未引用、越界、无效图片、现成/外链图片、目录逃逸、签名泄漏、完整逐字稿标题都会中止。发布程序不负责清理工作区，Agent 必须在最后执行 cleanup；发布前失败也要清理，除非用户要求保留续作。

视频选图确实无需高清时可加 `--frame-width 640`；默认 0 保留已取帧尺寸。`--allow-partial` 只用于用户明确接受局部材料，不是普通故障的默认重试参数。

## 4. 状态、失败与重复

- `published`：新笔记写入，返回路径、图片列表与限制。再次验证、看最终图片后交付。
- `skipped_existing`：同一原帖 ID 已在配置的笔记目录（含子目录）中归档；不会更新旧文。签名不同、标题不同也不重复。若用户已把旧文移出该目录，去重不覆盖整个库；可在明确授权后把配置笔记目录设为共同上层，或先查库。
- 非零退出：不得宣称成功。常见原因是没有配置、漏图、无效图片、链接非笔记、文件系统权限或缺 Pillow。
- 独占锁位于库根 `.douyin-xiaohongshu-obsidian-note.publish.lock`。有锁时不启动第二个发布。异常断电可能留锁：核对锁内 PID、启动时间与相关进程并确认已无发布运行后才能清理**该锁文件**，不要自动按年龄删锁。
- 先写临时 MD 并读回，再用硬链接原子提交、拒绝覆盖；要求 NTFS/APFS/ext4 等支持硬链接的文件系统。FAT/exFAT 或某些网盘挂载可能不支持，会安全失败，不静默降级到覆盖写入。失败回滚本次新增图片，复用已有图片不会删除。
- 用户强制终止进程/断电时无法保证 finally 执行；残留工作区只在标记一致时清理，残留笔记目录 `.social-note-publish-*.tmp` 和库锁须逐个确认归属，绝不能通配清除用户文件。
