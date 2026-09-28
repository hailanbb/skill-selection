# 来源与发布范围

- 项目：本仓库个人开发的 CloudDrive2 剧集整理助手，不是第三方仓库镜像。
- 版本：0.5.1；整理日期：2026-09-29。
- 来源：本次开发的已验证工作区源码；发布副本将实际站点替换为 `clouddrive.example`，并将内部 origin 校验和报告链接归到 `CLOUD_ORIGIN` 配置。
- 保留：安装文件、源码、构建脚本、5 份测试、所需第三方构建文件和许可证。
- 排除：个人扫描报告、原始会话、凭据、旧数据库、Obsidian 归档及附件、工作区临时脚本和依赖压缩包。
- 不存在可引用的外部上游 commit；版本来源以本目录 Git 历史为准。`snapshot-manifest.json` 记录本次源码、构建、测试和依赖文件的 SHA-256。
- 沿用本仓库 `script-tools/` 布局与手工索引，不创建面向第三方收藏库的 `imported_sources.json`，不重写其他分类。

## 第三方依赖

| 组件 | 版本 | 来源与许可 |
| :--- | :--- | :--- |
| OpenCC-js | 1.4.2 | [来源记录](vendor/provenance.json)、[LICENSE](vendor/package/LICENSE)、[第三方声明](vendor/package/THIRD_PARTY_LICENSES.md) |
| xlsx-js-style | 1.2.0 | [来源记录](vendor/xlsx-js-style/provenance.json)、[LICENSE](vendor/xlsx-js-style/package/LICENSE)、[分发许可](vendor/xlsx-js-style/package/dist/LICENSE) |

第三方许可证也嵌入安装文件。原项目代码不新增授权声明；不能将第三方许可推定为整个脚本的许可。

## 验证

发布副本构建、语法检查及 56 项测试通过。已检查上传范围与 UTF-8；不包含个人站点、报告或凭据。浏览器实地整分类与 Excel/WPS 界面仍未验证，详见使用指南。
