from __future__ import annotations

from html import escape
from pathlib import Path

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, FSInputFile, Message

from app.keyboards import LeadAction, manager_keyboard
from app.models import Lead, LeadStatus
from app.services.export_service import export_workbook
from app.services.lead_service import LeadNotFoundError, LeadService, StatusTransitionError


router = Router(name="manager")

STATUS_LABELS = {
    LeadStatus.NEW: "новая",
    LeadStatus.IN_PROGRESS: "в работе",
    LeadStatus.POSTPONED: "отложена",
    LeadStatus.DONE: "закрыта",
}


def _is_manager(user_id: int | None, manager_ids: frozenset[int]) -> bool:
    return user_id is not None and user_id in manager_ids


def _lead_line(lead: Lead) -> str:
    return (
        f"<b>#{lead.id}</b> · {escape(lead.service_type)} · "
        f"{STATUS_LABELS[lead.status]}\n"
        f"{escape(lead.name)} · {escape(lead.phone)}"
    )


@router.callback_query(LeadAction.filter())
async def change_lead_status(
    query: CallbackQuery,
    callback_data: LeadAction,
    lead_service: LeadService,
    manager_ids: frozenset[int],
) -> None:
    user_id = query.from_user.id if query.from_user else None
    if not _is_manager(user_id, manager_ids):
        await query.answer("Действие доступно только менеджеру.", show_alert=True)
        return
    try:
        target = LeadStatus(callback_data.action)
        lead = await lead_service.change_status(
            callback_data.lead_id, target, actor_id=int(user_id)
        )
    except (ValueError, LeadNotFoundError, StatusTransitionError) as error:
        await query.answer(str(error), show_alert=True)
        return
    await query.answer(f"Статус: {STATUS_LABELS[lead.status]}")
    if query.message:
        await query.message.edit_text(
            _lead_line(lead), reply_markup=manager_keyboard(lead.id, lead.status)
        )


@router.message(Command("leads"))
async def list_leads(
    message: Message, lead_service: LeadService, manager_ids: frozenset[int]
) -> None:
    if not _is_manager(message.from_user.id if message.from_user else None, manager_ids):
        await message.answer("Команда доступна только менеджеру.")
        return
    leads = await lead_service.list_recent(limit=10)
    if not leads:
        await message.answer("Заявок пока нет.")
        return
    await message.answer("<b>Последние заявки</b>\n\n" + "\n\n".join(_lead_line(lead) for lead in leads))


@router.message(Command("stats"))
async def show_stats(
    message: Message, lead_service: LeadService, manager_ids: frozenset[int]
) -> None:
    if not _is_manager(message.from_user.id if message.from_user else None, manager_ids):
        await message.answer("Команда доступна только менеджеру.")
        return
    stats = await lead_service.get_stats()
    await message.answer(
        "<b>Состояние очереди</b>\n\n"
        f"Всего: {stats.total}\n"
        f"Новые: {stats.by_status['new']}\n"
        f"В работе: {stats.by_status['in_progress']}\n"
        f"Отложены: {stats.by_status['postponed']}\n"
        f"Закрыты: {stats.by_status['done']}\n"
        f"Новые старше 2 часов: {stats.overdue_new}"
    )


@router.message(Command("export"))
async def export_leads(
    message: Message,
    lead_service: LeadService,
    manager_ids: frozenset[int],
    export_path: Path,
) -> None:
    if not _is_manager(message.from_user.id if message.from_user else None, manager_ids):
        await message.answer("Команда доступна только менеджеру.")
        return
    path = await export_workbook(lead_service, export_path)
    await message.answer_document(
        FSInputFile(path), caption="Выгрузка заявок, истории и сводки."
    )
