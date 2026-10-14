# BSQ 基站圈选查询系统

导入基站 → 地图圈选 → 按月查询本网/异网 → 查看并导出 Excel。

## 1. Windows 启动服务

### 首次安装和配置

安装 **Python 3.11+、Node.js 22.12+ 和 Git**。打开 PowerShell：

```powershell
git clone https://gitee.com/edengiteeBOOK/map-loc-project.git
cd map-loc-project
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
Copy-Item .env.example .env
notepad .env
```

在 `.env` 填写 MySQL 和天地图信息：

```dotenv
MYSQL_HOST=你的MySQL地址
MYSQL_PORT=3306
MYSQL_USER=你的数据库账号
MYSQL_PASSWORD=你的数据库密码
APP_DATABASE=bsq_app
TIANDITU_KEY=你的天地图Key
```

使用已有的远程 MySQL，账号需能创建及读写 `bsq_app`。**本机当前项目已配置并初始化，可以跳过以上步骤。**

首次初始化数据库，按提示设置管理员账号和密码，再安装前端依赖：

```powershell
cd backend
..\.venv\Scripts\python.exe -m app.init_db
cd ..\frontend
npm.cmd ci
```

已有表和管理员不会被覆盖。初始化只创建空表，不生成模拟数据。

### 每次启动

打开 **两个 PowerShell 窗口**，将下面的路径换成你的项目目录。

窗口一：启动后端。

```powershell
cd D:\CodexProject\mapWeb\backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

窗口二：启动前端。

```powershell
cd D:\CodexProject\mapWeb\frontend
npm.cmd run dev -- --host 127.0.0.1 --port 5173
```

浏览器打开 **http://127.0.0.1:5173**。保持两个窗口运行；停止时分别按 `Ctrl+C`。

首次登录须改密。本机管理员凭据见 `backend/data/initial-admin.txt`，演示分析员凭据见 `backend/data/demo-login.json`。这些文件不会上传 Git；新克隆项目使用初始化时设置的账号。

## 2. 迁移到 Linux 并运行

服务器需安装 **Git、Docker Engine、Docker Compose 插件**，并能连接远程 MySQL。

### 下载和配置

```bash
git clone https://gitee.com/edengiteeBOOK/map-loc-project.git
cd map-loc-project
cp .env.example .env
nano .env
```

填写与 Windows 相同的 MySQL 信息和天地图 Key，或自行安全复制 Windows 的 `.env` 到项目根目录。`.env` 不在 Git 仓库中。

继续使用同一个 MySQL 的 `bsq_app` 时，账号、基站和查询记录都还在，**不用迁移数据库或重建管理员**。如果换了 MySQL，先备份并恢复原 `bsq_app`，再修改 `.env` 的连接信息。

### 构建和启动

```bash
docker compose build
# 首次部署执行，已有表和管理员会保留
docker compose run --rm backend python -m app.init_db
docker compose up -d
```

浏览器打开 **http://服务器IP:8080**，服务器防火墙需开放 8080。Docker 运行网站和后端，不包含 MySQL。

Linux 使用 Docker 数据卷保存临时上传、导出文件。Windows 的 `backend/data` 无需复制，迁移后可以重新上传文件、重新导出结果。

### 常用命令

```bash
# 查看服务状态
docker compose ps
# 查看后端日志
docker compose logs --tail=100 backend
# 修改 .env 后重新创建服务，使配置生效
docker compose up -d --force-recreate
# 更新代码并重新构建运行
git pull
docker compose up -d --build
# 停止服务，保留数据卷
docker compose down
```

“当前定位”需要 **HTTPS 或 localhost**。普通服务器 IP 的 HTTP 地址可圈选查询，但无法使用浏览器定位。需要定位时配置 HTTPS 反向代理，并设置 `.env` 中的 `COOKIE_SECURE=true`。

## 3. 基本功能

- **账号管理**：新建、编辑、停用用户，配置区县、营服和明文权限。
- **基站管理**：CSV/XLSX 导入、列映射、坐标预览、错误报告、增量更新、编辑和停用。
- **地图选择**：天地图、站点聚合、搜索、矩形/多边形/圆形圈选和点选；支持当前定位、精度圈和中心坐标。
- **号码查询**：选择月份和本网/异网，填写事由后提交；查看进度、取消、分页和号码数量统计。
- **结果导出**：默认脱敏，有权限时可查看明文；XLSX 包含本网明细、异网明细和摘要。
- **我的查询**：查看自己的历史任务、复用条件。结果和导出文件默认保留 24 小时。

管理员可使用全部菜单、查询所有有效小区和查看明文；分析员按授权区域查询，空范围不可查询。所有用户只能访问自己的任务。

操作顺序：**登录 → 导入基站 → 地图圈选 → 选择月份/网别 → 查询 → 查看或导出**。

### 数据说明

默认本网表为 `bsq_app.detail_local`，异网表为 `bsq_app.detail_other`。接入其他来源时修改 `backend/datasource.yaml` 并重启后端。基站导入只导入地图站点，不生成号码明细。

初始化只创建空表，正式使用前应清理演示数据。下面的命令均须先停止后端，避免查询或导入与清理同时运行。脚本仅允许写入 `bsq_app`；不删除数据库、表结构、管理员或普通业务明细。

#### Windows：生成与清理

在项目根目录安装验收依赖，然后进入后端目录：

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
cd backend
# 只生成合成明细和演示分析员（不导入地图基站）
..\.venv\Scripts\python.exe -m app.demo
# 生成并验收：包含模拟基站、查询、分页及导出
..\.venv\Scripts\python.exe -m app.demo --verify
# 验收后清理模拟数据，恢复正式使用状态；可重复执行
..\.venv\Scripts\python.exe -m app.demo --clean
```

