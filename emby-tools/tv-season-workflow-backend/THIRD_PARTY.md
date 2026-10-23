# 来源与依赖

业务模块：hailanbb/skill-selection，固定提交见 reference/upstream.json，路径 script-tools/tv-season-workflow/src。vendor/workflow 保持下载的原始文本。业务模块来自本仓库固定历史提交；本次不新增统一授权声明，第三方依赖的许可证不能推定为业务代码的统一许可证。

OpenCC-js 1.4.2：vendor/opencc.cjs，许可及其第三方声明见 vendor/opencc-license。

xlsx-js-style 1.2.0：vendor/xlsx.bundle.js，原许可见 vendor/XLSX-LICENSE 和 vendor/XLSX-DIST-LICENSE。

CloudDrive proto：来自 https://www.clouddrive2.com/api/clouddrive.proto，保留原文与官方注释。MoviePilot OpenAPI：来自 https://api.movie-pilot.org/openapi.json，保留下载的接口快照。

Fastify、grpc-js、proto-loader、xmldom 的精确依赖树由 package-lock.json 锁定，依赖包自带许可。
