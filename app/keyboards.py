from __future__ import annotations

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.models import LeadStatus


SERVICES = {
    "telegram_bot": "Telegram-бот",
    "crm": "CRM",
    "excel_report": "Excel-отчёт",
    "ai_assistant": "AI-помощник",
}


class FormAction(CallbackData, prefix="form"):
    action: str


class ServiceChoice(CallbackData, prefix="service"):
    code: str


class LeadAction(CallbackData, prefix="lead"):
    action: str
    lead_id: int


def start_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Оставить заявку",
                    callback_data=FormAction(action="start").pack(),
                )
            ]
        ]
    )


def service_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=label,
                callback_data=ServiceChoice(code=code).pack(),
            )
        ]
        for code, label in SERVICES.items()
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirmation_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Подтвердить",
                    callback_data=FormAction(action="confirm").pack(),
                ),
                InlineKeyboardButton(
                    text="Отменить",
                    callback_data=FormAction(action="cancel").pack(),
                ),
            ]
        ]
    )


def manager_keyboard(lead_id: int, status: LeadStatus) -> InlineKeyboardMarkup:
    actions: list[tuple[str, str]] = []
    if status in {LeadStatus.NEW, LeadStatus.POSTPONED}:
        actions.append(("Взять в работу", LeadStatus.IN_PROGRESS.value))
    if status in {LeadStatus.NEW, LeadStatus.IN_PROGRESS}:
        actions.append(("Отложить", LeadStatus.POSTPONED.value))
    if status in {LeadStatus.IN_PROGRESS, LeadStatus.POSTPONED}:
        actions.append(("Закрыть", LeadStatus.DONE.value))
    rows = [
        [
                InlineKeyboardButton(
                    text=label,
                    callback_data=LeadAction(action=action, lead_id=lead_id).pack(),
                )
                for label, action in actions
        ]
    ] if actions else []
    return InlineKeyboardMarkup(inline_keyboard=rows)
