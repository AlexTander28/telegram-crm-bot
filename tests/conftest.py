from __future__ import annotations

from pathlib import Path

import pytest_asyncio

from app.database import Database
from app.services.lead_service import LeadService


@pytest_asyncio.fixture
async def service(tmp_path: Path) -> LeadService:
    database = Database(tmp_path / "test.sqlite3")
    await database.initialize()
    return LeadService(database)

