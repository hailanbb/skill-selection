# GitHub 工具收藏技能

将一个 GitHub 链接整理成 `hailanbb/tools` 中可查、可用、可追溯的收藏条目。沿用中文分类表和两阶段指南，增加版本固定、来源去重、许可证保留、原文与指南分离及摘要校验。

## 安装

把本目录整体复制到 Codex 的 `$CODEX_HOME/skills/github-tools-collect/`；未设置 CODEX_HOME 时使用 `~/.codex/skills/github-tools-collect/`。Windows 通常为 `%USERPROFILE%\.codex\skills\github-tools-collect\`。新会话中确认技能可见。其他 Agent 使用其支持的技能路径。

依赖：GitHub CLI（`gh`，已有授权）或可用 GitHub 连接器；Git 用于源码与工作副本；Python 3.10+ 用于校验。不需要额外 Python 包，不在配置文件中保存 Token。

## 直接使用

```text
用 $github-tools-collect 把 https://github.com/localsend/localsend 收藏到 hailanbb/tools。
用 $github-tools-collect 更新 tools 中的 LocalSend 到最新正式版。
用 $github-tools-collect 只检查 tools 的来源清单、索引和源码完整性。
用 $github-tools-collect 收藏这个仓库，只写中文指南，不复制源码：<链接>。
```

目标默认已设置为 `hailanbb/tools`，无需重复配置。更换目标时明确说出新仓库。仅要求设计或草稿时不会发布；明确要求收藏到指定仓库时，在该范围内完成推送。

## 产物与验证

每条工具有中文 README、UPSTREAM 来源说明；源码模式另有 source 和摘要清单。校验脚本检查重复来源、目录对应、固定提交格式、索引一致性和快照文件哈希。它不联网验证项目宣传、不证明程序能运行，也不评估软件安全性。

技能保存在 `skill-selection`；普通软件收藏保存在 `tools`，两者独立。校验脚本统一放在目标库 `scripts/`，无需复制到本技能。脚本用法及收录约定见[工具库维护说明](https://github.com/hailanbb/tools#collect)和[完整规范](https://github.com/hailanbb/tools/blob/main/docs/collection-policy.md)。