按需选择生成命令，不必连续执行两种生成方式。`--verify` 需要可用的 MySQL、已初始化的系统表及天地图配置。演示分析员凭据写入被忽略的 `backend/data/demo-login.json`；模拟结果不能作为真实业务结果。

#### Linux Compose

```bash
docker compose stop backend
# 仅生成模拟明细和演示账号
docker compose run --rm backend python -m app.demo
# 可选：生成并验收（运行容器内临时安装验收依赖）
docker compose run --rm backend sh -c "pip install --user httpx==0.28.1 && python -m app.demo --verify"
# 正式使用前清理模拟数据
docker compose run --rm backend python -m app.demo --clean
docker compose up -d backend
```

清理范围：两张自有明细表中 `is_demo=true` 的行、保留 LAC `990000` 下四个带精确模拟名称和区域标记的小区、演示分析员及其会话/导入/日志、仅使用这些模拟小区的查询任务与结果/导出，以及演示凭据和验收报告。其余账号、业务小区、`is_demo=false` 明细及管理员凭据保留。遇到模拟标记被修改、混合业务与模拟小区任务或运行中的模拟任务时停止清理，不模糊匹配删除；先核对相关数据后重试。

`--clean` 与 `--verify` 不可同时使用。清理完成后重新启动后端，地图空间索引会重新加载。缓存、浏览器截图与构建产物不属于数据库内容，也不会上传 Git。

更多信息：[接口说明](docs/API.md) · [验证记录](docs/VERIFICATION.md) · [基站模板](docs/stations-template.csv)。Linux Compose 配置已提供，尚未在 Linux 实测。

## 4. 项目结构

前端按业务面板组织 Vue 组件；后端按功能域组织 controller、service、DTO 三层，采用 Python 模块及函数命名：

```text
mapWeb/
├── frontend/                        # Vue 3 / TypeScript / Leaflet
│   ├── src/
│   │   ├── main.ts / App.vue         # 应用入口、登录及工作台
│   │   ├── MapPane.vue              # 地图、圈选及查询结果
│   │   ├── AdminPane.vue            # 账号与基站维护/导入
│   │   ├── DetailUploadPane.vue     # 用户信息（号码明细）导入
│   │   └── api.ts / types.ts / style.css # API 封装、类型、共享样式
│   └── package.json / package-lock.json / vite.config.ts / tsconfig.json
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI 装配、异常处理、生命周期
│   │   ├── controllers/             # auth / stations / query / detail_upload / system
│   │   ├── services/                # 同功能域业务、事务及任务运行状态
│   │   ├── dto/                     # auth / stations / query 请求模型
│   │   ├── dependencies.py          # 身份、权限及 CSRF 依赖
│   │   ├── config.py / db.py / models.py # 配置、MySQL 连接、ORM 模型
│   │   ├── datasource.py / detail_schema.py # 明细来源与自有表定义
│   │   ├── geo.py / audit.py         # 坐标工具、摘要日志
│   │   └── init_db.py / inspect_db.py / demo.py # 初始化、结构检查、模拟数据命令
│   ├── tests/                       # mock 业务、权限与分层回归测试
│   ├── datasource.yaml              # 明细查询表/字段白名单映射
│   └── requirements.in / requirements.txt / requirements-dev.txt / pyproject.toml
├── deploy/                          # 后端/Web Dockerfile、Caddyfile
├── compose.yaml                     # Linux 服务编排
├── docs/                            # PLAN/API、验证记录、基站模板、模拟导入样例
├── .env.example / .env              # 配置示例；.env 仅本地保留，不进 Git
└── AGENTS.md / .gitignore / .gitattributes / .dockerignore
```

controller 负责请求参数与依赖注入，统一委派 service；DTO 保留现有字段和校验。事务、授权复核、MySQL 网别锁、查询线程池及空间索引均留在对应 service。旧同名模块仅保留明确的兼容导出；新功能和测试直接导入分层模块。详细迁移对应见[接口说明](docs/API.md)。

`backend/data/` 为本地运行文件，`.venv/`、`frontend/node_modules/` 为开发依赖；这些目录均保留但不提交。浏览器验收截图、缓存及 `frontend/dist/` 可重新生成，2026-10-14 的清理已将其可恢复归档到项目外，不影响源码、配置或数据库。

在项目根目录执行后端检查：

```powershell
.\.venv\Scripts\python.exe -m compileall -q backend/app backend/tests
.\.venv\Scripts\python.exe -m pytest backend/tests -q
.\.venv\Scripts\python.exe -m ruff check backend/app backend/tests
```
