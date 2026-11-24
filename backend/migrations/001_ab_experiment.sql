-- 推荐实验（组合 vs 单课）功能的增量迁移，PostgreSQL 16，可重复执行。
-- 全新环境仍由 SQLAlchemy `create_all` 建表；本脚本仅用于保留数据卷的升级。
-- 用法：
--   docker compose exec -T db psql -U workshop -d workshop -f /dev/stdin < migrations/001_ab_experiment.sql

BEGIN;

-- 1. 报名台账增加家庭标识（实验分组与对账的连接键）。
ALTER TABLE enrollments ADD COLUMN IF NOT EXISTS family_key VARCHAR(64) NOT NULL DEFAULT '';
CREATE INDEX IF NOT EXISTS ix_enrollments_family_key ON enrollments (family_key);

-- 2. 推荐实验表。
CREATE TABLE IF NOT EXISTS ab_experiments (
    id         SERIAL PRIMARY KEY,
    title      VARCHAR(100) NOT NULL,
    course_a   VARCHAR(32)  NOT NULL,
    course_b   VARCHAR(32)  NOT NULL,
    state      VARCHAR(12)  NOT NULL DEFAULT 'running',
    author_id  INTEGER      NOT NULL REFERENCES users (id),
    note       TEXT         NOT NULL DEFAULT '',
    result     JSON,
    created_at TIMESTAMP    NOT NULL DEFAULT now(),
    ended_at   TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_ab_experiments_state ON ab_experiments (state);
-- 已存在旧表时补齐到期冻结结果列。
ALTER TABLE ab_experiments ADD COLUMN IF NOT EXISTS result JSON;

-- 3. 家庭分组记录表：同一实验下家庭唯一，跨馆同组，仅一条记录。
CREATE TABLE IF NOT EXISTS ab_assignments (
    id            SERIAL PRIMARY KEY,
    experiment_id INTEGER     NOT NULL REFERENCES ab_experiments (id),
    family_key    VARCHAR(64) NOT NULL,
    "group"       VARCHAR(12) NOT NULL,
    first_venue   VARCHAR(80) NOT NULL,
    created_at    TIMESTAMP   NOT NULL DEFAULT now(),
    CONSTRAINT uq_assignment_experiment_family UNIQUE (experiment_id, family_key)
);
CREATE INDEX IF NOT EXISTS ix_ab_assignments_experiment_id ON ab_assignments (experiment_id);
CREATE INDEX IF NOT EXISTS ix_ab_assignments_family_key ON ab_assignments (family_key);

COMMIT;

-- 升级后请确认历史报名的家庭标识：旧数据 family_key 为空，不会进入实验分母；
-- 新录入的报名必须带 family_key。如需把历史台账接入实验，请按业务侧家庭映射回填后再登记分组。
