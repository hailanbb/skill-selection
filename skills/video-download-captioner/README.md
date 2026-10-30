# 视频下载与智能字幕压制技能 (Video Download & Captioner)

基于 [VideoCaptioner](https://github.com/WEIFENG2333/VideoCaptioner)、`yt-dlp` 与 `ffmpeg` 的一站式 AI 视频处理与字幕工坊。支持任意网页/流媒体视频嗅探下载、多方言精准语音识别、方言口语转标准简体书面语精修、以及符合影视工业级规范的自适应字幕高清压制。

---

## 🌟 核心特性

- 🌐 **全网视频嗅探与逆向下载**：不仅支持 YouTube、B站、抖音等常见平台，还能逆向解析复杂流媒体新闻门户（如香港 Now 新闻台、TVB、各类网页 HLS/m3u8 分片）。
- 🎙️ **多方言 ASR 引擎智能分流**：
  - 粤语（广东话/香港口语）：智能调度**剪映 ASR**，杜绝普通话谐音识别乱码；
  - 标准普通话：调度**必剪 ASR** 或剪映，高速免费免 Key；
  - 多语种/外语：无缝对接 Whisper 体系。
- ✍️ **粤语口语转规范中文简体**：自动识别本字（𫪈、咗、噉、嘅、㖞等），精准转换为通顺规范的现代书面语，并对齐专有名词（如修正“医程通”为“医承通”）。
- 📐 **工业级字幕比例与防眩光设计**：
  - 摒弃死板小字号，根据视频分辨率自适应计算字高（$H \times 5.8\%$，720p 对应 42px，1080p 对应 60px）；
  - 纯黑 2.2px~3.2px 加厚描边，在浅色背景下字体清晰不发虚；
  - 自动避让电视台底部新闻滚动条与操作控制条。
- 📦 **软硬字幕双交付**：一键生成全设备兼容的硬字幕压制视频，以及保留原画质内嵌轨道的软字幕视频与独立标准 SRT 文件。

---

## 📂 技能目录结构

```text
video-download-captioner/
├── SKILL.md                 # AI Agent 执行核心指令
├── README.md                # 技能安装、配置与使用说明（本文件）
├── agents/
│   └── openai.yaml          # Agent 展示元数据配置
├── references/
│   ├── subtitle-standards.md # 影视与流媒体字幕工业级排版规范
│   ├── asr-engine-guide.md   # ASR 选型指南与粤语口语规范转化对照表
│   └── platform-download.md  # 专有流媒体门户与 m3u8 逆向抓取指引
└── scripts/
    ├── init_styles.py        # VideoCaptioner ASS 字幕样式预设初始化脚本
    └── burn_subtitles.py     # 基于分辨率自适应计算字号的字幕烧录脚本
```

---

## 🛠️ 环境准备与快速上手

### 1. 安装核心依赖
本技能依赖 Python 3.10+、`ffmpeg`、`yt-dlp` 及 `videocaptioner`：
```bash
pip install videocaptioner yt-dlp
# 确保系统已安装 ffmpeg 与 ffprobe 并加入 PATH 环境变量
```

### 2. 初始化字幕工业级样式预设
初次使用前，可一键注入 720p 与 1080p 标准高对比度字幕样式：
```bash
python scripts/init_styles.py
```

### 3. 一键字幕压制命令示例
使用技能内置脚本自动计算分辨率最佳比例进行压制：
```bash
# 自动检测分辨率并烧录硬字幕
python scripts/burn_subtitles.py input.mp4 subtitle.srt

# 压制软字幕（原画内嵌轨道）
python scripts/burn_subtitles.py input.mp4 subtitle.srt --mode soft
```

---

## 📖 典型处理工作流示例

以香港 Now 新闻台视频（粤语口播）为例：
1. **下载视频**：通过解析 `danielVod.php` 接口获取 m3u8，调用 `yt-dlp` 下载为 `now_news.mp4`；
2. **剪映 ASR 转录**：
   ```bash
   videocaptioner transcribe now_news.mp4 -o raw.srt --asr jianying
   ```
3. **书面语优化**：将口语词（“𫪈立法会”、“开咗会”）精修为规范汉语（“在立法会”、“开了会”），保持 SRT 时间轴不变，生成 `simplified.srt`；
4. **高质量压制**：调用 `burn_subtitles.py`，自动选用 42px 大字号与 2.2px 黑色轮廓描边完成压制。

---

## 🤝 贡献与许可

- 本技能遵循 MIT 许可证发布。
- 欢迎在 [skill-selection](https://github.com/hailanbb/skill-selection) 提交 Issue 或 PR 持续优化多平台解析与字幕样式！
