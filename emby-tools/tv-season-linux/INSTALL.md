# 一键安装与卸载

在Ubuntu的 **root终端** 复制这一条命令：

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/hailanbb/skill-selection/master/emby-tools/tv-season-linux/manage.sh)
```

屏幕会显示：

```text
1 一键安装（包含Node.js和程式）
2 一键卸载（清除清理已安装的程式）
```

## 选择1：安装

自动检测并优先复用已有Node/npm，必要时才下载Node并校验官方摘要，然后获取本项目、安装锁定依赖、构建程序并创建 `tvflow` 命令。有运行中的systemd时，同时启用本程序后台及开机启动。不会自动提交下载或操作云盘文件。

| 内容 | 默认位置 |
|---|---|
| 程序及依赖 | `/home/tv-season-linux/`（含 `bin/`、`lib/`、`node_modules/`） |
| Node.js | 优先复用现有路径；只有没有合格版本时才安装到 `/home/tvflow-node/`，卸载程序时保留 |
| 配置 | `/home/tv-season-linux/config/config.json` |
| 任务库、后台状态、安装记录、安装缓存 | `/home/tv-season-linux/data/` |
| Excel、CSV | `/home/tv-season-linux/reports/J编号/` |
| 完整JSON | `/home/tv-season-linux/records/J编号/` |
| 任务日志、后台启动日志 | `/home/tv-season-linux/logs/` |
| 实际命令 | `/home/tv-season-linux/bin/tvflow` |
| 实际后台服务配置 | `/home/tv-season-linux/config/systemd/tvflow.service` |
| 系统注册链接 | `/usr/local/bin/tvflow`、`/etc/systemd/system/tvflow.service`，都指向程序目录中的实际文件 |

运行要求是 **Node.js 22.13或更新版本**。管理器先检查当前PATH中的Node，再检查保留的独立Node、系统常见路径和当前账户的nvm版本目录，选择可运行且有可用npm的版本，**直接复用，不重复下载或安装Node**。不需要提前加载nvm，也不扫描其他用户的目录。

若仅有合格Node但缺少可用npm，会明确提示补齐npm并停止，不会为获取npm重复安装Node。只有没有任何合格Node时，才自动安装Node 22系列最新补丁到 `/home/tvflow-node/`；该目录已被占用时不覆盖。不会更改系统Node或nvm的默认版本。

安装时显示实际复用的Node/npm路径，服务和 `tvflow` 命令记录所选Node的绝对路径，不依赖后台加载nvm。请保留该Node版本；卸载本程序不会删除它。

仅获取 `emby-tools/tv-season-linux` 项目及必要的Git元数据/少量索引；安装暂存目录结束后清理，不保留其他工具源码。现有程序、命令或服务已占用目标时停止，不覆盖；先选择2卸载旧版，再重新运行此命令选择1。

安装完成后输入 `tvflow`。第一次可在菜单 `8` 设置连接，也可以在本地填写配置后上传至 `/home/tv-season-linux/config/config.json`。参考 [配置模板](config.example.json)，文件需为UTF-8无BOM的合法JSON，权限设为仅root读写（`chmod 600 /home/tv-season-linux/config/config.json`）。模板的三项 `outputs` 已填写新目录。用本地配置覆盖前先暂停任务并停止后台，覆盖后重新启动；不要上传旧输出路径的配置。地址只填协议、主机和端口，不加 `/api/v1/`。程序每次处理命令时重新读取配置；修改前暂停任务。

这是全新安装布局，不迁移旧版数据。默认不再使用 `/root/.local/share/tvflow/`。菜单 `8 → 7` 允许在各自的 `reports/`、`records/`、`logs/` 下选择子目录，不能把输出移到程序目录之外。`data/state.sqlite` 保存任务与防重记录；`logs/daemon-start.log` 保存菜单自动启动后台时的输出。安装缓存也位于 `data/npm-cache/`。

CloudDrive2按实际入口选择 `grpc` 或 `grpc-web`；网页能打开不等于原生gRPC可用。MoviePilot支持 `apikey` 或 `bearer`。运行 `tvflow doctor` 进行只读连接检查，所有 `ok` 为 `true` 后再开始初检。TMDB/豆瓣通过MoviePilot获取，不需要给本程序单独填写TMDB API Key。

整理历史修复单独需要配置MoviePilot看到的真实本地源/目标路径；不使用该功能可保持 `repair` 两项为空。

## 选择2：卸载，清理刚刚安装的旧版

先在菜单输入 `q` 退出，备份要保留的报告和配置。再运行上方唯一的管理命令，选择 **2**。

卸载器会根据命令链接、服务文件和项目标识识别旧版程序位置，先显示将清理的本机绝对路径。输入 **卸载** 后执行：

- 停止并禁用本程序服务，等待后台暂停并退出；没有退出时停止清理。
- 删除本程序命令、服务、服务附加配置和启动链接。
- 删除已确认的程序目录、配置、SQLite任务库、默认报告/JSON记录/日志，以及上传的本程序 `tvflow-config.json`。
- 对自定义输出目录，只删除任务记录明确对应的本程序报告和日志，不删除整个共用目录。
- 清理当前管理器的下载暂存文件。

**保留新安装的Node.js，也保留系统Node/npm及nvm。** 不删除云盘媒体，不卸载CloudDrive2/MoviePilot，不删除下载器任务。旧版若位于完整 `skill-selection` 仓库中，仅删除该项目子目录，其他项目和仓库不会删除。

不能确认归属的同名命令、服务或目录会保留并列出，不把它们当作本程序强删。卸载同时清除认证与任务记录，需要重新安装时请在本地保留自己的配置副本；不要将含认证信息的文件上传GitHub。

## 日常使用与归档核验

输入 `tvflow` 打开菜单；root后台管理使用 `systemctl status tvflow.service`、`systemctl stop tvflow.service`、`systemctl start tvflow.service`，日志使用 `journalctl -u tvflow.service -n 100 --no-pager`。

菜单 **9 归档库复核（只读）** 可独立复核已归档的电视剧与动漫；默认根目录为已有 `libraryRoot`，旧配置未填写时使用归档目标，未设置目标时为 `/115/Library_incs/nas.finish/`。不需要改变整理源根；可在该菜单浏览、多选分类或输入具体路径。详细说明见[归档库复核](docs/USAGE.md#归档库复核只读)。

补缺搜索范围为 **MoviePilot默认站点 + 天空 + 观众**。程序按站点名称查出本机MoviePilot中的ID，合并并去重资源，不修改MoviePilot全局站点设置。追加站点缺失、重名、停用或搜索失败会列明原因，不按不完整资源池继续选择下载。

归档结束自动复核报告与CloudDrive2。只有源目录已消失，目标路径、集号/视频数及文件大小、修改时间均符合记录，报告才标紫。异常标红并导出差异；菜单 `4 → 5` 可再次只读核验并输出新报告。核验不会自动删除、移动或“修正”云盘文件。

[完整操作说明](docs/USAGE.md) · [报告说明](docs/REPORTS.md) · [验证范围](docs/VALIDATION.md)

安装来源：[Node官方发行文件与摘要](https://nodejs.org/download/release/latest-v22.x/SHASUMS256.txt)、[Git部分目录检出](https://git-scm.com/docs/git-sparse-checkout)。支持Ubuntu22.04/24.04的x86_64/arm64；自动验证覆盖x86_64，arm64需实际主机验收。首次运行管理命令需要系统已具备curl及HTTPS证书；其余缺少的安装工具会自动通过apt补齐。
