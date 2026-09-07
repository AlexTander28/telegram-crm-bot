from __future__ import annotations

import pytest

from app.config import ConfigurationError, Settings
from app.keyboards import LeadAction, SERVICES, manager_keyboard, service_keyboard
from app.models import LeadStatus


def test_settings_refuse_to_start_without_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BOT_TOKEN", raising=False)
    monkeypatch.setenv("MANAGER_CHAT_ID", "123")
    monkeypatch.setenv("MANAGER_IDS", "123")

    with pytest.raises(ConfigurationError, match="BOT_TOKEN"):
        Settings.from_env()


def test_service_keyboard_has_one_typed_callback_per_service() -> None:
    keyboard = service_keyboard()

    assert len(keyboard.inline_keyboard) == len(SERVICES)
    callbacks = [row[0].callback_data for row in keyboard.inline_keyboard]
    assert all(value and value.startswith("service:") for value in callbacks)


def test_closed_lead_has_no_stale_manager_actions() -> None:
    keyboard = manager_keyboard(42, LeadStatus.DONE)

    assert keyboard.inline_keyboard == []


def test_manager_callback_round_trip() -> None:
    packed = LeadAction(action="in_progress", lead_id=42).pack()
    unpacked = LeadAction.unpack(packed)

    assert unpacked.action == "in_progress"
    assert unpacked.lead_id == 42
