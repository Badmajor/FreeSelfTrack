from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
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


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(200))

    projects: Mapped[list["Project"]] = relationship(back_populates="organization")


class OrganizationMember(Base):
    __tablename__ = "organization_members"

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[UUID] = mapped_column(primary_key=True)

    __table_args__ = (Index("ix_organization_members_user_id", "user_id"),)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))

    organization: Mapped[Organization] = relationship(back_populates="projects")
    statuses: Mapped[list["ProjectStatus"]] = relationship(
        back_populates="project", order_by="ProjectStatus.position", cascade="all, delete-orphan"
    )
    tasks: Mapped[list["Task"]] = relationship(back_populates="project")


class ProjectMember(Base):
    __tablename__ = "project_members"

    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[UUID] = mapped_column(primary_key=True)

    __table_args__ = (Index("ix_project_members_user_id", "user_id"),)


class ProjectStatus(Base):
    __tablename__ = "project_statuses"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    position: Mapped[int] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    project: Mapped[Project] = relationship(back_populates="statuses")
    tasks: Mapped[list["Task"]] = relationship(back_populates="status")

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
    created_by: Mapped[UUID] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    project: Mapped[Project] = relationship(back_populates="tasks")
    status: Mapped[ProjectStatus] = relationship(back_populates="tasks")

    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "status_id"],
            ["project_statuses.project_id", "project_statuses.id"],
            ondelete="RESTRICT",
            name="fk_tasks_project_status_same_project",
        ),
    )
