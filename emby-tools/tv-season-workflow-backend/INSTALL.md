# 剧集整理工作流(后端) · 安装与首次使用

将四阶段浏览器脚本改为 Node.js 后端：**初检 → 补缺下载 → 复核清理 → 归档**。支持 Windows11 / Ubuntu24，推荐 Node24 LTS，最低 Node22.13。全部服务操作走 API，无需浏览器、挂载盘符或 Tampermonkey。

- [全部脚本详细分析](docs/原工作流完整分析.md)
- [接口与操作流程](docs/API.md)
- [验证记录及限制](docs/验证记录.md)

## Windows11 启动

安装 Node24 后，在项目目录执行：

```powershell
npm.cmd ci --ignore-scripts
Copy-Item -LiteralPath config.env.example -Destination config.env
# 编辑 config.env，填写凭据及实际源/归档虚拟路径
node --env-file=config.env app/server.cjs
```

Windows PowerShell 中显式使用 `npm.cmd`，可避免 `npm.ps1` 被执行策略阻止，无需修改系统执行策略。

前台启动即可使用。需要开机运行时，可将 `node.exe` 和参数 `--env-file=config.env app/server.cjs` 配置到 Windows 任务计划程序；起始位置设置为本项目目录。不要同时启动两个实例操作同一源目录。

## Ubuntu24 启动

在已安装 Node24 的环境运行：

```bash
npm ci --ignore-scripts
cp config.env.example config.env
chmod 600 config.env
# 编辑 config.env
node --env-file=config.env app/server.cjs
```

常驻服务模板见 `deploy/tv-season.service`；根据安装位置修改 WorkingDirectory、EnvironmentFile 和 Node 可执行路径后交 systemd 管理。模板没有自动安装，不会更改当前机器的服务设置。

容器方式：`docker build -t tv-season-backend .`，然后 `docker run --env-file config.env -e HOST=0.0.0.0 -p 127.0.0.1:8080:8080 -v tv-season-data:/data tv-season-backend`。容器监听非回环地址，必须填写 BACKEND_API_KEY。

## 配置重点

`CD_ORIGIN`/`MP_ORIGIN` 填服务入口，`CD_TOKEN`/`MP_TOKEN`/`TMDB_API_KEY` 从本机环境注入或放在自行维护的 config.env 中。提供的示例不包含秘密值。`config.env`、data 和 node_modules 已忽略。

CloudDrive 默认 `CD_TRANSPORT=grpc-web`，适合网页入口的反向代理；也可设 `grpc`，需要原生 HTTP/2 gRPC 转发。`MP_AUTH_MODE=apikey` 使用 X-API-KEY，可选择 `token`（查询参数）或 `bearer`（Authorization）。不同类型令牌不可互换。

SOURCE_ROOT / ARCHIVE_ROOT 是 CloudDrive 内的 `/115/...` 虚拟路径，Windows 和 Linux 使用同一格式；不是 `D:\...` 或 Linux 挂载路径。两根必须互不包含，归档分类必须已存在。MP_REPAIR_SOURCE / MP_REPAIR_TARGET 是 MoviePilot 容器内部的本地路径，仅用于整理修复；不是 CloudDrive 虚拟路径。

默认监听 `127.0.0.1:8080`。设置 BACKEND_API_KEY 后，每个请求包含 `X-API-Key`。默认 `ALLOW_REMOTE_WRITES=false`：可以扫描、查询、生成计划，执行接口会拒绝外部写入。看过具体计划后，在自行维护的配置中开启写入并重启，仍需对计划 hash 单独确认。

## 测试

Windows PowerShell 使用 `npm.cmd test`；Ubuntu 使用：

```text
npm test
```

任务和操作日志在 DATA_DIR/workflow.sqlite。备份运行中数据库需使用 SQLite 备份机制或先停服务，不能只复制主文件而漏掉 WAL。下载计划可能包含资源站私密链接的内部上下文，数据库应按私有资料保管；公开计划/报告接口输出白名单字段。

上游代码固定在 vendor/workflow，原始版本见 reference/upstream.json。业务模块来自本仓库油猴版的固定历史提交；本次不新增统一开源授权，第三方许可不能推定为业务代码的统一许可。OpenCC 与 XLSX 原始许可在 vendor 中。
