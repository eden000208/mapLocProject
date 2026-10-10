# BSQ 基站圈选查询（轻量版）

Vue 3 + Leaflet、FastAPI、MySQL。系统数据写入独立 `bsq_app`，在线本网/异网明细查询只读。当前范围以 `docs/PLAN.md` 为准。

## 当前连接状态

2026-10-10 已使用远程 MySQL `10.44.225.184:3306` 的 `root` 账号连接成功，服务端为 MySQL 8.0.41。已初始化独立 `bsq_app`，按用户要求创建本网/异网明细表及合成验收数据，并配置天地图 Key。其他库及原有业务表未修改。

## 本地开发

Python 3.11+、Node 22.12+。将 `.env.example` 配置为根目录 `.env`（该文件被忽略），填写连接密码和天地图 Key。当前工作区已配置提供的连接信息。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
cd backend
..\.venv\Scripts\python.exe -m app.inspect_db
```

检查命令只展示表字段元信息，不打印明细。`backend/datasource.yaml` 当前映射 `bsq_app.detail_local/detail_other`；接入其他真实来源时可修改映射，表名支持 `数据库.表` 格式。

```powershell
# backend 目录执行，显式创建系统库与表，交互输入管理员密码
..\.venv\Scripts\python.exe -m app.init_db
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
# 另一个终端进入 frontend
npm ci
npm run dev -- --host 127.0.0.1 --port 5173
```

打开 http://127.0.0.1:5173。首次登录须改密。管理员可使用地图查询、我的查询和管理工作台，查询全部有效小区并显式查看明文。分析员按区县/营服授权访问，空范围默认无法看到小区。所有账号只能访问自己的任务。

当前工作区已初始化管理员，初始凭据在被忽略的 `backend/data/initial-admin.txt`，首次登录改密后删除该文件。它是本地交付文件，不会进入版本库或 Docker 镜像。

`allowPublicKeyRetrieval=true` 是 JDBC 驱动选项，不能直接传给 PyMySQL。本项目已包含其 RSA 认证所需的 cryptography 依赖，并已成功完成远程认证。1045 时优先核对实际账号、密码及客户端授权。

## 模拟数据与验收

当前已在 `bsq_app.detail_local` 和 `bsq_app.detail_other` 写入带 `DEMO-` 标记的合成明细，每网 240 行，覆盖 2 个月和 4 个小区，`is_demo=1`。演示分析员凭据见被忽略的 `backend/data/demo-login.json`，首次登录须改密；该账号只可访问“模拟区县”的 3 个小区。

重新生成数据并运行真实 MySQL/API 闭环验收：

```powershell
cd backend
..\.venv\Scripts\python.exe -m app.demo --verify
```

该命令仅重建标记为模拟的明细，保留正式数据，不改其他库；验收会保留演示任务、清理临时管理员。摘要记录在 `backend/data/acceptance.json`。停止正在运行的后端后执行，完成后重启后端，以避免验收期间进程内参数及任务恢复与正在使用的服务互相影响。

`--verify` 需要开发依赖中的 httpx；仅创建模拟明细和演示账号可运行 `python -m app.demo`。Linux 镜像默认只安装运行依赖。

接入正式数据前，删除模拟明细并停用演示账号；管理页面导入自己的基站。模拟基站 LAC 固定为 990000，名称前缀“模拟”，可按该标记识别。不要将演示查询结果当成真实业务结果。

## Linux Docker

```bash
docker compose build
docker compose run --rm backend python -m app.inspect_db
docker compose run --rm backend python -m app.init_db
docker compose up -d
```

打开服务器 8080 端口。Compose 不创建 MySQL 容器。外部 MySQL 用户需要 `bsq_app` 建库建表和读写权限、明细表 SELECT 权限。默认 Caddy 内网 HTTP；已有 HTTPS 反代时设置 `COOKIE_SECURE=true`。生产外部 TLS 按部署环境自行配置。

## 使用

1. 管理员上传 CSV/XLSX，确认列映射和坐标校准，将有效行增量导入；无效行可下载错误报告。
2. 分析员或管理员在地图放大后画矩形、多边形、圆，或点选站点小区；可按名称、小区号、LAC 搜索。点击“当前定位”后浏览器请求位置授权，显示定位点和精度圈；地图底部显示视口中心经纬度及缩放。定位需要 HTTPS 或 localhost，位置精度取决于设备，拒绝授权不影响手工圈选。
3. 选择月份与网别、填写事由，提交查询。任务可取消、分页查看和导出 XLSX。
4. 默认脱敏；明文操作必须有明文权限。结果和导出只属于本人，区域权限收回后再次访问受限。

轻量设计：不含 TOTP、审批、覆盖导入、导入回滚、去重视图、配置页、审计哈希链；前端使用 Vue 原生表单与共享状态，减少 UI/状态依赖。

## 验证

```powershell
cd backend
..\.venv\Scripts\python.exe -m pytest -q
..\.venv\Scripts\python.exe -m compileall -q app
cd ../frontend
npm run typecheck
npm run build
```

单元测试通过 mock/纯函数验证，不创建测试数据库；显式 `app.demo --verify` 使用独立系统库中的合成数据，已通过真实远程 MySQL 验收。运行故障可通过 `/api/health` 判定数据库可达性，错误响应不会暴露 SQL、号码或密码。

实际验证结果见 [docs/VERIFICATION.md](docs/VERIFICATION.md)。离线导入模板为 [docs/stations-template.csv](docs/stations-template.csv)，也可登录管理页下载。坐标系在导入时选择，模板不包含业务示例数据。

未设置天地图 Key 时保留可交互地图画布并提示配置缺失；不回退到其他底图。

## 维护

- 配置与表映射通过 `.env`、`datasource.yaml` 修改，重启后生效。
- 后端必须单进程（workers=1），空间索引和线程任务在进程内维护。
- 重启后未完成任务标记失败；成功结果及导出按 TTL 清理，失败或取消任务不提供部分明细。
- 更新前使用 MySQL 官方工具备份 `bsq_app`，凭据通过选项文件或交互输入，不把密码直接放进命令；后续表结构变化执行明确 SQL，不使用迁移框架。
- 不要改已有明细表。MySQL 明细查询需 `(month_id,lac,cell_id)` 索引或等效分区；大数据量查询性能依赖实际库。
