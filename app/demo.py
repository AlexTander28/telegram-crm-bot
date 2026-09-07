from __future__ import annotations

import argparse
import asyncio
import csv
import json
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.database import Database
from app.models import LeadCreate, LeadStatus
from app.services.export_service import export_workbook
from app.services.lead_service import LeadService


DEMO_NOW = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)
DEMO_MANAGER_ID = 91001

DEMO_LEADS = [
    ("Анна Крылова", "+7 999 123-45-67", "Telegram-бот", "Бот для заявок с сайта", "после 16:00", 190, LeadStatus.NEW),
    ("Михаил Орлов", "8 913 444-20-10", "CRM", "Нужна очередь для двух менеджеров", "10:00–12:00", 105, LeadStatus.IN_PROGRESS),
    ("Елена Власова", "+7 913 555-02-41", "Excel-отчёт", "Еженедельная сводка продаж", "утро", 92, LeadStatus.DONE),
    ("Игорь Лапин", "9136668032", "AI-помощник", "Ответы по базе знаний", "после 18:00", 76, LeadStatus.POSTPONED),
    ("Дарья Соколова", "+7 913 110-22-31", "Telegram-бот", "Запись на консультацию", "любое", 64, LeadStatus.DONE),
    ("ООО Вектор", "8 (913) 007-19-90", "CRM", "Контроль статусов заявок", "14:00", 50, LeadStatus.IN_PROGRESS),
    ("Павел Юдин", "+7 913 810-47-22", "Excel-отчёт", "Свести три таблицы", "вечер", 42, LeadStatus.NEW),
    ("Мария Белова", "9139001133", "AI-помощник", "Классификация обращений", "11:00", 34, LeadStatus.POSTPONED),
    ("Никита Ершов", "+7 913 720-44-11", "Telegram-бот", "Уведомления о заказах", "любое", 27, LeadStatus.DONE),
    ("Студия Пиксель", "8 913 808-05-05", "CRM", "Мини-CRM без сложного внедрения", "15:30", 18, LeadStatus.IN_PROGRESS),
    ("Алексей Мартынов", "+7 913 330-12-00", "Excel-отчёт", "Проверка дублей", "утро", 11, LeadStatus.NEW),
    ("Ольга Титова", "9131020304", "AI-помощник", "Передача сложных вопросов человеку", "17:00", 6, LeadStatus.IN_PROGRESS),
]


async def seed_demo(service: LeadService) -> list[object]:
    existing = await service.list_all()
    if existing:
        return existing
    created = []
    for name, phone, service_type, comment, preferred_time, age_minutes, status in DEMO_LEADS:
        lead = await service.create_lead(
            LeadCreate(
                name=name,
                phone=phone,
                service_type=service_type,
                comment=comment,
                preferred_time=preferred_time,
                source="telegram-demo",
            ),
            created_at=DEMO_NOW - timedelta(minutes=age_minutes),
        )
        if status is LeadStatus.IN_PROGRESS:
            lead = await service.change_status(
                lead.id,
                LeadStatus.IN_PROGRESS,
                actor_id=DEMO_MANAGER_ID,
                changed_at=lead.created_at + timedelta(minutes=7),
            )
        elif status is LeadStatus.POSTPONED:
            lead = await service.change_status(
                lead.id,
                LeadStatus.POSTPONED,
                actor_id=DEMO_MANAGER_ID,
                changed_at=lead.created_at + timedelta(minutes=9),
            )
        elif status is LeadStatus.DONE:
            await service.change_status(
                lead.id,
                LeadStatus.IN_PROGRESS,
                actor_id=DEMO_MANAGER_ID,
                changed_at=lead.created_at + timedelta(minutes=5),
            )
            lead = await service.change_status(
                lead.id,
                LeadStatus.DONE,
                actor_id=DEMO_MANAGER_ID,
                changed_at=lead.created_at + timedelta(minutes=24),
            )
        created.append(lead)
    return created


def _write_csv(path: Path, leads: list[object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            ["id", "created_at", "name", "phone", "service_type", "status", "manager_id", "source"]
        )
        for lead in leads:
            writer.writerow(
                [
                    lead.id,
                    lead.created_at.isoformat(),
                    lead.name,
                    lead.phone,
                    lead.service_type,
                    lead.status.value,
                    lead.manager_id or "",
                    lead.source,
                ]
            )


async def build_demo(database_path: Path, reports_dir: Path, *, reset: bool = False) -> dict[str, object]:
    if reset and database_path.exists():
        database_path.unlink()
    database = Database(database_path)
    await database.initialize()
    service = LeadService(database)
    leads = await seed_demo(service)
    stats = await service.get_stats(now=DEMO_NOW)
    workbook_path = await export_workbook(service, reports_dir / "leads.xlsx")
    csv_path = database_path.parent / "sample_leads.csv"
    _write_csv(csv_path, leads)
    summary = {
        "generated_at": DEMO_NOW.isoformat(),
        "synthetic": True,
        "total": stats.total,
        "by_status": stats.by_status,
        "overdue_new": stats.overdue_new,
        "overdue_ids": list(stats.overdue_ids),
        "workbook": str(workbook_path.as_posix()),
        "database": str(database_path.as_posix()),
    }
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build synthetic Telegram CRM demo artifacts.")
    parser.add_argument("--database", type=Path, default=Path("data/crm.sqlite3"))
    parser.add_argument("--reports", type=Path, default=Path("reports"))
    parser.add_argument("--reset", action="store_true", help="Recreate only the selected demo database.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary = asyncio.run(build_demo(args.database, args.reports, reset=args.reset))
    print(
        "Demo created | "
        f"total={summary['total']} | "
        f"new={summary['by_status']['new']} | "
        f"in_progress={summary['by_status']['in_progress']} | "
        f"done={summary['by_status']['done']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

