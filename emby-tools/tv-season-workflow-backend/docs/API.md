# API 与操作流程

服务默认地址 `http://127.0.0.1:8080`，JSON 请求使用 Content-Type: application/json。若配置 BACKEND_API_KEY，所有请求添加 X-API-Key。以下示例不包含真实凭据。

## 端点

| 方法/路径 | 输入 | 行为 |
|---|---|---|
| GET /health | 无 | 应用状态及外部写入开关，不声称外部服务连通 |
| POST /scan | 无 | 读 CloudDrive，登记源根下分类/剧集/Season N |
| GET /seasons | 无 | 季 ID、路径、颜色、来源和核查数据 |
| POST /seasons/:id/inspect | 可选 `{"doubanId":"123"}` | 重读文件、TMDB核查；失败时按明确豆瓣ID补查 |
| POST /plans | `{"kind":"download","seasonIds":["季ID"]}` | 生成具体操作计划，不下载/删文件/移动 |
| POST /plans | `{"kind":"cleanup","seasonIds":["季ID"],"doubanId":"123"}` | 豆瓣本季复核，保留/删除明细 |
| POST /plans | `{"kind":"repair","seasonIds":["季ID"]}` | 旧历史整理修复预览；仅MoviePilot v2.15.6 |
| POST /plans | `{"kind":"archive","seasonIds":["本剧全部季ID"]}` | 同一剧全部季归档计划，缺季或冲突阻断 |
| GET /plans/:id | 无 | 可审阅计划、hash 和状态，下载链接不公开 |
| POST /plans/:id/execute | `{"confirm":true,"hash":"计划hash"}` | 已开启外部写入时执行储存的清单，拒绝重放/过期/变化 |
| POST /plans/:id/reconcile | 无 | 只读核实，不重新提交写操作 |
| GET /jobs/:id | 无 | running/finished/stopped，结果或错误 |
| POST /jobs/:id/pause | 无 | 在检查点停止；当前已提交请求仍需核实 |
| GET /reports | 无 | JSON 季数据、公开计划、任务记录 |
| GET /reports.xlsx | 无 | 从数据库生成当前初检/状态 XLSX |
| POST /reports/import | `{"base64":"原XLSX文件base64"}` | 导入原工作流报告，不启动网络写入 |
| GET /reports/:id/xlsx?mode=download | import 返回的报告ID | 局部更新原下载报告，保留原无关内容 |
| GET /reports/:id/xlsx?mode=review | 同上 | 导出复核清理更新 |
| GET /reports/:id/xlsx?mode=archive | 同上 | 导出归档更新 |

耗时 POST 返回 HTTP202 和 `{"jobId":"..."}`，结果从 GET /jobs/:id 读取。计划创建任务的 result 含 plan id/hash。错误在 job.state=stopped 时查看 job.error。只有一个长任务可以运行；并行请求返回409。GET 的身份/参数错误返回400，认证失败401。

## 实际调用顺序

1. POST /scan，取得 job，等待结束；GET /seasons 获取季 ID。扫描只登记，不自动发起 TMDB 批量查询。
2. 对目标季 POST inspect；查看 inspection 的 missing、duplicates、unknown、evidence、error。来源未知不能继续猜总数。
3. 为缺集季创建 download 计划。预览会调用同一下载状态机模拟决策，包含已有任务排重、版本选择及播出复核；执行只允许已审阅资源上下文的子集。执行前仍重读活动下载。
4. 人工审阅计划；配置开启写入后，以 confirm/hash 调执行。任务 accepted 只表示提交成功，等待 MoviePilot 下载整理实际完成。
5. 重新 inspect，再用明确本季豆瓣 ID 生成 cleanup 计划。多个完整版本会返回需要人工处理，不能靠确认按钮强制自动删除。
6. cleanup 执行后再次核对实际文件和播完证据。对同一部剧所有绿色季创建 archive 计划，审阅每个移动及源清理条目后执行。
7. 不确定状态用 reconcile。它不会自动解除 submitting/uncertain 记录，不会重发剩余部分请求。部分成功需要按 journal 人工处理，或在状态明确后重新检查；不提供绕过保护的一键强制继续。

可通过 curl、PowerShell Invoke-RestMethod、任何前端或自动化客户端调用。原 UI 的点击确认被显式的 execute+hash 取代；生成计划本身不包含写入授权。

## 报告注意事项

原报告必须使用当前 CloudDrive origin、源目录与正确的 `?page=files&path=...` 超链接。导入遇到重复季行、错误链接、条件格式或不支持的表格结构会报错。原报告导入不能覆盖数据库已有同一路径的季记录；需要独立导入会话时使用单独 DATA_DIR。

原 XLSX 按 mode 更新对应阶段已成功执行结果；没有成功结果的行保留原样。新生成的 `/reports.xlsx` 是当前状态快照，不包含原 Excel 手工公式；要保留这些内容应使用原报告导入/局部导出路径。完整机器审计以 SQLite 和 JSON 报告为准。公开下载计划省略种子链接和上下文；内部持久化保留执行所需上下文。
