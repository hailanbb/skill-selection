# 多平台视频嗅探、逆向解析与下载策略

本文档指导 AI Agent 如何从各类网页与流媒体平台稳定提取并下载高质量视频源。

---

## 1. 常见平台与解析层级矩阵

```text
[输入 URL]
   │
   ├─► 通用已知平台 (YouTube / Bilibili / 抖音 / 微博 / X)
   │     └─► 直接调用 yt-dlp: yt-dlp "<URL>" -o "video.mp4"
   │
   └─► 专有新闻/流媒体门户 (如 Now 新闻、TVB、各类政企独立播放器)
         │
         ├─► 步骤 1: 静态 HTML 嗅探 (扫描 <video src="...">, <source>, JSON 数据块)
         ├─► 步骤 2: 动态播放器逆向 (提取 MediaPlayer.js / player 逻辑，查找 getVodURL / checkout 接口)
         └─► 步骤 3: HLS (m3u8) / MP4 真实流地址下载: yt-dlp "<m3u8-url>" 或 ffmpeg
```

---

## 2. 专有流媒体门户逆向解析实例（以 Now News 为例）

当通用解析器无法直接通过主页面 URL 抓取视频时，采用以下逆向三步法：

### 第一步：定位页面核心播放器逻辑
1. 抓取网页源码，检索关键字：`MediaPlayer`、`checkout`、`vodUrl`、`m3u8`、`hls`、`player`。
2. 发现页面引用的播放器核心脚本（如 `/revamp2014/js/MediaPlayer.js`）。

### 第二步：分析视频流鉴权接口
通过审查 `MediaPlayer.js` 中的 `checkout` 方法，提取其异步接口参数契约：
```http
GET https://d1jithvltpp1l1.cloudfront.net/danielVod.php?vodPath=/getnowmediahls//sd/index.m3u8&mode=prod&audioCode=&format=HLS&callerReferenceNo=20140702122500&newsid={newsId}&quality=abr&site=nnew
```
服务端直接返回包含真实 `m3u8` 的 JSON 响应：
```json
{
  "asset": "https://news-videos.now.com/nownews/667405/hls/667405.m3u8",
  "responseCode": "SUCCESS"
}
```

### 第三步：全量分片合并下载
使用 `yt-dlp` 对 m3u8 地址进行多线程分片抓取与 TS 流封装修复：
```bash
yt-dlp "https://news-videos.now.com/nownews/<newsId>/hls/<newsId>.m3u8" -o "video.mp4"
```

---

## 3. 音视频属性自检指令

下载完成后，必须使用 `ffprobe` 快速读取视频基本元数据，为后续字幕字号计算提供依据：
```bash
ffprobe -v error -show_entries stream=width,height,duration -of json "video.mp4"
```
- 读取到 `width` 与 `height`（如 1280x720 或 1920x1080）；
- 根据 `height` 立即确定后续字幕渲染的最佳字号。
