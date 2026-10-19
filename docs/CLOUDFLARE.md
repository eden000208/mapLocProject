# Cloudflare 托管部署

分支：`codex/cloudflare-hosting`。Vue 静态资源、API 入口托管在 Worker，FastAPI
运行在 Cloudflare Containers；公司内网只保留现有 MySQL 和 cloudflared。

## 架构与边界

```text
浏览器 → Worker 静态资源 /api → 单个 FastAPI Container
                                    ├─ 私有出站 WebSocket → VPC Network → 已有 Tunnel → MySQL
                                    └─ 私有出站 HTTP → R2 绑定
```

采用 Containers 是为了保留 Python 原生依赖、线程查询、200 MiB 上传、XLSX
流式处理和 MySQL 单事务导入。不是纯 Python Worker 部署。需要启用 Containers
并满足其付费及配额要求；按配置实例为 `standard-1`，最多 1 个，空闲 30 分钟休眠。
不能横向扩容，否则查询恢复、进程锁和空间索引需要重新设计。平台仍可能重启实例，
查询重启后失败，不自动重放明细写入。

Containers 必须依托 Durable Object；配置中的 `storage: sqlite` 仅为平台
容器控制状态，不存业务表、不增加 SQLite 应用数据库。业务数据仍在现有 MySQL，
文件及操作摘要在私有 R2，不引入 Redis/Celery/迁移框架。

数据库使用 VPC Network 的固定目标原始 TCP 通道，而不是 Hyperdrive 的连接池。
这是为了保持已有 MySQL `GET_LOCK` 会话锁的连接归属。现有 Hyperdrive 不需要删除，
此部署不使用它，也不修改其配置。WebSocket 网关只存在于 Container outbound
拦截器，公网 Worker 不能选择目标或直接调用该网关。
VPC Network 原始 TCP 目前不提供额外数据库 TLS，此方案链路由 Cloudflare
内部传输和 cloudflared 加密隧道保护，MySQL 出口仍应限制在内网。

## 一次性账号准备

1. 保持已有 `lt_mysql` Tunnel 在线。
2. 启用 Containers 和 R2，创建私有桶 `bsq-files`。不启用 r2.dev 或公开域名。
3. 在 R2 为 `imports/`、`detail_uploads/`、`chunks/`、`exports/` 设置 2 天对象过期，
   `operations/` 同样设置 2 天过期。应用继续执行 24 小时授权有效期；生命周期负责
   孤立文件和容器停机时的最终清理，过期对象删除可能有平台延迟。
4. 核对 `cloudflare/cloudflare.config.ts` 中的 Tunnel ID、数据库地址和端口。
   当前来自本次账号只读检查；API 不提供数据库实际连通性保证。
5. 应用账号只能写 `bsq_app`；其他明细库仅 SELECT。无需创建新库或运行 demo/init。
6. 天地图控制台添加网站正式域名白名单。

本地需要 Node 24、Docker Engine/Desktop 和可运行的 Docker daemon。
CLI 使用已锁版本的 `cf`；Vite 插件生成部署产物，不手写 Wrangler 配置。

## 首次构建与发布

```powershell
cd frontend
npm.cmd ci
npm.cmd run typecheck
npm.cmd run build
cd ../cloudflare
npm.cmd ci
npm.cmd run typecheck
npm.cmd run build
Copy-Item .env.example .env
notepad .env
# 以下命令交互登录；CI 使用限定范围的 API token
npx.cmd cf auth login
npm.cmd run deploy -- --prebuilt --secrets-file .env
```

在被忽略的 `cloudflare/.env` 填 `MYSQL_USER`、`MYSQL_PASSWORD`、`TIANDITU_KEY`。
这些值上传为 Worker secrets，在启动容器时注入，不进入镜像和版本控制。
根目录原有 `.env` 继续用于本地/Compose，两种部署配置分开。

首次发布可能由平台要求创建容器控制资源；确认使用现有 Cloudflare 账号，
不更改 MySQL 表结构。发布后在 Worker 配置自定义域名或使用 workers.dev。

## GitHub 自动更新

已提供 `.github/workflows/cloudflare.yml`：

- 分支 push/PR：语法检查、ruff、mock 测试、前端 typecheck/build、Worker
  typecheck 和 Linux Docker 完整构建。
- 首次发布并配置 secrets 后，在 GitHub Repository Variables 设置
  `CLOUDFLARE_ACCOUNT_ID` 和 `CLOUDFLARE_AUTO_DEPLOY=true`。
- Repository Secrets 设置限定到该账号的 `CLOUDFLARE_API_TOKEN`，需要 Worker、
  Containers/镜像发布、绑定现有 R2/VPC 资源的相应权限。
- `main` push 检查通过后发布；迭代分支默认只检查。也可手动运行 workflow，
  显式勾选 deploy。建议为 GitHub `production` Environment 配置发布保护。
- CI 发布不传数据库密码，复用首次部署的 Worker secrets。禁用 fork PR 的部署。
- 更新会重启后端；安排在无导入、无查询时发布。没有实现零停机或数据库回滚，
  部署前应使用数据库现有备份策略。代码回退不会回退已提交的导入。

本地 Git 的 origin 当前仍为 Gitee，若要推送这个分支到 GitHub，可新增 remote：

```powershell
git remote add github https://github.com/eden000208/mapLocProject.git
git push -u github codex/cloudflare-hosting
```

## HTTP 行为

- 前后端同域 `/api`，安全 Cookie 和 CSRF 保留。API 及下载响应 `no-store`。
- 明细上传按 8 MiB 顺序分片，不超过 Free/Pro 单请求上限；总文件仍最多 200 MiB。
  分片只允许管理员本人操作，使用已有 ImportBatch，不建新表。
- 合并、全量预览、确认、导出走 `/api/operations` 提交后轮询；最多 2 个执行、
  4 个排队及执行合计。没有业务数据写入 Cloudflare 日志或工作流快照。
- 每次读取操作和下载复核用户归属及当前权限，导出继续复核区域/明文权限。
- R2 恢复上传原文件后继续使用原解析逻辑。临时磁盘不可作为持久副本。
- 旧同步接口保留给现有客户端，但大文件经 Cloudflare 应使用新前端流程。

## 上线验收与当前限制

先请求 `/api/health`，该接口仅执行数据库健康检查，不回显记录。之后验证登录、
CSRF、地图、合成样例分片上传、预览/确认、查询、分页、取消、脱敏/明文权限、
导出及重启后的 R2 文件恢复。不要用真实号码作为浏览器截图或测试输出。

当前工作机没有 Docker CLI，Worker JS 和 Vue 资源可打包，但完整容器镜像构建
未在本机通过；GitHub Linux pipeline 已包含该检查，需推送后运行。没有创建云端
资源、上传镜像、发布 Worker 或修改真实数据库；实际容器出站 WebSocket/VPC
兼容性、真实 MySQL 连通性、200 MiB 性能、资源配额和计费仍需云端验收。
本分支在这些检查通过前不能标记为生产验收完成。
