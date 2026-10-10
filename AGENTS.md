# BSQ 轻量版

docs/PLAN.md 与 docs/API.md 为当前权威需求。
技术栈：FastAPI + SQLAlchemy/PyMySQL + MySQL、Vue3/TypeScript/Leaflet、Linux Compose/Caddy。
不引入 SQLite、迁移框架、Redis、Celery、TOTP、审批、复杂审计。
仅 bsq_app 可写；运行时明细查询仅 SELECT。用户于 2026-10-10 授权在 bsq_app 创建本网/异网表并写入明确标记的模拟数据用于验收，不创建额外测试数据库、不修改其他库。
真实号码及 uid 不写入日志、快照或 AI 输出。凭据只放被忽略的 .env。
MySQL 查询值必须绑定，表字段来自配置白名单。
权限只信后端；分析员无区域默认拒绝；管理员可使用全部菜单、全部有效小区及明文操作。任务只允许所属用户访问，读取和导出重新校验当前权限。
并行开发：主 agent 维护 config.py/db.py/models.py/main.py 与公共文档；子 agent 只改分配模块。
开发完成必须执行 Python 语法检查、mock 单元测试、前端 typecheck/build，记录真实数据库验证限制。
