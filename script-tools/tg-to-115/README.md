# Telegram 频道 -> CloudDrive2 多 115 定向云下载工具 (`tg-to-115`)

基于 **Telegram MTProto (Telethon)** 与 **CloudDrive2 官方 gRPC API** 的全自动离线云下载与管理面板。纯云端离线下载（不消耗本地带宽），支持多 115 账号按序配额轮转、出演者多语言别名白名单过滤、断点续传、每日 Markdown 归档报表，以及交互式 Ubuntu 数字菜单管理。

---

## 核心特性

- **纯 115 云端离线下载**：仅在内存解析几 KB 的 `.torrent` 种子并转为磁力链接，通过本地 CloudDrive2 gRPC 下发 115 云下载，彻底免除手动维护 115 Cookie 的烦恼。
- **多 115 账号顺序轮转与配额熔断**：
  - 在 `config.json` 中可配置任意数量的 115 云存储目标（路径名、保存目录、独立每日限额、启停状态）。
  - 第 1 个 115 达到当日限额后，自动无缝切换至第 2 个 115，依次类推；全部账号均满额后自动进入保护休眠，次日 00:01 自动重置配额并唤醒续扫（休眠期间若扩容或新增 115 账号也会即时唤醒）。
- **多语言别名过滤与自动建子目录**：支持中/繁/日文假名/英文罗马音多别名映射，自动通过 CD2 创建对应出演者子目录归档。
- **图文+种子跨条关联引擎**：自动关联 Telegram 频道中“先发图文介绍、后发 `.torrent` 附件”的多条连续消息。
- **无缝断点续传与优雅暂停**：实时记录已处理的最新消息 ID（`data/checkpoint.json`），支持随时暂停/恢复或停止/重启，自动补扫离线或暂停期间遗漏的消息，绝不重复扫描历史。
- **每日下载报表**：自动在 `records/YYYY-MM-DD.md` 生成包含时间、115 账号、出演者、标题、保存目录与磁力链接的 Markdown 表格。
- **Ubuntu 交互式数字菜单 (`tg115`)**：支持 `1 启动 / 2 暂停 / 3 停止 / 4 配置 / 5 实时任务查看 / 6 守护进程 / 7 退出`。

---

## 快速安装与使用（Ubuntu）

### 1. 获取并初始化环境

```bash
chmod +x install.sh
./install.sh
```

脚本会自动创建 `venv` 虚拟环境、安装依赖、下载并编译 CloudDrive2 官方 `clouddrive.proto`，并注册全局快捷命令 `tg115`。

### 2. 配置凭据与多 115 目标

如尚未创建 `config.json`，安装脚本会自动从 `config.example.json` 复制生成。你可以直接编辑 `config.json`，或在菜单中选择 `4. 配置` 进行交互式管理：

```json
{
  "telegram": {
    "api_id": 12345678,
    "api_hash": "YOUR_TELEGRAM_API_HASH",
    "target_channel": "your_target_channel",
    "history_start_time": "2025-01-01 00:00:00"
  },
  "clouddrive2": {
    "server": "127.0.0.1:19798",
    "api_token": "YOUR_CLOUDDRIVE2_API_TOKEN",
    "split_by_actor": true,
    "targets": [
      {
        "name": "115-主盘",
        "mount_path": "/115-1",
        "save_folder": "/115-1/云下载/tg",
        "daily_limit": 500,
        "enabled": true
      },
      {
        "name": "115-备盘",
        "mount_path": "/115-2",
        "save_folder": "/115-2/云下载/tg",
        "daily_limit": 500,
        "enabled": true
      }
    ]
  },
  "target_actors": {
    "示例出演者A": ["示例出演者A", "Example Actor A"]
  }
}
```

### 3. 启动交互式管理面板

在 Ubuntu 任意目录执行：

```bash
tg115
```

或在项目目录执行 `./tg115.sh`，即可呼出数字菜单：

| 选项 | 功能说明 |
| :--- | :--- |
| **1. 启动** | 首次运行自动引导 Telegram 手机号登录；已登录则后台启动，暂停状态下自动恢复。 |
| **2. 暂停** | 挂起推送与扫描并保留断点；恢复后自动补扫暂停期间遗漏的新消息。 |
| **3. 停止** | 优雅停止后台或守护进程并安全固化断点。 |
| **4. 配置** | 交互式新增、修改、删除多 115 路径名/保存目录/每日限额/轮转顺序，以及管理基础配置与出演者名单（支持热重载）。 |
| **5. 实时任务查看** | 展示各 115 今日配额进度条、断点状态、最近推送记录，并可进入实时滚动日志（`Ctrl+C` 返回菜单）。 |
| **6. 守护进程** | 一键开启或关闭 `systemd` (`tg115.service`) 开机自启与崩溃自愈。 |
| **7. 退出** | 退出管理面板（不影响正在后台运行的监控任务）。 |

---

## 安全提示

- 切勿将包含真实 `api_id`、`api_hash`、`api_token` 的 `config.json` 或登录凭证 `user_session.session` 提交到公开 Git 仓库。
- 本项目默认通过 `.gitignore` 屏蔽了所有私有配置、会话、断点与运行日志。
