# 抖音/小红书平台访问与媒体判断（无内置浏览器模式）

## 工具适配与无内置浏览器约定

此流程描述能力，不绑定某家 Agent API。**本技能全流程在命令行及 Python 脚本中完成，不调用 Browser Subagent 或任何内置网页浏览器。**

优先级顺序：本地轻量 HTTP 解析与双平台 SSR 元数据及媒体自动落盘 (`sources.py --resolve` / `extract_metadata.py --download-media`) → 平台公开 CDN 单文件或批量直接取证 (`fetch_asset.py`) → 用户提供的原帖截图/视频/字幕素材。遇到反爬阻断、登录限制或验证码时，引导用户通过 `manage_cookies.py --platform <douyin|xiaohongshu>` 更新本地 Cookie 或提供原素材，不尝试启动浏览器绕过。

## 解析与定位

1. 从分享文本提取完整 URL；`sources.py` 标准输出只包含分类与去掉签名的规范化链接，不回显签名。若传入 `--run-dir "RUN"`，`sources.py` 会将保留了 `xsec_token` 等临时访问参数的 `access_url` 安全写入 `RUN/resolved_sources.json`，供 `extract_metadata.py` 在本次工作区内完成无浏览器请求，随工作区清理一并销毁。
2. 短链接使用 `sources.py --resolve` 在本地通过标准 HTTP 302 重定向嗅探解析（即使目标页返回 403 也可从重定向响应头提取规范 ID 与访问令牌），无需打开任何浏览器。若轻量解析遇到极端风控阻断，直接提示用户提供展开后的具体作品链接。跳转若不是对应平台原帖域名，则停止。不能把短链直接当永久来源或根据标题推测作品。
3. 只处理用户给定的具体单条作品，拒绝主页作品流、收藏列表或推荐流。
4. 通过 `extract_metadata.py --run-dir "RUN" --url "<访问URL>" --output "RUN/metadata.json" --download-media` 提取正文、作者、可确认的发布日期（`publish_date`）与媒体类型（`media_type`），并将公开 CDN 媒体清单写入 `RUN/metadata.assets.json` 及自动下载到 `RUN/`。`08-11` 不足以证明年份；“编辑于 1 天前”是编辑信息，不是发布时间。不能根据电脑日期补年份。标题写“附地址”但正文只有店名/地区时，不虚构街道门牌。
5. 当 SSR 提取被风控拦截时，提示用户使用 `manage_cookies.py --platform <douyin|xiaohongshu>` 刷新本地 Cookie 或提供本地素材，绝不虚构正文内容，也不枚举账号其它作品。

## 抖音单条视频与图文

- 确认最终规范地址是 `www.douyin.com/video/<id>` 或 `www.douyin.com/note/<id>`；用户页或带 `modal_id` 的分享链接会自动规范化为单条作品地址，但不得枚举账号其它作品。
- 页面简介只作为元数据，不能代替视频口播。`extract_metadata.py` 只在 `metadata.json` 持久化白名单字段，不保存签名直链、Cookie 或请求头；已验证的公开 CDN 媒体清单独立保存在工作区 `metadata.assets.json` 并在 `--download-media` 模式下直接落盘为 `RUN/source.mp4` 或 `RUN/page-XX.jpg`。
- 取得视频后进入 [视频取证与清理](video-workflow.md)：字幕/ASR与实际画面共同支撑内容，候选帧需逐张查看；若为抖音图文（`media_type: "gallery"`），按图文卡片逐张查看。

## 小红书图文与 LIVE

- 通过 `extract_metadata.py --download-media` 解析 `window.__INITIAL_STATE__` 中的 `imageList` 轮播总数（`image_count`），并将全部公开 CDN 图片下载为 `RUN/page-01.jpg`、`RUN/page-02.jpg` 等。结束时比较已查看页码集合与总数。
- 对每张原图记录原顺序和所承载的信息：知识卡片、操作步骤、对照/证据、背景装饰。逐张理解后再选择最终插图；选择少于总数时不能遗漏独立要点。
- LIVE 图文静态部分足够时按图文处理；关键动作仅在 LIVE 动态中出现时查看动态或明确未验证，不能凭一张静态图推断动作。
- 若用户直接提供本地截图代替原图，注明是截图而非原图。不要放大低清图后谎称高清。
- 保留水印与必要署名，不为规避归属而裁切。正文整理为自己的学习摘要，不无必要复制评论个人信息。

## 小红书视频

此分支必须同时阅读 [视频取证与清理](video-workflow.md)，与抖音视频共用字幕/ASR取证、关键帧筛选和最终清理；下列规则限定小红书平台的访问方式。

- 用 `extract_metadata.py` 解析出的 `media_type` 与 ffprobe 探测的实际时长确认视频。图文与视频同时承载信息则使用 `mixed`。
- 下载仅限已经提取到、符合域名白名单（`.xhscdn.com`）的公开平台 CDN 地址；禁止构造签名、破解防盗链或调用未知第三方解析站。`fetch_asset.py` 支持单资源与批量 `"assets"` 数组下载，并校验 HTTPS、公网 IP 与 MIME 类型。
- 视频下载后用 ffprobe 验证，而不是只看 `.mp4` 扩展名。
- 原字幕/本地 ASR可作为临时证据。使用云 ASR 前说明将上传视频/音频并取得用户授权；不默认消耗付费 API。ASR错字要结合画面修正，仍存疑则标注。
- 无可靠口播证据，只能写视觉笔记并标注边界。仅标题/封面不构成视频知识笔记；只听口播又不查看画面也不能称为图文分析。
- 均匀抽帧不保证覆盖快速闪现步骤。理解内容后按时间补帧，去除重复镜头/转场/模糊图；每张入选帧写清“支持哪项说明”。默认抽帧宽度不超过 1920 且不放大。

## 收尾与范围

本技能不收集两平台的主页/收藏列表，不记录个人收藏地址，不检查新增内容，也不根据账号推荐其它作品。设计验证时的样本不进入默认配置。全流程无浏览器运行，仅清理此次工作区，不动用户既有文件。
