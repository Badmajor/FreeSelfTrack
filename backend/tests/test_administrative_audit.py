from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.audit import request_id
from app.models import AdministrativeAuditEvent, SecurityEvent, TaskHistory, User
from app.repositories.administrative_audit import AdministrativeAuditRepository
from app.schemas.administrative_audit import (
    AdministrativeAuditWrite,
    AuditChange,
    WorkflowStatusSnapshot,
)
from app.services.administrative_audit import AdministrativeAuditService


def profile_change(actor=None, entity=None, **overrides):
    return AdministrativeAuditWrite(
        **{
            "actor_id": actor or uuid4(),
            "entity_type": "user",
            "entity_id": entity or uuid4(),
            "action": "profile_updated",
            "changes": (
                AuditChange(field="first_name", old="Before", new="After"),
                AuditChange(field="last_name", old="Old", new="New"),
            ),
            **overrides,
        }
    )


async def test_one_event_for_all_changed_fields_and_no_op(db_session):
    correlation = uuid4()
    token = request_id.set(correlation)
    try:
        service = AdministrativeAuditService(db_session)
        data = profile_change()
        event = service.record(data)
        assert event is not None
        assert (
            service.record(
                profile_change(changes=(AuditChange(field="first_name", old="Same", new="Same"),))
            )
            is None
        )
        assert service.record(profile_change(changes=())) is None
        await db_session.commit()
    finally:
        request_id.reset(token)
    rows = list(await db_session.scalars(select(AdministrativeAuditEvent)))
    assert len(rows) == 1
    assert rows[0].operation_id == correlation
    assert rows[0].actor_id == data.actor_id
    assert rows[0].entity_id == data.entity_id
    assert rows[0].changes == [
        {"field": "first_name", "old": "Before", "new": "After"},
        {"field": "last_name", "old": "Old", "new": "New"},
    ]
    assert rows[0].occurred_at is not None
    assert await db_session.scalar(select(func.count()).select_from(SecurityEvent)) == 0
    assert await db_session.scalar(select(func.count()).select_from(TaskHistory)) == 0


async def test_cascade_and_membership_card_events_share_operation(db_session):
    actor, subject, org, project, task = (uuid4() for _ in range(5))
    service = AdministrativeAuditService(db_session)
    now = datetime.now(UTC)
    for kind, target in (("organization", org), ("project", project), ("task", task)):
        service.record(
            AdministrativeAuditWrite(
                actor_id=actor,
                entity_type=kind,
                entity_id=target,
                action="archived",
                changes=(AuditChange(field="archived_at", old=None, new=now),),
            )
        )
    for kind, target in (("user", subject), ("organization", org)):
        service.record(
            AdministrativeAuditWrite(
                actor_id=actor,
                entity_type=kind,
                entity_id=target,
                subject_user_id=subject,
                action="member_added",
                changes=(
                    AuditChange(field="organization_id", old=None, new=org),
                    AuditChange(field="state", old=None, new="active"),
                    AuditChange(field="role", old=None, new="member"),
                ),
            )
        )
    await db_session.commit()
    rows = list(await db_session.scalars(select(AdministrativeAuditEvent)))
    assert len(rows) == 5
    assert len({row.id for row in rows}) == 5
    assert {row.operation_id for row in rows} == {service.operation_id}
    assert {row.entity_id for row in rows} == {subject, org, project, task}
    assert sum(row.action == "archived" for row in rows) == 3
    assert sum(row.subject_user_id == subject for row in rows) == 2


async def test_bootstrap_identity_and_workflow_allowlisted_snapshot(db_session):
    service = AdministrativeAuditService(db_session)
    service.record(
        profile_change(
            actor_id=None,
            actor_kind="bootstrap",
            action="system_role_changed",
            changes=(AuditChange(field="is_system_admin", old=False, new=True),),
        )
    )
    status = WorkflowStatusSnapshot(
        id=uuid4(), name="Review", position=4, is_active=True, is_completed=False
    )
    service.record(
        profile_change(
            entity_type="project",
            action="workflow_changed",
            changes=(AuditChange(field="statuses", old=(), new=(status,)),),
        )
    )
    await db_session.commit()
    rows = list(await db_session.scalars(select(AdministrativeAuditEvent)))
    assert rows[0].actor_kind == "bootstrap"
    assert rows[0].actor_id is None
    assert rows[1].changes[0]["new"] == [status.model_dump(mode="json")]


@pytest.mark.parametrize(
    "field",
    ["email", "password", "password_hash", "token", "ip", "comment", "filename", "details"],
)
def test_sensitive_or_unrestricted_fields_rejected_without_value_in_error(field):
    secret = "do-not-disclose-this-value"
    with pytest.raises(ValidationError) as error:
        AuditChange(field=field, old=None, new=secret)
    assert secret not in str(error.value)


