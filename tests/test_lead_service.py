from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.models import LeadCreate, LeadStatus
from app.services.lead_service import LeadService, LeadValidationError, StatusTransitionError


def lead_input(**overrides: str) -> LeadCreate:
    values = {
        "name": "Анна Крылова",
        "phone": "8 (999) 123-45-67",
        "service_type": "Telegram-бот",
        "comment": "Нужен бот для заявок",
        "preferred_time": "После 16:00",
        "source": "telegram",
    }
    values.update(overrides)
    return LeadCreate(**values)


@pytest.mark.asyncio
async def test_client_can_create_auditable_lead(service: LeadService) -> None:
    lead = await service.create_lead(lead_input())

    assert lead.id == 1
    assert lead.phone == "+79991234567"
    assert lead.status is LeadStatus.NEW

    history = await service.get_history(lead.id)
    assert [(item.from_status, item.to_status, item.actor_id) for item in history] == [
        (None, LeadStatus.NEW, None)
    ]


@pytest.mark.asyncio
async def test_ambiguous_phone_is_rejected(service: LeadService) -> None:
    with pytest.raises(LeadValidationError, match="телефон"):
        await service.create_lead(lead_input(phone="12345"))


@pytest.mark.asyncio
async def test_manager_can_move_lead_through_workflow(service: LeadService) -> None:
    lead = await service.create_lead(lead_input())

    active = await service.change_status(lead.id, LeadStatus.IN_PROGRESS, actor_id=7001)
    done = await service.change_status(lead.id, LeadStatus.DONE, actor_id=7001)

    assert active.status is LeadStatus.IN_PROGRESS
    assert active.manager_id == 7001
    assert done.status is LeadStatus.DONE
    assert [item.to_status for item in await service.get_history(lead.id)] == [
        LeadStatus.NEW,
        LeadStatus.IN_PROGRESS,
        LeadStatus.DONE,
    ]


@pytest.mark.asyncio
async def test_closed_lead_cannot_return_to_queue(service: LeadService) -> None:
    lead = await service.create_lead(lead_input())
    await service.change_status(lead.id, LeadStatus.IN_PROGRESS, actor_id=7001)
    await service.change_status(lead.id, LeadStatus.DONE, actor_id=7001)

    with pytest.raises(StatusTransitionError, match="done"):
        await service.change_status(lead.id, LeadStatus.IN_PROGRESS, actor_id=7001)


@pytest.mark.asyncio
async def test_stats_report_queue_and_overdue_leads(service: LeadService) -> None:
    now = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)
    old = await service.create_lead(lead_input(name="Олег"), created_at=now - timedelta(hours=3))
    active = await service.create_lead(lead_input(name="Марина"), created_at=now - timedelta(minutes=40))
    closed = await service.create_lead(lead_input(name="Илья"), created_at=now - timedelta(minutes=20))
    await service.change_status(active.id, LeadStatus.IN_PROGRESS, actor_id=7001, changed_at=now)
    await service.change_status(closed.id, LeadStatus.IN_PROGRESS, actor_id=7001, changed_at=now)
    await service.change_status(closed.id, LeadStatus.DONE, actor_id=7001, changed_at=now)

    stats = await service.get_stats(now=now)

    assert stats.total == 3
    assert stats.by_status == {"new": 1, "in_progress": 1, "postponed": 0, "done": 1}
    assert stats.overdue_new == 1
    assert old.id in stats.overdue_ids


@pytest.mark.asyncio
async def test_recent_leads_are_returned_newest_first(service: LeadService) -> None:
    base = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)
    first = await service.create_lead(lead_input(name="Первая"), created_at=base)
    second = await service.create_lead(lead_input(name="Вторая"), created_at=base + timedelta(minutes=1))

    leads = await service.list_recent(limit=10)

    assert [lead.id for lead in leads] == [second.id, first.id]

