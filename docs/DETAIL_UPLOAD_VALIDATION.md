# 明细上传迭代验证（2026-10-14）

新增独立 detail_upload.py / DetailUploadPane.vue，无新增类或数据库表。仅修改原模块的路由注册、管理标签、返回地图时刷新月份，以及阻止基站接口误访问明细批次。原查询方法保持原逻辑。

验证结果：

- Python 全部源文件 py_compile 通过；新增模块及测试 ruff check 通过。
- mock 单元测试全套 57 项通过：管理员/分析员接口权限、批次归属、重复确认、多月份、已有月份拒绝、无效行、GB18030、XLSX 只读迭代及关闭、超限清理、无敏感日志、写入失败不提交、确认异常关闭事务并释放网别锁。
- 前端 npm run typecheck / npm run build 通过。第三方 leaflet-geoman CSS source map 提示和打包体积警告仍存在，不影响构建成功。
- 本机 600000 行合成 CSV 校验：有效，27.49 秒，tracemalloc 峰值 5.08 MiB；临时文件自动删除。这是解析校验测量，不能代表端到端导入速度、进程 RSS 或 XLSX 性能。
- 真实数据库仅 SELECT information_schema.TABLES：bsq_app.detail_local/detail_other 均存在且为 InnoDB；没有读取、输出号码或 UID，没有写入数据库。

真实数据库验证限制：本轮未执行真实明细写入、60万行数据库导入、并发真实连接或网络中断验证；未运行浏览器端端到端和 XLSX 大文件性能测试。上线验收须使用授权数据验证事务回滚、导入时间和资源容量。已有 max_rows 查询限制未改变，导入60万行并不表示单次查询可返回60万行。

上传文件存放被忽略的 DATA_DIR/detail_uploads；成功后删除，24小时到期后访问拒绝并删除，下次上传清理过期批次。没有独立历史/进度/模板下载功能；格式样例见 docs/samples。
