# 目录与数据契约

本技能自带脚本适用于 schema_version 1。旧库结构不同时先确认映射与必要迁移，不覆盖旧清单。

## 新库最小布局

```text
<collection>/
├── README.md
├── imported_sources.json
└── tools/
    └── <slug>/
        ├── README.md
        ├── UPSTREAM.md
        ├── snapshot-manifest.json   # 仅 snapshot 模式
        └── source/                  # 仅 snapshot 模式
```

空库先创建 tools 目录和 `{"schema_version":1,"imported_urls":{}}` 清单。README 需含且仅含一组按顺序排列的标记：

```markdown
# 实用工具收藏

<!-- catalog:start -->
<!-- catalog:end -->
```

添加完整条目后，用技能自带脚本 render、check。空库也可 render；没有工具时 Git 不跟踪空目录，检查前需在工作副本创建 tools 目录。无需向目标库复制技能或维护脚本。

## 单条记录示例

下面是结构示例，提交 SHA 和日期须替换为真实核验值；不能把占位数据当作取证结果。

```json
{
  "schema_version": 1,
  "imported_urls": {
    "https://github.com/owner/repo": {
      "tool_name": "repo",
      "display_name": "工具名称 · 中文用途",
      "category": "文件传输",
      "summary": "核心功能",
      "scenario": "适用场景",
      "platforms": ["Windows"],
      "mode": "guide-only",
      "ref": "实际版本或分支",
      "commit": "替换为上游实际40位小写提交SHA",
      "license": "实际 SPDX 标识；未核实则写 unknown",
      "imported_at": "2026-09-09T12:00:00+08:00",
      "checked_at": "2026-09-09T12:00:00+08:00",
      "verification": "仅文档核验，未安装实测"
    }
  }
}
```

更新添加 updated_at，保留 imported_at。来源键使用小写 canonical HTTPS 仓库地址，不包含 .git、query、fragment 或 tree 路径。名称变更先核验重定向并检查旧记录；脚本只做语法规范化，不联网解析改名。

README 与 UPSTREAM.md 两种模式均需存在。guide-only 不应有 source/。snapshot 的摘要覆盖 source 中所有普通文件，类型与链接规则见 [收录规范](collection-policy.md)。未查询到真实 commit 时只能作为待核验草稿，不伪造 SHA 通过检查。

## 人工检查补充

脚本检查清单、目录、摘要与首页索引，不能确认事实来源、许可证适用性或运行效果。发布前仍需核对具体指南中的命令、平台信息与原项目链接，并比对所选 commit；不要只用脚本成功作为发布依据。
