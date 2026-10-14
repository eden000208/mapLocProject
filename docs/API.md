# BSQ 轻量版接口契约

所有接口前缀 /api。JSON 错误 {code,message,trace_id}。时间 ISO UTC。
登录 Cookie bsq_session；/auth/me 返回 csrf_token；所有写请求带 X-CSRF-Token。
首次改密前只有 me/logout/change-password 可访问。坐标 [lng,lat]。

## 账号
POST /auth/login {username,password} → 用户（含 csrf_token）。GET /auth/me 同上。
用户 {id,username,name,role,is_active,view_plain,districts,service_centers,must_change_pwd,csrf_token}。
POST /auth/logout。POST /auth/change-password {old_password,new_password}。
GET /admin/users → 用户数组；POST /admin/users 与 PATCH /admin/users/{id}：用户名、姓名、密码（新建必填/更新可选）、role、is_active、view_plain、districts、service_centers。
GET /meta/scope-options → {districts:[],service_centers:[]}。

## 基站
GET /admin/stations?q=&page=1&size=50 → {items,total}。
PATCH /admin/stations/{id} → 编辑名称、区县、营服、坐标、is_active。
GET /admin/stations/template → CSV。
POST /admin/stations/import multipart file → {batch_id,headers,mapping,samples}。
POST /admin/stations/import/{batch}/preview {mapping,coord_sys} → {total,valid_count,error_count,warning_count,new_count,update_count,errors,warnings,points}。
points 为 [{station_name,raw:[lng,lat],WGS84:[lng,lat],GCJ02:[lng,lat],BD09:[lng,lat]}]（最多50）。
POST /admin/stations/import/{batch}/confirm → {imported,error_count}；GET .../errors → CSV。
GET /stations?bbox=west,south,east,north&zoom=12&q= → {items,truncated:false}。
items 可为站点 {kind:'station',station_name,lng,lat,cells:[{lac,cell_id,station_name,district,service_center,lng,lat}]} 或聚合 {kind:'cluster',lng,lat,count,bbox}。
POST /selections/resolve {type:'rect'|'polygon'|'circle'|'cells',geometry?,center?,radius?,cells?} → {cells,cell_count,station_count,excluded_count}。
rect/polygon 使用 GeoJSON Polygon，circle center=[lng,lat] radius 米；cells=[{lac,cell_id}]。

## 管理员明细上传

POST /admin/detail-import multipart {file,network:'local'|'other'} → {batch_id,network}。
POST /admin/detail-import/{batch_id}/preview → {network,months,rows,error_count,errors:[{row,message}],existing_months,valid}。
POST /admin/detail-import/{batch_id}/confirm → {imported,months}。
三个接口均 require_admin、CSRF 校验，批次仅上传本人访问；批次有效期24小时。成功后删除原文件，下次上传清理过期文件。
支持 CSV（UTF-8/GB18030）和单工作表 XLSX，200 MiB；固定英文列名允许调整列顺序。
公共列 month_id,device_number,cell_name,street_name,lac,cell_id；本网另有 uid。所有列必须存在；号码非空，名称/uid 可空。month_id 必须为 YYYYMM，lac/cell_id 为非负 BIGINT；号码100字符、uid200字符、名称255字符。文本标识建议在 Excel 中设为文本，禁止公式。
同网别可包含多个月；任一月份已有数据（含模拟数据）均拒绝，不覆盖、不追加、不去重；错误整批拒绝，预览最多显示100条无原始值错误。无号码/uid预览，无历史页、进度页或模板下载。
固定写入 bsq_app.detail_local/detail_other，is_demo=false；配置与目标不匹配则拒绝，SQL 值绑定。同网别确认使用 MySQL GET_LOCK 互斥，确认再次完整校验并检查月份，1000行批量写入，明细、批次状态与摘要日志同一事务提交；失败回滚。

