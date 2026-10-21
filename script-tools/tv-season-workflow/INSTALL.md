# 从零安装：按顺序完成即可

[返回工具首页](README.md)

## 1. 先准备三项资料

| 要准备什么 | 从哪里得到 | 示例（不要照抄） |
| --- | --- | --- |
| CloudDrive2 网站地址 | 浏览器地址栏，只保留协议、域名和端口 | `https://cloud.your-domain.com:8920` |
| MoviePilot 网站地址 | 同上，不带页面路径、查询参数或末尾 `/` | `https://mp.your-domain.com:8920` |
| CloudDrive2 中待检查的源根目录 | 文件浏览器路径；这里下面应当是各个分类 | `/115/Library_incs/nas/电视剧` |

例如地址栏为 `https://cloud.your-domain.com:8920/?page=files&path=...`，需要填写的站点地址只有 `https://cloud.your-domain.com:8920`。路径不带界面的 `Root` 前缀，不填网页 URL，也不要把“韩国剧集”这一层当作根目录。

先确认能手动登录两个网站、打开云盘目录，并且 MoviePilot 已配置可用站点和默认下载器。第一脚本的 TMDB 凭据稍后在面板中填写，不写入源码。

## 2. 安装 Tampermonkey

1. 在 Chrome 扩展商店找到并安装 **Tampermonkey**，也可从 [Tampermonkey 官网](https://www.tampermonkey.net/) 进入安装页。
2. 按浏览器/扩展当前提示允许用户脚本运行，允许它访问自己的 CloudDrive2、MoviePilot 以及脚本声明的豆瓣页面。
3. 如果曾安装旧版 `CloudDrive2剧集整理助手` 或重复的阶段脚本，先暂停旧任务并导出结果，再停用旧副本。同一阶段只启用一份。

## 3. 安装第一脚本，修改两处

1. 打开 [第一脚本文件](season-inspect.user.js)，点击 GitHub 的 **Raw**，复制完整文件内容。
2. 点击浏览器 Tampermonkey 图标→管理面板→新建脚本，删除模板内容，粘贴完整脚本。
3. 在文件顶部找到这一行，只改成自己的协议和主机名，**这里不带端口**：

   ```javascript
   // @match        https://clouddrive.example/*
   // 修改示例：
   // @match        https://cloud.your-domain.com/*
   ```

   上面“修改示例”仅用于解释；实际保留一条自己的 CloudDrive2 `@match`。原有两个豆瓣 `@match` 不要删除。

4. 向下几行，在“大段第三方库”开始前找到配置区：

   ```javascript
   const CLOUD_ORIGIN = 'https://clouddrive.example';
   const CLOUD_HOSTNAME = new URL(CLOUD_ORIGIN).hostname;
   const SOURCE = '/115/Library_incs/nas/电视剧';
   ```

   将 `CLOUD_ORIGIN` 单引号内改为自己的完整站点地址，**有端口必须带端口**；将 `SOURCE` 改为自己的源根目录。`CLOUD_HOSTNAME` 这一行保持原样，它会自动提取域名。

5. 按 **Ctrl+S** 保存；确认脚本已启用；刷新 CloudDrive2 文件页面。看到“① 剧集初检 · 只读”面板即说明加载成功，此时不会自动扫描。

HTTP 部署需将 `@match` 和配置地址中的协议都改为 `http`。不要改成匹配所有网站。不要修改第三方库内容。

## 4. 安装第二脚本，修改顶部及三项配置

同样复制 [第二脚本完整文件](season-download.user.js)，在 Tampermonkey **另建一个脚本**，不要覆盖第一脚本。

将顶部 `@match` 改为自己的 MoviePilot 协议和主机名，不带端口：

```javascript
// @match        https://mp.your-domain.com/*
```

在文件开头配置区填写：

```javascript
const ORIGIN='https://mp.your-domain.com:8920';       // MoviePilot 完整站点地址
const CLOUD='https://cloud.your-domain.com:8920';    // 与第一脚本 CLOUD_ORIGIN 完全一致
const SOURCE='/115/Library_incs/nas/电视剧';         // 与第一脚本 SOURCE 完全一致
```

保存后刷新 MoviePilot 页面，应看到“② MoviePilot 补缺下载”。此时不会搜索或下载。两脚本的云盘地址和源根目录必须一致，否则导入报告会提示源链接不符。

## 5. 第一脚本的首次配置

1. 打开 CloudDrive2，展开“TMDB 访问设置”区域，填写自己的 **API 读访问令牌**或 **API 密钥**，点击“保存 TMDB 凭据”，再点击“测试 TMDB 连接”。两者都填时优先令牌，认证失败再尝试密钥。
2. 凭据可在自己的 TMDB 账号 API 设置中获取，参考 [TMDB 认证说明](https://developer.themoviedb.org/docs/authentication-application)。不要把凭据放到公开仓库、报告或截图里。脚本将它保存在浏览器用户脚本存储中。
3. 需要豆瓣时，点击“打开豆瓣／登录准备”，手动完成可能的登录或验证，回云盘勾选“豆瓣已可访问”。已有可用豆瓣标签页时可直接检查该页再勾选，不必反复打开新页。
4. 先手动进入一部剧或它的 Season 目录，点击“检查当前剧集”。核对结果后导出。单剧检查会新建本轮结果，先保存上一轮结果。
5. 批量检查时点击“读取分类”，选择分类，点击“开始检查”。操作详情见 [第一脚本说明](docs/01-inspect.md)。

## 6. 用报告补缺下载

1. 在第一脚本导出 `.xlsx`；不要用 CSV 代替，因为 CSV 不保存颜色。
2. 若要人工维护，保留身份、路径、季号、来源集数及机器记录列；只将确认齐全的季的“剧集目录”格设为普通实心浅绿底 `C6EFCE`、深绿字 `006100`。
3. 打开 MoviePilot→第二脚本→“导入 Excel”→选择报告。
4. 看面板的任务数量和错误提示。导入完成仍不会运行。
5. 点击“开始补缺下载”才会提交下载；需要停下时点“暂停”，等待当前请求结果被记录。
6. 点“导出更新报告”。新文件名以 `_下载补充.xlsx` 结尾，原文件不会被修改。
7. 打开新报告的“下载明细_N”，查看资源和执行情况。去 MoviePilot/下载器查看实际进度。黄格代表待复核，不能直接改成已完成。

## 7. 没看到面板怎么办

按顺序检查：脚本已保存和启用→地址栏协议正确→`@match` 域名正确→配置常量的端口正确→刷新网页→扩展已获访问及执行权限。不要反复新建脚本造成多个副本同时运行。

若页面提示没有 `MoviePilotAPI`，说明当前 MoviePilot 前端未提供脚本需要的页面接口。它不是 TMDB 密钥问题；不要在脚本里粘贴登录令牌来绕过。停止执行，检查部署版本及前端兼容性。

运行中保持浏览器和工作标签页打开，避免电脑休眠。不要同时在云盘工作标签页手动切换目录。网页后台节流可能让运行变慢，不能保证锁屏后继续运行。

## 8. 以后升级怎么做

1. 暂停并导出当前报告，记下自己的站点地址和源根目录。
2. 在 Tampermonkey 中编辑**原来同一阶段的脚本**，用新版完整代码替换。
3. 按上述配置区重新填入地址、路径及 `@match`，保存后刷新对应网站。
4. 第一脚本可点击“恢复上次进度”后手动继续；第二脚本重新导入报告，并利用保留的本地记录避免重复下载。

不要清空用户脚本存储来重试结果不明的下载。卸载脚本、换浏览器或清除存储可能丢失进度与防重复记录。公开脚本不配置自动更新地址，以免自动更新覆盖手工填写的站点配置。
