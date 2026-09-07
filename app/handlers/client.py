from __future__ import annotations

from html import escape

from aiogram import Bot, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from app.keyboards import (
    SERVICES,
    FormAction,
    ServiceChoice,
    confirmation_keyboard,
    manager_keyboard,
    service_keyboard,
    start_keyboard,
)
from app.models import LeadCreate
from app.services.lead_service import LeadService, LeadValidationError, normalize_phone


router = Router(name="client")


class LeadForm(StatesGroup):
    name = State()
    phone = State()
    service = State()
    comment = State()
    preferred_time = State()
    confirmation = State()


def _summary(data: dict[str, str]) -> str:
    return (
        "<b>Проверьте заявку</b>\n\n"
        f"Имя: {escape(data['name'])}\n"
        f"Телефон: {escape(data['phone'])}\n"
        f"Услуга: {escape(data['service_type'])}\n"
        f"Комментарий: {escape(data['comment'] or '—')}\n"
        f"Удобное время: {escape(data['preferred_time'] or '—')}"
    )


@router.message(Command("start"))
async def start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "Здравствуйте. Я соберу заявку и передам её менеджеру без потери деталей.",
        reply_markup=start_keyboard(),
    )


@router.callback_query(FormAction.filter(F.action == "start"))
async def begin_form(query: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(LeadForm.name)
    await query.answer()
    if query.message:
        await query.message.answer("Как к вам обращаться?")


@router.message(LeadForm.name, F.text)
async def collect_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if len(name) < 2:
        await message.answer("Имя слишком короткое. Напишите минимум два символа.")
        return
    await state.update_data(name=name)
    await state.set_state(LeadForm.phone)
    await message.answer("Укажите телефон, например +7 999 123-45-67.")


@router.message(LeadForm.phone, F.text)
async def collect_phone(message: Message, state: FSMContext) -> None:
    try:
        phone = normalize_phone(message.text or "")
    except LeadValidationError as error:
        await message.answer(str(error))
        return
    await state.update_data(phone=phone)
    await state.set_state(LeadForm.service)
    await message.answer("Выберите услугу.", reply_markup=service_keyboard())


@router.callback_query(LeadForm.service, ServiceChoice.filter())
async def collect_service(
    query: CallbackQuery, callback_data: ServiceChoice, state: FSMContext
) -> None:
    service_type = SERVICES.get(callback_data.code)
    if service_type is None:
        await query.answer("Эта услуга больше недоступна.", show_alert=True)
        return
    await state.update_data(service_type=service_type)
    await state.set_state(LeadForm.comment)
    await query.answer()
    if query.message:
        await query.message.answer("Коротко опишите задачу. Если деталей нет — отправьте «—».")


@router.message(LeadForm.comment, F.text)
async def collect_comment(message: Message, state: FSMContext) -> None:
    comment = (message.text or "").strip()
    await state.update_data(comment="" if comment == "—" else comment)
    await state.set_state(LeadForm.preferred_time)
    await message.answer("Когда удобно связаться? Если неважно — отправьте «—».")


@router.message(LeadForm.preferred_time, F.text)
async def collect_time(message: Message, state: FSMContext) -> None:
    preferred_time = (message.text or "").strip()
    await state.update_data(preferred_time="" if preferred_time == "—" else preferred_time)
    await state.set_state(LeadForm.confirmation)
    await message.answer(
        _summary(await state.get_data()),
        reply_markup=confirmation_keyboard(),
    )


@router.callback_query(LeadForm.confirmation, FormAction.filter(F.action == "confirm"))
async def confirm_lead(
    query: CallbackQuery,
    state: FSMContext,
    lead_service: LeadService,
    bot: Bot,
    manager_chat_id: int,
) -> None:
    data = await state.get_data()
    lead = await lead_service.create_lead(
        LeadCreate(
            name=data["name"],
            phone=data["phone"],
            service_type=data["service_type"],
            comment=data["comment"],
            preferred_time=data["preferred_time"],
            source="telegram",
        )
    )
    await state.clear()
    await query.answer("Заявка сохранена")
    if query.message:
        await query.message.answer(
            f"Заявка <b>#{lead.id}</b> принята. Менеджер увидит все указанные данные."
        )
    await bot.send_message(
        manager_chat_id,
        (
            f"<b>Новая заявка #{lead.id}</b>\n"
            f"Клиент: {escape(lead.name)}\n"
            f"Телефон: {escape(lead.phone)}\n"
            f"Услуга: {escape(lead.service_type)}\n"
            f"Комментарий: {escape(lead.comment or '—')}\n"
            f"Удобное время: {escape(lead.preferred_time or '—')}"
        ),
        reply_markup=manager_keyboard(lead.id, lead.status),
    )


@router.callback_query(FormAction.filter(F.action == "cancel"))
async def cancel_form(query: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await query.answer("Отменено")
    if query.message:
        await query.message.answer("Заявка не сохранена.", reply_markup=start_keyboard())


@router.message(StateFilter("*"))
async def unexpected_input(message: Message) -> None:
    await message.answer("Используйте кнопки или команду /start, чтобы начать заново.")

