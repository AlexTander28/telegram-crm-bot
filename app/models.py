from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class LeadStatus(str, Enum):
    NEW = "new"
    IN_PROGRESS = "in_progress"
    POSTPONED = "postponed"
    DONE = "done"


@dataclass(frozen=True, slots=True)
class LeadCreate:
    name: str
    phone: str
    service_type: str
    comment: str
    preferred_time: str
    source: str = "telegram"


@dataclass(frozen=True, slots=True)
class Lead:
    id: int
    created_at: datetime
    name: str
    phone: str
    service_type: str
    comment: str
    preferred_time: str
    status: LeadStatus
    manager_id: int | None
    source: str


@dataclass(frozen=True, slots=True)
class StatusHistoryEntry:
    id: int
    lead_id: int
    changed_at: datetime
    from_status: LeadStatus | None
    to_status: LeadStatus
    actor_id: int | None


@dataclass(frozen=True, slots=True)
class LeadStats:
    total: int
    by_status: dict[str, int]
    overdue_new: int
    overdue_ids: tuple[int, ...]

