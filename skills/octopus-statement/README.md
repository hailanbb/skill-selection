# 八达通详单

将本地八达通长截图裁剪并转为消费 Excel。显示名称为“八达通详单”，技术标识和目录名为 `octopus-statement`。

默认从第一笔交通费用补贴开始去掉下方内容，图片保留上方的正数交易，Excel 排除正数、保留零金额。表格所有列居中、支持筛选，**不冻结表头或列**。原图保留，每次独立输出。

## 安装与调用

将整个 `octopus-statement` 文件夹复制到客户端的技能目录。Codex 默认使用 `~/.codex/skills/`，项目级技能可使用 `.agents/skills/`；不要把本仓库的 Agent 规则文件一并复制。

示例：

> 使用八达通详单处理本地“八达通消费记录_日期.jpg”，裁去交通费用补贴及以下内容，再把不带“+”的记录转为 Excel。

也可指定：保留到某笔记录、没有补贴时处理全图、输出目录。用户当次明确指令优先。

## 脚本输入

图片识别由调用技能的 Agent 完成，脚本不提供 OCR。先查看、复核截图，再生成 UTF-8 JSON。所有坐标按原图像素计，顶部包含、底部不包含。相邻交易坐标不重叠。输入可以包含裁剪边界下方记录，脚本会排除。

```json
{
  "cutoff_y": 700,
  "card_number": "示例卡号",
  "screenshot_balance": "73.5",
  "records": [
    {"top": 200, "bottom": 300, "datetime": "2026-10-13 14:54", "party": "港鐵", "amount": "-5.9"},
    {"top": 300, "bottom": 400, "datetime": "2026-10-13 13:59", "party": "八達通卡有限公司", "amount": "+300.0"},
    {"top": 400, "bottom": 500, "datetime": "2026-10-13 11:16", "party": "九巴／龍運", "amount": "0.0"},
    {"top": 500, "bottom": 600, "datetime": null, "party": "港鐵", "amount": null, "note": "日期和完整金额截断，待核对"}
  ]
}
```

- `cutoff_y` 是第一笔补贴上方的裁剪边界，不是补贴文字中心。没有补贴且无需其他边界时写 `null`，保留全图。
- `amount` 用带符号十进制字符串，保留原图精度。`+0.0` 也按带“+”交易排除。缺失写 `null` 并说明 `note`，不得用 `0` 代替。
- `datetime` 必须为 `YYYY-MM-DD HH:mm`，无法识别写 `null` 并说明 `note`。本地字面时间不转为 UTC 时间。
- `card_number` 是可选文本标识，不自动转数字；`screenshot_balance` 可选，只代表截图显示余额，不参与裁剪后消费汇总。
- 记录必须自上而下按原图排序。脚本拒绝跨越裁剪边界的记录、重叠坐标、无效日期和非法金额。

执行准备和无损裁剪（程序名替换成当前环境获准运行时）：

```text
python scripts/prepare.py --source <本地截图> --input <识别结果.json> --output-dir <本次输出目录>
```

生成裁剪 PNG 及 `prepared.json`，已存在同名文件时拒绝覆盖。支持中文和空格路径。

## Excel 生成与依赖

准备脚本依赖 Python 3.10+ 与 Pillow。Excel 脚本依赖 Node.js 和 `@oai/artifact-tool`。在 Codex 内使用 `load_workspace_dependencies` 提供的运行时，不修改全局依赖，不将 `node_modules` 提交到仓库。

按照当前表格技能要求，在本次临时工作目录复制 `scripts/write_workbook.mjs`，连接已提供的运行时依赖后执行：

```text
node write_workbook.mjs --input <prepared.json> --output <本次输出目录/详单.xlsx> --preview <临时工作目录/preview.png>
```

有未知字段时备注列显示缺失原因。未知金额单独计数、排除于金额合计；同一时刻的不同记录不会自动去重。保留日期与金额的可计算类型，序号连续编号；表头不冻结。

脚本会计算并检查汇总、扫描公式错误、导出及生成预览。Agent 仍需核对截图识别结果和目视预览。脚本验证不能证明 OCR 正确，也不代替真实 Excel／WPS 的应用兼容性测试。

## 验证

```text
python -m unittest discover -s tests -v
python tests/verify_workbook.py <prepared.json> <已生成.xlsx>
```

测试只使用合成图片与记录，覆盖裁剪像素、首个截止边界、无补贴全图、正数和零金额过滤、未知金额、日期校验及防覆盖。发布包不包含真实截图、卡号、消费记录或工作簿。
