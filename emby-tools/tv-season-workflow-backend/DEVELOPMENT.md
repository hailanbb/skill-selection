# 开发、测试与发布

[项目首页](README.md)

安装依赖后，Windows PowerShell执行 `npm.cmd test`，Ubuntu执行 `npm test`。本后端使用12项模拟测试，不操作真实服务或读取本机config.env。

维护源码在app/，固定原业务工厂在vendor/workflow/；不要把网页主控制器当作后端执行。package-lock.json锁定依赖。根仓库的tv-season-backend工作流按项目目录分别在Windows及Ubuntu运行Node22/24测试。

本地配置、data、node_modules、上游临时工作副本和日志不属于发布包。snapshot-manifest.json记录除自身外所有发布文件的SHA-256；发布更新后应重新生成并校验。

原业务模块固定提交见UPSTREAM.md；原油猴版测试和构建指南见[油猴版开发说明](../tv-season-workflow/DEVELOPMENT.md)。发布时保留第三方许可，不能将第三方许可推定为业务源码统一许可。
