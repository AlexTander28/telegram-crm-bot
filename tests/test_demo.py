from __future__ import annotations

from pathlib import Path

import openpyxl
import pytest

from app.demo import build_demo


@pytest.mark.asyncio
async def test_demo_builds_repeatable_local_artifacts(tmp_path: Path) -> None:
    summary = await build_demo(tmp_path / "data" / "crm.sqlite3", tmp_path / "reports")

    assert summary["synthetic"] is True
    assert summary["total"] == 12
    assert summary["by_status"] == {
        "new": 3,
        "in_progress": 4,
        "postponed": 2,
        "done": 3,
    }
    assert summary["overdue_new"] == 1
    assert (tmp_path / "data" / "sample_leads.csv").exists()
    workbook = openpyxl.load_workbook(tmp_path / "reports" / "leads.xlsx")
    assert workbook.sheetnames == ["Заявки", "История", "Сводка"]