@pytest.mark.parametrize(
    "action",
    [
        "viewed",
        "failed",
        "access_denied",
        "password_changed",
        "email_changed",
        "members_deactivated",
    ],
)
def test_excluded_actions_are_not_supported(action):
    with pytest.raises(ValidationError):
        profile_change(action=action)


@pytest.mark.parametrize(
    "overrides",
    [
        {"entity_type": "task"},
        {"actor_id": None},
        {"actor_kind": "bootstrap"},
        {"subject_user_id": uuid4()},
        {"changes": (AuditChange(field="is_active", old=True, new=False),)},
        {"changes": (AuditChange(field="name", old="a", new="b"),) * 2},
        {"changes": (AuditChange(field="first_name", old="a", new="b"),) * 2},
        {"action": "member_added", "changes": ()},
        {"email": "excluded@example.com"},
    ],
)
def test_event_policy_rejects_wrong_actor_entity_fields_or_membership_subject(overrides):
    with pytest.raises(ValidationError):
        profile_change(**overrides)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("role", "password-value"),
        ("state", "unknown"),
        ("is_active", "false"),
        ("is_active", 1),
        ("organization_id", "not-a-uuid"),
        ("archived_at", datetime(2026, 1, 1)),
        ("description", {"password": "not-allowed"}),
        ("statuses", ({"id": uuid4(), "password": "not-allowed"},)),
    ],
)
def test_change_values_are_typed_not_arbitrary_json(field, value):
    with pytest.raises(ValidationError):
        AuditChange(field=field, old=None, new=value)


async def test_rollback_removes_event_and_mutation(db_session):
    user = User(email="audit-rollback@example.com", password_hash="not-a-credential")
    db_session.add(user)
    await db_session.commit()
    user_id = user.id
    user.is_active = False
    AdministrativeAuditService(db_session).record(
        profile_change(
            entity=user_id,
            action="user_blocked",
            changes=(AuditChange(field="is_active", old=True, new=False),),
        )
    )
    await db_session.flush()
    await db_session.rollback()
    assert await db_session.scalar(select(User.is_active).where(User.id == user_id)) is True
    assert await db_session.scalar(select(func.count()).select_from(AdministrativeAuditEvent)) == 0


async def test_failed_audit_insert_cannot_commit_domain_change(db_session):
    user = User(email="audit-failure@example.com", password_hash="not-a-credential")
    db_session.add(user)
    await db_session.commit()
    user_id = user.id
    user.is_active = False
    event = AdministrativeAuditService(db_session).record(profile_change(entity=user_id))
    # Simulate persistence rejecting an event after the domain mutation was staged.
    event.actor_id = None
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()
    assert await db_session.scalar(select(User.is_active).where(User.id == user_id)) is True
    assert await db_session.scalar(select(func.count()).select_from(AdministrativeAuditEvent)) == 0


async def test_entity_pages_fixed_twenty_tied_times_and_concurrent_insertion(db_session):
    entity, actor = uuid4(), uuid4()
    timestamp = datetime(2026, 10, 5, tzinfo=UTC)
    service = AdministrativeAuditService(db_session)
    for value in range(1, 46):
        event = service.record(profile_change(actor=actor, entity=entity))
        event.id = UUID(int=value)
        event.occurred_at = timestamp
    # Neither a different ID nor a different entity type may leak into the result.
    service.record(profile_change())
    service.record(
        profile_change(
            entity=entity,
            entity_type="project",
            action="updated",
            changes=(AuditChange(field="name", old="Before", new="After"),),
        )
    )
    await db_session.commit()
    repository = AdministrativeAuditRepository(db_session)
    first = await repository.page_for_entity("user", entity)
    assert [row.id.int for row in first.items] == list(range(45, 25, -1))
    assert first.next_position is not None
    inserted = service.record(profile_change(actor=actor, entity=entity))
    inserted.occurred_at = timestamp + timedelta(seconds=1)
    await db_session.commit()
    second = await repository.page_for_entity("user", entity, after=first.next_position)
    third = await repository.page_for_entity("user", entity, after=second.next_position)
    assert [row.id.int for row in second.items] == list(range(25, 5, -1))
    assert [row.id.int for row in third.items] == [5, 4, 3, 2, 1]
    assert third.next_position is None
    refreshed = await repository.page_for_entity("user", entity)
    assert refreshed.items[0].id == inserted.id
    empty = await repository.page_for_entity("user", uuid4())
    assert empty.items == []
    assert empty.next_position is None
