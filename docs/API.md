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
auth.py 导出 current_user(request,db=Depends(get_db))、require_admin、require_query、visible_filter(user)、cell_visible(user,station)、user_payload；get_db/SessionLocal 在 db.py。
stations.py 导出 invalidate_index()、validate_cells(db,user,keys) → 去重授权有效 Station 列表（无效/越权422/403）。
query.py 导出 router、start_maintenance()、stop_maintenance()；启动恢复任务、周期TTL清理。
audit.py 导出 log_event(db,user_id,action,params=None)，不自动 commit；仅摘要，不含号码/uid。

## 当前默认明细来源

`bsq_app.detail_local`（本网，含 uid）及 `bsq_app.detail_other`（异网，无 uid），公共字段为 month_id、device_number、cell_name、street_name、lac、cell_id。索引 `(month_id,lac,cell_id)`；`is_demo` 标记合成数据。初始化命令创建空表，显式 demo 命令写入模拟数据；在线查询只执行 SELECT。
