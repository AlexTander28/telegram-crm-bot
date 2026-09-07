from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

from app.database import Database
from app.models import Lead, LeadCreate, LeadStats, LeadStatus, StatusHistoryEntry


class LeadValidationError(ValueError):
    """Raised when client-supplied lead data cannot be accepted safely."""


class LeadNotFoundError(LookupError):
    """Raised when an operation targets a missing lead."""


class StatusTransitionError(ValueError):
    """Raised when a status change violates the workflow."""


ALLOWED_TRANSITIONS: dict[LeadStatus, frozenset[LeadStatus]] = {
    LeadStatus.NEW: frozenset({LeadStatus.IN_PROGRESS, LeadStatus.POSTPONED}),
    LeadStatus.IN_PROGRESS: frozenset({LeadStatus.POSTPONED, LeadStatus.DONE}),
    LeadStatus.POSTPONED: frozenset({LeadStatus.IN_PROGRESS, LeadStatus.DONE}),
    LeadStatus.DONE: frozenset(),
}


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).replace(microsecond=0).isoformat()


def _parse(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def normalize_phone(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    if len(digits) == 10 and digits.startswith("9"):
        digits = "7" + digits
    elif len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    if len(digits) != 11 or not digits.startswith("7") or digits[1] != "9":
        raise LeadValidationError("Укажите российский телефон в однозначном формате.")
    return "+" + digits


def _lead_from_row(row: object) -> Lead:
    return Lead(
        id=row["id"],
        created_at=_parse(row["created_at"]),
        name=row["name"],
        phone=row["phone"],
        service_type=row["service_type"],
        comment=row["comment"],
        preferred_time=row["preferred_time"],
        status=LeadStatus(row["status"]),
        manager_id=row["manager_id"],
        source=row["source"],
    )


def _history_from_row(row: object) -> StatusHistoryEntry:
    return StatusHistoryEntry(
        id=row["id"],
        lead_id=row["lead_id"],
        changed_at=_parse(row["changed_at"]),
        from_status=LeadStatus(row["from_status"]) if row["from_status"] else None,
        to_status=LeadStatus(row["to_status"]),
        actor_id=row["actor_id"],
    )


class LeadService:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def create_lead(
        self, payload: LeadCreate, *, created_at: datetime | None = None
    ) -> Lead:
        name = payload.name.strip()
        service_type = payload.service_type.strip()
        if len(name) < 2:
            raise LeadValidationError("Укажите имя длиной не менее двух символов.")
        if not service_type:
            raise LeadValidationError("Выберите услугу.")
        phone = normalize_phone(payload.phone)
        timestamp = created_at or _utc_now()

        async with self.database.connection() as connection:
            cursor = await connection.execute(
                """
                INSERT INTO leads (
                    created_at, name, phone, service_type, comment,
                    preferred_time, status, manager_id, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?)
                """,
                (
                    _iso(timestamp),
                    name,
                    phone,
                    service_type,
                    payload.comment.strip(),
                    payload.preferred_time.strip(),
                    LeadStatus.NEW.value,
                    payload.source.strip().lower() or "telegram",
                ),
            )
            lead_id = int(cursor.lastrowid or 0)
            await connection.execute(
                """
                INSERT INTO status_history (
                    lead_id, changed_at, from_status, to_status, actor_id
                ) VALUES (?, ?, NULL, ?, NULL)
                """,
                (lead_id, _iso(timestamp), LeadStatus.NEW.value),
            )
            await connection.commit()
            row = await (
                await connection.execute("SELECT * FROM leads WHERE id = ?", (lead_id,))
            ).fetchone()
        return _lead_from_row(row)

    async def get_lead(self, lead_id: int) -> Lead:
        async with self.database.connection() as connection:
            row = await (
                await connection.execute("SELECT * FROM leads WHERE id = ?", (lead_id,))
            ).fetchone()
        if row is None:
            raise LeadNotFoundError(f"Заявка #{lead_id} не найдена.")
        return _lead_from_row(row)

    async def change_status(
        self,
        lead_id: int,
        target: LeadStatus,
        *,
        actor_id: int,
        changed_at: datetime | None = None,
    ) -> Lead:
        timestamp = changed_at or _utc_now()
        async with self.database.connection() as connection:
            await connection.execute("BEGIN IMMEDIATE")
            row = await (
                await connection.execute("SELECT * FROM leads WHERE id = ?", (lead_id,))
            ).fetchone()
            if row is None:
                await connection.rollback()
                raise LeadNotFoundError(f"Заявка #{lead_id} не найдена.")
            current = LeadStatus(row["status"])
            if target not in ALLOWED_TRANSITIONS[current]:
                await connection.rollback()
                raise StatusTransitionError(
                    f"Переход {current.value} → {target.value} запрещён."
                )
            manager_id = actor_id if target is LeadStatus.IN_PROGRESS else row["manager_id"]
            await connection.execute(
                "UPDATE leads SET status = ?, manager_id = ? WHERE id = ?",
                (target.value, manager_id, lead_id),
            )
            await connection.execute(
                """
                INSERT INTO status_history (
                    lead_id, changed_at, from_status, to_status, actor_id
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (lead_id, _iso(timestamp), current.value, target.value, actor_id),
            )
            await connection.commit()
        return await self.get_lead(lead_id)

    async def list_recent(self, *, limit: int = 10) -> list[Lead]:
        safe_limit = max(1, min(limit, 100))
        async with self.database.connection() as connection:
            rows = await (
                await connection.execute(
                    "SELECT * FROM leads ORDER BY created_at DESC, id DESC LIMIT ?",
                    (safe_limit,),
                )
            ).fetchall()
        return [_lead_from_row(row) for row in rows]

    async def list_all(self) -> list[Lead]:
        async with self.database.connection() as connection:
            rows = await (
                await connection.execute("SELECT * FROM leads ORDER BY id")
            ).fetchall()
        return [_lead_from_row(row) for row in rows]

    async def get_history(self, lead_id: int) -> list[StatusHistoryEntry]:
        async with self.database.connection() as connection:
            rows = await (
                await connection.execute(
                    "SELECT * FROM status_history WHERE lead_id = ? ORDER BY id",
                    (lead_id,),
                )
            ).fetchall()
        return [_history_from_row(row) for row in rows]

    async def list_history(self) -> list[StatusHistoryEntry]:
        async with self.database.connection() as connection:
            rows = await (
                await connection.execute("SELECT * FROM status_history ORDER BY id")
            ).fetchall()
        return [_history_from_row(row) for row in rows]

    async def get_stats(self, *, now: datetime | None = None) -> LeadStats:
        timestamp = now or _utc_now()
        leads = await self.list_all()
        by_status = {status.value: 0 for status in LeadStatus}
        for lead in leads:
            by_status[lead.status.value] += 1
        threshold = timestamp.astimezone(UTC) - timedelta(hours=2)
        overdue_ids = tuple(
            lead.id
            for lead in leads
            if lead.status is LeadStatus.NEW and lead.created_at.astimezone(UTC) < threshold
        )
        return LeadStats(
            total=len(leads),
            by_status=by_status,
            overdue_new=len(overdue_ids),
            overdue_ids=overdue_ids,
        )

