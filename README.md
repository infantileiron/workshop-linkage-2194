# 禾埠木作 · 工坊课程联报核查

禾埠木作由 6 位运营人员为 3 家木工体验场馆排周末班。运营每周从线下表单与场馆预约表整理已确认报名。单独计次会把同一报名的多个勾选重复算进分母，取消占位会抬高联报，整体热门场馆也会把跨场馆构成差误当成课程关联。本项目把报名台账、分场馆列联表和排课签核接起来，支持导出复核凭据给场馆店长。

| 角色 | 常用页面 | 权限与动作 |
|---|---|---|
| 课程分析员 `analyst` | 课程与名额、场馆报名、推荐实验、联报核查 | 录入课程和报名，登记家庭分组、建实验，锁定快照并运算，查看和下载结果 |
| 运营负责人 `manager` | 推荐实验、排课建议 | 分析员权限，另可将实验到期冻结、签核和查询操作审计 |
| 场馆观察员 `viewer` | 各模块 | 查阅目录、报名、实验对账与计算证据，下载 CSV |

## 周五工作剧本

1. 09:10 查对本周的 `11月场馆报名汇总.xlsx`，确认木雕浅刻 `WOOD-11` 每场 22 人，木片彩漆 `LACQ-24` 每场 20 人。模拟数据预置在程序中。
2. 09:25 在课程与名额核对榫卯入门 `JOIN-06` 及研磨封蜡 `SAND-18` 的课程编号。
3. 09:45 在场馆报名按河湾老仓过滤，核对 100 份确认报名及 1 份已取消报名。
4. 10:00 录入槐里快闪补单，独立保留取消记录，以场馆和报名编号追溯源文件。
5. 10:25 在联报核查锁定木雕和彩漆的报名快照，每馆至少 12 份有效报名。槐里快闪的样本量未达门槛。
6. 10:30 比对同口径合并优势比 1.0905 和分场馆调整优势比 0.4113，检查方向反转。
7. 11:00 运营负责人进入排课建议，签署「按场馆单独试排」。
8. 11:05 观察员下载已签核的 CSV 以便安排周末教室和讲师。

## 推荐实验：组合推荐多带来多少联报

家庭先随机领取「组合推荐」或「单课推荐」，再选课，用于衡量两门课一起推能多带来多少联报。规则与系统实现一一对应：

1. **先分组后选课**：家庭在「推荐实验」页登记领组，之后录入的报名才用于对账。
2. **跨馆同组**：同一家庭全局只有一条分组记录（`ab_assignments` 的 `(experiment_id, family_key)` 唯一约束）。家庭在另一场馆再次登记时直接返回原分组，`first_venue` 保留首次进组的场馆。
3. **馆内均衡**：新家庭在其登记场馆领取当前人数较少的一组，计数持平则由加盐哈希随机决定，使各馆首次进组家庭在两组尽量均衡。
4. **并发幂等**：并发登记同一家庭时，唯一约束兜底；冲突方回滚并回读最早登记成功的分组，重试不新增记录、不改变分组。
5. **到期冻结**：运营负责人执行「到期」后实验转为 `ended`，新家庭登记被拒绝（已登记家庭的重复请求仍幂等返回）；到期同时计算并把对账结果固化到 `ab_experiments.result`，之后报名台账的增改不再影响已签发的报告（进行中页面为实时预览）。
6. **对账口径**：以分组记录为分母，没有有效报名或仅有取消报名的家庭仍留在分母；家庭任意一份 `confirmed` 报名同时勾选两门目标课即记为联报（多份报名取课程并集）。
7. **分层比较**：按家庭**首次进组的场馆**比较两组联报率，给出百分点提升与相对提升；任一馆缺少任一组时该馆标记「样本不足」，不计算提升。报告可下载 CSV 复核。

实验接口：`GET/POST /api/experiments`、`GET /api/experiments/{id}`（对账报告）、`GET /api/experiments/{id}/export`、
`GET/POST /api/experiments/{id}/assignments`、`POST /api/experiments/{id}/end`。报名必须携带 `family_key` 才能进入实验口径。

## 启动

```bash
cp .env.example .env
docker compose up --build --wait
docker compose exec -T backend python -m scripts.seed_demo
```

打开 `http://localhost:18276`。FastAPI 文档位于 `http://localhost:19276/docs`，PostgreSQL 映射端口为 `17776`。示例邮箱为 `analyst@hemu.demo`、`manager@hemu.demo` 和 `viewer@hemu.demo`，密码均为 `Woodwork2026!`。

| 服务 | 技术与作用 |
|---|---|
| frontend | Nginx 1.27，原生 HTML/CSS/JS，`/api` 反代 |
| backend | Python 3.11、FastAPI、SQLAlchemy、JWT |
| worker | Python SQL 持久队列和 Redis 唤醒，计算后归档 JSON 至共享卷 |
| db | PostgreSQL 16，保存目录、报名、复核单和操作审计 |
| redis | Redis 7，唤醒计算并支撑健康探针 |

`FRONTEND_PORT`、`BACKEND_PORT`、`DB_PORT` 可覆盖本地映射。`SEED_DEMO` 控制初始化模拟数据。`JWT_SECRET` 与 `DB_PASSWORD` 可以通过 `.env` 覆盖。`frontend/src/pages` 是业务页面，`backend/src/services/association.py` 实现公式，`backend/src/services/experiment.py` 实现分组与对账。调试后端可沿用容器的 Python 环境执行 `docker compose exec -T backend python -m compileall src`。`docker compose down` 保留数据卷。

## 测试

后端测试基于 SQLite 与 SQLAlchemy，HTTP 用例另需 httpx（镜像未内置时可 `pip install httpx`）：

```bash
docker compose exec -T backend python tests/test_experiment_service.py   # 分组均衡/并发幂等/对账口径/冻结快照
docker compose exec -T backend python tests/test_experiment_api.py       # 路由、权限、状态码、并发请求
```

前端页面为原生 ESM，用 Node 原生加载器做无浏览器渲染冒烟（mock 掉 API 与会话）：

```bash
cd frontend/tests && node --experimental-loader ./loader.mjs test_frontend.mjs
```


## 计算口径

使用确认报名的自然键去重，按场馆拆 a（均报）、b（仅首课）、c（仅次课）、d（均未报）。同口径合并比是 `Σa × Σd / (Σb × Σc)`，Mantel–Haenszel 调整比是 `Σ(a×d/n) / Σ(b×c/n)`。不足最小样本量和某门课程没有比较边际的场馆仍列证据，计算时剔除。分母为零时显示「未定义」。两种比方向相反时提示分馆审阅。使用确定性模拟台账，每次提交保存独立快照，后续新增报名不改变旧单。场馆内混杂、同一申请人多单及体验前后顺序需要业务方另行核查。当前报告给出点估计和分层诊断，未计算区间或强制检验共同比假设。

共享枚举定义于 `backend/src/constants/enums.py` 和 `frontend/src/constants/enums.js`。角色出现在登录、前端会话与后端授权。核查状态出现在 worker、签核服务和排课建议页。报名状态出现在输入校验、台账页与分析口径。实验状态（`running`/`ended`）与分组（`combo`/`single`）出现在推荐实验服务与页面；实验服务在 `backend/src/services/experiment.py`。

MIT License，见 `LICENSE`。