## 查询
GET /meta/months?nets=local,other → {months:[]}。
POST /queries {cells:[{lac,cell_id}],months:[],nets:[],purpose} → 任务对象。
GET /queries?page=&size= → {items,total}；GET /queries/{id} → 任务对象。
任务含 id,status,cell_keys,months,nets,purpose,rows_local,rows_other,uniq_local,uniq_other,completed_batches,total_batches,error,created_at,expire_at。
POST /queries/{id}/cancel。GET /queries/{id}/rows?net=local&page=1&size=50&plain=false → {items,total}。
POST /queries/{id}/export?plain=false → 下载 XLSX（前端 blob）。
有 plain 权限仍默认脱敏；管理员可查询全部有效小区并显式查看明文，分析员按当前区域及明文授权操作。结果读/导出始终校验任务本人归属。
GET /config → {tianditu_key,map_center:[lng,lat],map_zoom,min_draw_zoom,max_cells,max_months}。
GET /health → {status:'ok'|'unavailable'}，无数据库连接时503。

## 后端共享约定

`app/controllers/` 仅声明路由、请求参数和 FastAPI 依赖，并调用同功能域的 `app/services/`；`app/dto/` 存放原有 Pydantic 请求模型及校验器。所有已有 HTTP 路径、参数默认值、模型名称和响应契约保持不变。

`dependencies.py` 导出 `current_user(request, db=Depends(get_db))`、`require_admin`、`require_query`，所有路由及测试 override 复用同一函数对象。`services/auth.py` 提供 `visible_filter(user)`、`cell_visible(user, station)`、`user_payload` 和账号业务。

`services/stations.py` 提供 `invalidate_index()`、`validate_cells(db, user, keys)` → 去重授权有效 Station 列表（无效/越权422/403），并统一持有空间索引与锁。

`services/query.py` 提供 `start_maintenance()`、`stop_maintenance()`；统一持有查询线程池、并发限额、恢复状态及 TTL 清理。`services/detail_upload.py` 保留明细上传全量校验、单事务写入及 MySQL 网别锁。`services/system.py` 提供健康检查及公开配置。

`get_db`/`SessionLocal` 位于 `db.py`；配置、ORM 模型、明细来源、坐标及日志仍为共享基础设施。`audit.py` 导出 `log_event(db, user_id, action, params=None)`，不自动 commit；仅摘要，不含号码/uid。

原 `app.auth`、`app.stations`、`app.query`、`app.detail_upload` 仅显式重导出旧入口，不保留第二份业务实现。新增代码直接从分层模块导入；业务测试 mock 应 patch 实现所在的 service，HTTP 依赖 override 使用 `dependencies` 中的函数。

### 原实现迁移对应

| 原位置 | 新位置 | 迁移内容 |
| --- | --- | --- |
| `app.auth` | `services/auth.py` | 原账号业务及辅助函数，共15个函数，函数体不变 |
| `app.auth` | `dependencies.py` | `current_user`、`require_admin`、`require_query`，函数体及依赖身份不变 |
| `app.auth` | `dto/auth.py` | `LoginBody`、`PasswordBody`、`UserBody`、`UserPatch` |
| `app.stations` | `services/stations.py` | 原19个函数、空间索引及锁 |
| `app.stations` | `dto/stations.py` | `PreviewBody`、`StationPatch`、`SelectionBody` |
| `app.query` | `services/query.py` | 原27个函数、`TaskInterrupted`、查询运行状态 |
| `app.query` | `dto/query.py` | `CellKey`、`QueryBody` |
| `app.detail_upload` | `services/detail_upload.py` | 原13个函数、导入常量及事务/网别锁边界 |
| `app.main` | `services/system.py` | `health`、`public_config` 原函数体 |
| 原业务模块及 `app.main` | `controllers/{auth,stations,query,detail_upload,system}.py` | 原29个 HTTP 操作的同名路由函数，原签名/默认值/依赖不变，仅委派 |

`main.py` 保留应用装配、异常处理和生命周期；生命周期调用 query service。服务函数不声明 `Depends`、`Query`、`File` 或 `Form`，所有路由参数由 controller 显式传入。未新增持久化层、数据表、数据库或迁移框架。

## 当前默认明细来源

`bsq_app.detail_local`（本网，含 uid）及 `bsq_app.detail_other`（异网，无 uid），公共字段为 month_id、device_number、cell_name、street_name、lac、cell_id。索引 `(month_id,lac,cell_id)`；`is_demo` 标记合成数据。初始化命令创建空表，显式 demo 命令写入模拟数据；在线查询只执行 SELECT。
