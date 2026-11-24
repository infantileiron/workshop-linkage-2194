from enum import StrEnum


class Role(StrEnum):
    MANAGER = 'manager'
    ANALYST = 'analyst'
    VIEWER = 'viewer'


class Status(StrEnum):
    QUEUED = 'queued'
    RUNNING = 'running'
    COMPLETED = 'completed'
    FAILED = 'failed'
    PUBLISHED = 'published'


class Group(StrEnum):
    COMBO = 'combo'        # 组合推荐：两门课一起推
    SINGLE = 'single'      # 单课推荐


class TestState(StrEnum):
    RUNNING = 'running'    # 实验进行中，仍可登记分组
    ENDED = 'ended'        # 到期，进入对账口径，分组冻结
