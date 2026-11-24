from datetime import datetime
from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from src.config.database import Base


class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(120), unique=True)
    password_hash: Mapped[str] = mapped_column(String(150))
    role: Mapped[str] = mapped_column(String(16))


class Course(Base):
    __tablename__ = 'courses'
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    title: Mapped[str] = mapped_column(String(100))
    seats: Mapped[int]
    category: Mapped[str] = mapped_column(String(50))


class Enrollment(Base):
    __tablename__ = 'enrollments'
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True)
    venue: Mapped[str] = mapped_column(String(80), index=True)
    state: Mapped[str] = mapped_column(String(12))
    codes: Mapped[list] = mapped_column(JSON)
    family_key: Mapped[str] = mapped_column(String(64), index=True, default='')


class Experiment(Base):
    __tablename__ = 'ab_experiments'
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(100))
    course_a: Mapped[str] = mapped_column(String(32))
    course_b: Mapped[str] = mapped_column(String(32))
    state: Mapped[str] = mapped_column(String(12), index=True, default='running')
    author_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    note: Mapped[str] = mapped_column(Text, default='')
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Assignment(Base):
    """家庭分组记录。同一家庭全局唯一一条；first_venue 记录首次进组的场馆。"""
    __tablename__ = 'ab_assignments'
    id: Mapped[int] = mapped_column(primary_key=True)
    experiment_id: Mapped[int] = mapped_column(ForeignKey('ab_experiments.id'), index=True)
    family_key: Mapped[str] = mapped_column(String(64), index=True)
    group: Mapped[str] = mapped_column(String(12))
    first_venue: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (UniqueConstraint('experiment_id', 'family_key', name='uq_assignment_experiment_family'),)


class Analysis(Base):
    __tablename__ = 'linkage_reviews'
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(16), index=True)
    parameters: Mapped[dict] = mapped_column(JSON)
    snapshot: Mapped[list] = mapped_column(JSON)
    result: Mapped[dict | None] = mapped_column(JSON)
    author_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    note: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Audit(Base):
    __tablename__ = 'audits'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    action: Mapped[str] = mapped_column(String(40))
    subject: Mapped[str] = mapped_column(String(100))
    recorded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
