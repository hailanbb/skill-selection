# 🎬 剧集整理工作流 — Win11 后台版本

基于 CloudDrive2 / MoviePilot / TMDB API 的无头剧集管理工具。原 Tampermonkey 油猴脚本的后台重构版，无需浏览器。

## 快速开始

```bash
# 1. 安装依赖
npm install

# 2. 配置
cp config.example.json config.json
# 编辑 config.json，填写 CloudDrive2 和 MoviePilot 的 API 令牌

# 3. 运行
node bin/tv-workflow.js inspect          # ① 全库初检
node bin/tv-workflow.js inspect -i       # 🔍 交互式浏览选择分类与剧集初检
node bin/tv-workflow.js download         # ② 补缺下载（含自动整理修复）
node bin/tv-workflow.js repair           # 🔧 专项整理修复（仅解除 MoviePilot 阻塞历史重转）
node bin/tv-workflow.js review           # ③ 复核清理（预览）
node bin/tv-workflow.js review --yes     # ③ 复核清理（执行）
node bin/tv-workflow.js archive          # ④ 归档（预览）
node bin/tv-workflow.js archive --yes    # ④ 归档（执行并自动对账复核）
node bin/tv-workflow.js verify           # 🔍 归档后对账复核（独立核验目标与源存量）
node bin/tv-workflow.js auto             # 全自动流程
```

## 交互式后台模式

```bash
node bin/tray.js
```

启动后显示交互菜单，支持手动触发各阶段。同时启动内置定时调度器（默认每日 02:00 自动执行全流程）。

## 工作流程

```
① 初检 → ② 补缺下载 → ③ 复核清理 → ④ 归档
   │           │            │           │
   │  扫描CD2  │ 搜索MP资源  │ 清理冗余   │ 移动到目标
   │  查TMDB   │ 提交下载    │ 版本文件   │ 验证完整性
   │           │            │           │
   └──→ .xlsx ─┘──→ .xlsx ──┘──→ .xlsx ─┘──→ 最终报告
```

## 配置说明

| 配置项 | 说明 | 必填 |
|--------|------|------|
| `clouddrive2.origin` | CloudDrive2 地址，如 `http://192.168.1.100:19798` | ✅ |
| `clouddrive2.token` | CloudDrive2 API 令牌 | ✅ |
| `moviepilot.origin` | MoviePilot 地址，如 `http://192.168.1.100:3000` | ✅ |
| `moviepilot.token` | MoviePilot API 令牌 | ✅ |
| `moviepilot.extraSearchSites` | 补缺下载追加搜索的专属站点（默认: `["观众", "天空"]`） | 可选 |
| `tmdb.apiKey` | TMDB API 密钥（用于初检查询集数） | 可选 |
| `paths.source` | 云盘源目录 | 默认 `/115/Library_incs/nas/电视剧` |
| `paths.destination` | 归档目标目录 | 默认 `/115/Library_incs/nas.finish/电视剧` |
| `schedule.cron` | 定时任务 cron 表达式 | 默认 `0 2 * * *` |

## 目录结构

```
tv-workflow-win/
├── bin/
│   ├── tv-workflow.js      # CLI 入口
│   └── tray.js             # 交互式后台入口
├── lib/
│   ├── clients/            # API 客户端
│   │   ├── clouddrive2.js  # CloudDrive2 REST API
│   │   ├── moviepilot.js   # MoviePilot REST API
│   │   └── tmdb.js         # TMDB API
│   ├── core/               # 核心业务逻辑
│   │   ├── episode-parser.js   # 集号解析
│   │   ├── title-matcher.js    # 剧名匹配
│   │   └── report-adapter.js   # Excel 报表读写
│   ├── stages/             # 四阶段编排
│   │   ├── inspect.js      # ① 初检
│   │   ├── download.js     # ② 补缺下载
│   │   ├── review.js       # ③ 复核清理
│   │   ├── archive.js      # ④ 归档
│   │   └── index.js        # 调度入口
│   └── platform/           # 平台层
│       ├── notify.js       # Win11 Toast 通知
│       ├── scheduler.js    # 定时调度器
│       └── data-store.js   # 持久化存储
├── config.example.json     # 配置模板
├── reports/                # 报表输出
├── logs/                   # 日志
└── data/                   # 持久化数据
```

## 与油猴脚本的区别

| 特性 | 油猴脚本 | Win11 后台版 |
|------|---------|-------------|
| 需要浏览器 | ✅ | ❌ |
| 界面依赖 | 网页 DOM | 纯 API |
| 定时运行 | ❌ | ✅ cron |
| 人工操作 | 每步导入导出 | 全自动串联 |
| 稳定性 | 受页面变化影响 | API 稳定 |
| 通知 | 无 | Win11 Toast |

## 系统要求

- Node.js >= 20
- Windows 11（通知功能；核心功能跨平台）
- CloudDrive2（需开启 API）
- MoviePilot（需 API 令牌）

## 运行方式

### 模式 A：交互式控制台（新手推荐，日常挂机）

```powershell
# 进入项目目录
node bin/tray.js
```

### 模式 B：命令行直接执行（适合脚本与自动化）

```powershell
node bin/tv-workflow.js inspect -i       # 交互式选剧初检
node bin/tv-workflow.js archive --yes    # 归档执行并对账复核
node bin/tv-workflow.js verify           # 独立归档核验
```
