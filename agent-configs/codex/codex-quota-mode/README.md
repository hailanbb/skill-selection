# Codex 全局省额度开关

**OpenAI Codex 专用 Skill**，属于「Agent 配置与行为规范」。开启采用 **GPT-6 Astra / high** 统筹、**GPT-5.6 Luna / medium** 按需执行；关闭恢复开启前的设置。它不承诺固定节省比例。

[技能指令](SKILL.md) · [分析与设计](references/design.md) · [Codex 配置分类](../README.md)

## 全局安装

需要 Python 3.11+ 和支持相应模型、子 Agent 的 Codex 环境。TOML 编辑依赖已随技能附带，无需额外 pip 安装。

1. 将本目录 **codex-quota-mode 整个文件夹** 复制到 Codex 全局技能目录：Windows 默认 `%USERPROFILE%\.codex\skills\`；macOS/Linux 默认 `~/.codex/skills/`。若设置了 `CODEX_HOME`，使用 `<CODEX_HOME>/skills/`。
2. 确认最终文件为 `<CODEX_HOME>/skills/codex-quota-mode/SKILL.md`，并保留 `scripts/vendor/`、`assets/`、`agents/` 和 `references/`。
3. 新开 Codex 会话发现技能，先说“查询省额度模式”。也可显式调用 `$codex-quota-mode`。
4. 安装不会自动开启；需要时说“开启省额度模式”。已有同名技能时先备份再更新，且不要在切换事务未完成时替换脚本。

此技能是 Codex 的全局配置开关，不使用仓库其他技能的 Gemini 安装路径。不需要覆盖你的全局 AGENTS.md，也不依赖安装旁边的 AGENTS.md 模板。

## 日常口令

| 口令 | 行为 |
| --- | --- |
| 开启省额度模式 | 保存当前基线，写入 Astra/high、Luna/medium、子线程上限 2，并追加全局调度规则 |
| 关闭省额度模式 | 恢复开启前六个配置值，移除模式规则，保留期间的无关修改 |
| 查询省额度模式 | 查看保存模式、配置一致性、覆盖文件和重载提示 |

重复开启或关闭不会重复插入规则或覆盖最初备份。小任务直接由主 Agent 完成；复杂任务按收益选择 Luna，不机械启动五个角色。

## 生效与恢复

- **全局默认不等于当前窗口即时切换。** 新会话或重启后加载；UI、项目、profile、命令行和平台设置可能覆盖它。脚本不强行切换已运行的模型。
- 关闭恢复的是每个人开启前的配置，可能是 medium，也可能是其他模型或未设置状态，不固定恢复到 medium。
- 状态及备份在 `<CODEX_HOME>/quota-mode/`。期间未改动时恢复原字节；有无关改动时按键恢复并保留其他设置。受管键或规则块被手改时拒绝覆盖，先处理提示的冲突。
- 中断事务可用脚本的 `recover` 恢复；先查询状态，且不要自动删除仍可能由运行进程持有的锁。备份可能含原配置私有内容，只存本地，不上传。
- 不改变审批、沙箱或 MCP 设置，不重置或购买额度。high 推理和多 Agent 协调仍有成本，订阅配额不能按 API 价格直接换算。

需要手动诊断时，将下面的 `<CODEX_HOME>` 替换为你的实际绝对路径，在本技能目录运行：

```text
python scripts/quota_mode.py status --codex-home "<CODEX_HOME>"
python scripts/quota_mode.py on --codex-home "<CODEX_HOME>"
python scripts/quota_mode.py off --codex-home "<CODEX_HOME>"
```

命令使用你环境中实际可用的 Python 3.11+ 可执行文件；stdout 为可解析的 JSON。

## 验证与依赖

隔离目录中的 14 项开关测试和 1 项输出编码检查通过，另经 Luna 独立前向测试验证用户修改保留。测试不写真实全局配置：

```text
python scripts/test_quota_mode.py
python scripts/test_output.py
```

未以这些测试声称跨所有客户端热加载或固定额度收益已验证。随附 tomlkit 0.15.1，许可证见 [TOMLKIT-LICENSE](scripts/vendor/TOMLKIT-LICENSE)。
