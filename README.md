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

本机数据库保留了带 `DEMO-` 标记的模拟数据。需要重新生成并验收时，先停止后端，在 Windows 项目根目录执行：

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
cd backend
..\.venv\Scripts\python.exe -m app.demo --verify
```

完成后重新启动后端。该命令会生成模拟明细、导入模拟基站并验收查询导出，模拟结果不能作为真实业务结果。

更多信息：[接口说明](docs/API.md) · [验证记录](docs/VERIFICATION.md) · [基站模板](docs/stations-template.csv)。Linux Compose 配置已提供，尚未在 Linux 实测。
