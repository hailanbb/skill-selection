# 🧰 脚本工具 (Script Tools)

收录个人开发与维护的实用脚本。独立于 [Agent 配置与行为规范](../README.md#-agent-配置与行为规范-agent-configuration) 和 [精选技能索引](../README.md#️-精选技能索引-skills-directory)，按各工具指南安装与配置。

| 脚本名称 | 适用环境 | 核心功能 | 文件与说明 |
| :--- | :--- | :--- | :--- |
| **① CloudDrive2 剧集初检 · v1.1.1** | **Chrome + Tampermonkey + CloudDrive2** | 按季只读核对；TMDB 主查、豆瓣缓存/限速补查；绿/蓝 Excel 报告、暂停与进度恢复。 | [安装脚本](tv-season-workflow/season-inspect.user.js) · [从零安装](tv-season-workflow/INSTALL.md) · [完整说明](tv-season-workflow/docs/01-inspect.md) |
| **② MoviePilot 剧集补缺下载 · v1.2.1** | **Chrome + Tampermonkey + MoviePilot** | 导入初检 Excel 后手动下载；整季优先、中文优先、≥5 做种按容量选择；逐资源执行明细。 | [安装脚本](tv-season-workflow/season-download.user.js) · [从零安装](tv-season-workflow/INSTALL.md) · [完整说明](tv-season-workflow/docs/02-download.md) |
| **MoviePilot订阅批量取消脚本 · v2.4.0** | **Chrome + Tampermonkey + MoviePilot** | 电影批量取消；电视剧零进度取消、未完成订阅维护、跳过名单、资源筛选及执行结果导出。 | [安装脚本](moviepilot-unsubscribe/moviepilot-unsubscribe.user.js) · [👉 配置与使用指南](moviepilot-unsubscribe/README.md) |
| **CloudDrive2剧集整理助手 · 只读核对版 v0.5.1** | **Chrome + Tampermonkey + CloudDrive2** | 指定分类逐季核对；TMDB 主查、豆瓣复核未完结，重名检查及 Excel 绿色标记／CSV／JSON 导出，不移动文件。 | [安装脚本](clouddrive2-season-audit/season-audit.user.js) · [👉 配置与使用指南](clouddrive2-season-audit/README.md) |

[← 返回个人开发首页](../README.md)
