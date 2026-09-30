import json
from datetime import UTC, date, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DeadlineNotificationDelivery
from app.repositories.domain import DomainRepository


class DeadlineService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = DomainRepository(session)

    async def process_due(self, current_date: date | None = None, limit: int = 500) -> int:
        today = current_date or datetime.now(UTC).date()
        tasks = await self.repository.list_due_tasks(today, limit)
        for task in tasks:
            if task.assignee_id is None or task.due_date is None:
                continue
            self.session.add(
                DeadlineNotificationDelivery(
                    task_id=task.id,
                    due_date=task.due_date,
                    recipient_id=task.assignee_id,
                )
            )
            self.repository.add_notification(
                recipient_id=task.assignee_id,
                task_id=task.id,
                event_type="deadline_due",
                message=f"Deadline is today for {task.slug}",
                event_data=json.dumps(
                    {"project_id": str(task.project_id), "due_date": task.due_date.isoformat()},
                    separators=(",", ":"),
                ),
            )
        await self.session.commit()
        return len(tasks)
