# 安装与首次使用

## 环境

- Ubuntu 22.04/24.04为自动验证目标；Node.js 22.13或更新，npm随Node安装。
- 可以使用root或普通SSH用户安装和运行。root使用系统级服务；普通用户使用用户级服务，数据分别保存在各自账户目录。
- Ubuntu可通过网络访问远端CloudDrive2和MoviePilot API。不要求挂载网盘，不要求两个服务与控制端同机。
- CloudDrive2 API令牌及MoviePilot API Key或Bearer凭据由你在对应服务准备；本程序不会创建、轮换令牌或修改服务权限。

**必须使用Node.js 22.13或更新版本**；这是程序使用内置SQLite的运行要求。Ubuntu默认软件源安装的版本可能过低，不能只确认“已安装Node”。已经满足版本要求的可跳过下面的Node安装步骤。

## 安装Node.js（root可直接复制）

以下使用[nvm官方安装方式](https://github.com/nvm-sh/nvm#installing-and-updating)，安装Node 22系列的最新补丁版本，自带npm。在以后运行本程序的同一个账户下执行；root直接复制，普通用户仅在前两条apt命令前加 `sudo`，其余命令不加。

```bash
apt update
apt install -y ca-certificates curl git

export NVM_DIR="$HOME/.nvm"
curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.8/install.sh | bash
. "$NVM_DIR/nvm.sh"
nvm install 22
nvm alias default 22
nvm use 22

node --version
npm --version
```

检查 `node --version` 输出为 `v22.13.0` 或更新；新终端若仍使用旧版本，执行 `. "$HOME/.nvm/nvm.sh"` 和 `nvm use 22` 后再安装本程序。不需要先卸载系统原有Node。

Node来源与版本说明见[Node.js官方安装页](https://nodejs.org/en/download)。systemd记录安装时的Node绝对路径，所以无需依赖后台加载nvm；启用服务后不要删除该Node版本。

## 获取与安装

下面采用Git部分克隆和目录检出，获取本项目，避免下载仓库中其他工具的正文。Git仍保留必要的仓库元数据、少量根目录和上级索引文件，方便后续更新；`--depth 1`本身只减少历史记录，不能只下载子目录。

```bash
git clone --depth 1 --filter=blob:none --sparse https://github.com/hailanbb/skill-selection.git tvflow-source
git -C tvflow-source sparse-checkout set emby-tools/tv-season-linux
cd tvflow-source/emby-tools/tv-season-linux
bash install.sh
```

以上是首次获取命令，目标 `tvflow-source` 必须尚不存在。已安装的项目不要移动源码或重复克隆覆盖；按文末更新步骤操作。[Git目录检出说明](https://git-scm.com/docs/git-sparse-checkout)。

安装脚本安装锁定依赖、验证上游快照、构建纯业务模块，并按当前账户创建命令链接和服务文件：

| 安装账户 | 命令 | 服务文件 | 默认数据目录 |
|---|---|---|---|
| root | `/usr/local/bin/tvflow` | `/etc/systemd/system/tvflow.service` | `/root/.local/share/tvflow` |
| 普通用户 | `~/.local/bin/tvflow` | `~/.config/systemd/user/tvflow.service` | `~/.local/share/tvflow` |

默认不会覆盖一个不同的既有命令或服务配置，不自动启动服务或启用自启动。root安装无需创建其他用户，直接运行 `bash install.sh`。root服务记录该账户的HOME、状态目录和Node绝对路径，避免后台读到另一份配置；如安装时设置了 `TVFLOW_HOME`，会记录该实际目录。

运行 `tvflow` 进入菜单；如果命令不在PATH中，root使用 `/usr/local/bin/tvflow`，普通用户使用 `~/.local/bin/tvflow`。不要移动源码目录；服务文件记录其实际位置。后续使用与安装相同的账户，不要交替用root和普通用户运行，以免分别创建独立任务库。

## 建议启用独立于SSH会话的服务

### root安装

尚未运行过菜单或其他后台时，直接执行：

```bash
systemctl daemon-reload
systemctl enable --now tvflow.service
systemctl status tvflow.service
```

root使用系统级服务，**不加 `--user`，也不需要配置linger**。日志和启停命令：

```bash
journalctl -u tvflow.service -n 100 --no-pager
systemctl stop tvflow.service
systemctl start tvflow.service
```

如果已运行菜单并自动启动后台，先按下文的方法核对并停止原进程，再启用服务，避免两个后台竞争同一任务库。安装本身不启用服务。

### 普通用户安装

先关闭此前自动启动的后台，再启用systemd，避免两个管理方式竞争同一个数据目录。若这是第一次启动，直接执行下面最后两条即可。

查看本程序状态目录中的 `daemon.lock`，确认PID对应 `tvflow.js daemon` 后，对该进程发送SIGTERM并等待退出；不要杀死不明PID。运行中写任务会尝试在75秒内暂停和记录结果。

```bash
systemctl --user daemon-reload
systemctl --user enable --now tvflow.service
```

为了让用户服务在SSH退出后继续运行，由你在Ubuntu上启用用户linger：

```bash
sudo loginctl enable-linger "$USER"
loginctl show-user "$USER" -p Linger
systemctl --user status tvflow.service
```

应看到 `Linger=yes`。这会让该用户的systemd服务在注销后继续存在，是明确的系统设置变更；安装脚本不代为执行。无systemd的环境可用进程管理器托管 `node bin/tvflow.js daemon`，仅使用tmux不能替代任务日志和未知结果核实。

常用管理：

```bash
journalctl --user -u tvflow.service -n 100 --no-pager
systemctl --user stop tvflow.service
systemctl --user start tvflow.service
```

服务重启会恢复任务记录，但未完成任务处于暂停状态，需从菜单继续或只读核实，不自动重发外部写入。

## 首次设置

运行 `tvflow`，进入 `8 设置与连接诊断`。

1. **3 CloudDrive2连接**：设置协议、主机、端口，例如 `https://cloud.example`。选择原生 `grpc` 或代理支持的 `grpc-web`；网页可访问不等于原生gRPC可访问。认证采用API令牌，输入隐藏。
2. **4 MoviePilot连接**：填写服务origin；程序追加 `/api/v1/`。按实际服务选择 `apikey`（X-API-KEY）或 `bearer`，隐藏输入认证值。不要把凭据写在URL里。
3. **1 当前源根目录**：默认 `/115/Library_incs/nas/`，可浏览或输入更改。
4. **2 归档根目录**：自行选择已经存在的目标，不设猜测默认值。源目标不能相同、嵌套或为云盘根。目标相应分类须提前存在。
5. **7 报告与保存路径**：分别设置本机Excel/CSV、JSON、日志目录。配置时由后台实际运行账户检查可写性。
6. **6 只读连接诊断**：核对目录读取、正在下载接口及本机输出目录。

常规配置和认证保存在 `~/.local/share/tvflow/config.json`，权限为仅当前用户读写；不要提交到GitHub。任务快照、报告和日志不包含凭据。默认状态目录可通过 `TVFLOW_HOME` 更改，但CLI与服务必须使用同一值；systemd需在自己的服务override中设置同名环境变量。

## 三类路径不能混用

| 路径 | 属于哪里 | 示例 |
|---|---|---|
| 源/归档目录 | CloudDrive2虚拟文件树 | `/115/Library_incs/nas/` |
| 修复源/目标目录 | MoviePilot看到的local存储，可能为容器路径 | `/video/downloads`、`/video/library` |
| 报告/记录/日志目录 | Ubuntu控制端本机 | `/home/media/tvflow/reports` |

整理修复路径在 `8 → 5` 单独设置，初检、普通补缺和归档不要求填写它。当前修复沿用固定规则，只支持MoviePilot v2.15.6且满足严格单集预览的local路径，其他版本会停止并说明，不自行更改或升级MoviePilot。

## 更新

先暂停任务、保留数据库和报告；在仓库无个人改动冲突时拉取更新，再在项目目录运行 `npm ci --ignore-scripts` 和 `npm run build`，重启对应服务（root：`systemctl restart tvflow.service`；普通用户：`systemctl --user restart tvflow.service`）。本版不含自动数据迁移或自动更新任务；不要删除数据库来“解除”不确定操作。

备份状态时先停止服务，复制整个状态目录（包含可能的SQLite WAL文件）；配置中含认证信息，备份自行妥善保存。报告路径若自定义到别处，也应单独保留。备份程序数据库不等于备份远端媒体。
