from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


class ConfigurationError(RuntimeError):
    """Raised when the bot cannot start safely with the current environment."""


@dataclass(frozen=True, slots=True)
class Settings:
    bot_token: str
    manager_chat_id: int
    manager_ids: frozenset[int]
    database_path: Path
    export_path: Path

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        token = os.getenv("BOT_TOKEN", "").strip()
        if not token or token == "replace_with_botfather_token":
            raise ConfigurationError("BOT_TOKEN не задан. Скопируйте .env.example в .env.")

        try:
            manager_chat_id = int(os.getenv("MANAGER_CHAT_ID", "0"))
        except ValueError as error:
            raise ConfigurationError("MANAGER_CHAT_ID должен быть целым числом.") from error
        if manager_chat_id == 0:
            raise ConfigurationError("MANAGER_CHAT_ID не задан.")

        raw_ids = [value.strip() for value in os.getenv("MANAGER_IDS", "").split(",")]
        try:
            manager_ids = frozenset(int(value) for value in raw_ids if value)
        except ValueError as error:
            raise ConfigurationError("MANAGER_IDS должен содержать Telegram ID через запятую.") from error
        if not manager_ids:
            raise ConfigurationError("Добавьте хотя бы один ID в MANAGER_IDS.")

        return cls(
            bot_token=token,
            manager_chat_id=manager_chat_id,
            manager_ids=manager_ids,
            database_path=Path(os.getenv("DATABASE_PATH", "data/crm.sqlite3")),
            export_path=Path(os.getenv("EXPORT_PATH", "reports/leads.xlsx")),
        )

