# 来源、依赖与许可

项目基于用户指定油猴版的固定源码快照，不复用 `tv-season-workflow-backend`。

- 来源仓库：https://github.com/hailanbb/skill-selection
- 固定提交：`12afc3b4e24c1373f390f96d96bfbd6cb6b85af7`
- 原目录：`emby-tools/tv-season-workflow`
- `vendor/upstream`保留原77文件，原摘要清单用于构建时校验；其中包含原有228项模拟测试。
- `scripts/build-cores.cjs`生成7个纯业务工厂，统一补缺播期判断为与初检相同的保守日期边界。新API适配器从原始大小字段采集精确字节数。

原OpenCC-js 1.4.2、xlsx-js-style 1.2.0及随附MIT/Apache-2.0和第三方数据声明均保存在原快照内。新运行依赖为@grpc/grpc-js、@grpc/proto-loader、@xmldom/xmldom和xlsx-js-style，版本与传递依赖固定在package-lock.json，其各自许可证随npm包分发。

CloudDrive2协议文件来自 [官方proto](https://www.clouddrive2.com/api/clouddrive.proto)，获取日期2026-10-23；接口说明见[官方指南](https://www.clouddrive2.com/api/CloudDrive2_gRPC_API_Guide.html)。MoviePilot接口按[官方OpenAPI](https://api.movie-pilot.org/openapi.json)及v2.15.6源代码核对。运行时服务版本不同需验证，不将公开规范视为全部部署的兼容保证。

本项目不是CloudDrive2、MoviePilot、TMDB或豆瓣的官方产品。不新增对原项目自有代码的统一开源授权声明；第三方依赖许可不能被推定为全部自有代码许可。

This product uses TMDB data through MoviePilot but is not endorsed or certified by TMDB.
