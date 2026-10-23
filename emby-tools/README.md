# emby工具

收录Emby媒体库相关的剧集整理、补缺下载、归档及MoviePilot订阅维护工具。独立于Agent配置、Skills与通用Script Tools。

| 工具名称 | 适用环境 | 核心功能 | 文件与说明 |
| :--- | :--- | :--- | :--- |
| **剧集整理工作流(后端)** | **Windows 11 / Ubuntu 24 + Node.js** | 四阶段API后端，CloudDrive2 / MoviePilot / TMDB接口、持久化计划与日志、Excel报告衔接。 | [项目与源码](tv-season-workflow-backend/README.md) · [从零安装](tv-season-workflow-backend/INSTALL.md) · [接口与使用](tv-season-workflow-backend/docs/API.md) |
| **剧集整理工作流(油猴版)** | **Chrome + Tampermonkey + CloudDrive2 / MoviePilot** | ① 初检 → ② 补缺下载 → ③ 复核清理 → ④ 归档；Excel衔接，逐项记录下载、删除和移动。 | [项目与四个脚本](tv-season-workflow/README.md) · [从零安装](tv-season-workflow/INSTALL.md) · [报告与追溯](tv-season-workflow/REPORT.md) |
| **MoviePilot订阅批量取消脚本 · v2.4.0** | **Chrome + Tampermonkey + MoviePilot** | 电影批量取消；电视剧零进度取消、未完成订阅维护、跳过名单、资源筛选及结果导出。 | [安装脚本](moviepilot-unsubscribe/moviepilot-unsubscribe.user.js) · [配置与使用](moviepilot-unsubscribe/README.md) |

两个油猴工具原位于Script Tools，本次完整迁入本分类；版本与业务代码保持不变。各工具需配置自己的站点，安装或导入后默认不执行外部写入。

[← 返回个人开发首页](../README.md)
