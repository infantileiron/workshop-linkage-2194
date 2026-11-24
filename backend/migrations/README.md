初始结构由 `src/models/entities.py` 中 SQLAlchemy 元数据定义。小型单机演示首次启动时以 `create_all` 建表。保留持久卷升级时，需先为字段变更编写并验证迁移。

已提供的增量迁移（PostgreSQL，幂等，可重复执行）：

- `001_ab_experiment.sql`：为 `enrollments` 增加 `family_key` 列与索引，并新建 `ab_experiments`、`ab_assignments` 两张表。

执行方式（容器运行中）：

```bash
docker compose exec -T db psql -U workshop -d workshop -f /dev/stdin < backend/migrations/001_ab_experiment.sql
```

升级注意：旧报名的 `family_key` 为空，不会进入实验对账分母；接入实验前需按业务侧家庭映射回填，再通过分组登记接口让家庭领组。
