from datetime import UTC, date, datetime
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

TaskPriority = Literal["low", "normal", "major", "critical"]


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(Text, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_system_admin: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
    profile: Mapped["UserProfile"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )


class UserProfile(Base):
    __tablename__ = "user_profiles"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    user: Mapped[User] = relationship(back_populates="profile")


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(200))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    projects: Mapped[list["Project"]] = relationship(back_populates="organization")


class OrganizationMember(Base):
    __tablename__ = "organization_members"

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )

    role: Mapped[Literal["member", "manager"]] = mapped_column(
        String(16), default="member", server_default="member"
    )
    state: Mapped[Literal["active", "archived", "revoked"]] = mapped_column(
        String(16), default="active", server_default="active"
    )

    __table_args__ = (
        Index("ix_organization_members_user_id", "user_id"),
        CheckConstraint("role IN ('member', 'manager')", name="ck_organization_members_role"),
        CheckConstraint(
            "state IN ('active', 'archived', 'revoked')", name="ck_organization_members_state"
        ),
    )


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    organization: Mapped[Organization] = relationship(back_populates="projects")
    statuses: Mapped[list["ProjectStatus"]] = relationship(
        back_populates="project", order_by="ProjectStatus.position", cascade="all, delete-orphan"
    )
    tasks: Mapped[list["Task"]] = relationship(back_populates="project")


class ProjectTaskSequence(Base):
    __tablename__ = "project_task_sequences"

    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    next_number: Mapped[int] = mapped_column(Integer, default=1)

    project: Mapped[Project] = relationship()


class ProjectMember(Base):
    __tablename__ = "project_members"

    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )

    role: Mapped[Literal["member", "manager"]] = mapped_column(
        String(16), default="member", server_default="member"
    )
    state: Mapped[Literal["active", "archived", "revoked"]] = mapped_column(
        String(16), default="active", server_default="active"
    )

    __table_args__ = (
        Index("ix_project_members_user_id", "user_id"),
        CheckConstraint("role IN ('member', 'manager')", name="ck_project_members_role"),
        CheckConstraint(
            "state IN ('active', 'archived', 'revoked')", name="ck_project_members_state"
        ),
    )


class ProjectStatus(Base):
    __tablename__ = "project_statuses"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    position: Mapped[int] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False)

    project: Mapped[Project] = relationship(back_populates="statuses")
    tasks: Mapped[list["Task"]] = relationship(back_populates="status", overlaps="tasks")

    __table_args__ = (
        UniqueConstraint("project_id", "position", name="uq_project_statuses_project_position"),
        UniqueConstraint("project_id", "id", name="uq_project_statuses_project_id"),
    )


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    status_id: Mapped[UUID] = mapped_column(index=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    slug: Mapped[str] = mapped_column(String(80))
    sequence_number: Mapped[int] = mapped_column(Integer)
    created_by: Mapped[UUID] = mapped_column()
    reporter_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    assignee_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    story_points: Mapped[int | None] = mapped_column(Integer, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    priority: Mapped[TaskPriority | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    project: Mapped[Project] = relationship(back_populates="tasks", overlaps="tasks")
    status: Mapped[ProjectStatus] = relationship(back_populates="tasks", overlaps="project,tasks")
    reporter: Mapped[User] = relationship(foreign_keys=[reporter_id])
    assignee: Mapped[User | None] = relationship(foreign_keys=[assignee_id])
    history: Mapped[list["TaskHistory"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "status_id"],
            ["project_statuses.project_id", "project_statuses.id"],
            ondelete="RESTRICT",
            name="fk_tasks_project_status_same_project",
        ),
        UniqueConstraint("project_id", "slug", name="uq_tasks_project_slug"),
        UniqueConstraint("project_id", "sequence_number", name="uq_tasks_project_sequence"),
        CheckConstraint(
            "story_points IS NULL OR story_points IN (1, 2, 3, 5, 8, 13, 21)",
            name="ck_tasks_story_points_fibonacci",
        ),
        CheckConstraint(
            "priority IS NULL OR priority IN ('low', 'normal', 'major', 'critical')",
            name="ck_tasks_priority",
        ),
    )


class TaskLink(Base):
    __tablename__ = "task_links"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    task_a_id: Mapped[UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    task_b_id: Mapped[UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    relation_type: Mapped[str] = mapped_column(String(16))
    blocking_task_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), nullable=True
    )
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    creator: Mapped[User] = relationship(foreign_keys=[created_by])

    __table_args__ = (
        CheckConstraint("task_a_id < task_b_id", name="ck_task_links_canonical_pair"),
        CheckConstraint(
            "(relation_type = 'related' AND blocking_task_id IS NULL) OR "
            "(relation_type = 'blocks' AND blocking_task_id IN (task_a_id, task_b_id))",
            name="ck_task_links_type_direction",
        ),
        UniqueConstraint("task_a_id", "task_b_id", name="uq_task_links_pair"),
    )


class TaskHistory(Base):
    __tablename__ = "task_history"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    changed_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    from_status_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("project_statuses.id", ondelete="RESTRICT"), nullable=True
    )
    to_status_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("project_statuses.id", ondelete="RESTRICT"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(64), default="status_changed")
    field_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )

    task: Mapped[Task] = relationship(back_populates="history")
    actor: Mapped[User] = relationship(foreign_keys=[changed_by])

    __table_args__ = (Index("ix_task_history_task_created_at_id", "task_id", "created_at", "id"),)


class TaskWatcher(Base):
    __tablename__ = "task_watchers"

    task_id: Mapped[UUID] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )

    __table_args__ = (Index("ix_task_watchers_user_id", "user_id"),)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    recipient_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    task_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), nullable=True, index=True
    )
    event_type: Mapped[str] = mapped_column(String(64))
    message: Mapped[str] = mapped_column(String(500))
    event_data: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DeadlineNotificationDelivery(Base):
    __tablename__ = "deadline_notification_deliveries"

    task_id: Mapped[UUID] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True
    )
    due_date: Mapped[date] = mapped_column(Date, primary_key=True)
    recipient_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
