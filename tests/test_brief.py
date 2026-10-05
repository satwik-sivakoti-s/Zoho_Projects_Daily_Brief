"""Unit tests for status classification and Flock formatting (no live APIs)."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

from services.brief import build_flockml, build_plain_preview, group_tasks_by_person
from services.config import Settings
from services.zoho import TaskRow, ZohoProjectsClient, normalize_task_name


def _client() -> ZohoProjectsClient:
    settings = Settings(
        zoho_accounts_domain="https://accounts.zoho.in",
        zoho_projects_domain="https://projectsapi.zoho.in",
        zoho_client_id="id",
        zoho_client_secret="secret",
        zoho_refresh_token="refresh",
        zoho_portal_id="1",
        flock_webhook_url="https://example.com/hook",
        cron_secret="test-secret",
        include_completed=False,
        timezone_name="Asia/Kolkata",
        deadline_date_order="DMY",
        skip_weekends=True,
    )
    return ZohoProjectsClient(settings, client=MagicMock())


def test_normalize_task_name_strips_key() -> None:
    assert normalize_task_name("[AJ7P-T24] Industry Pages Revamp", "AJ7P-T24") == (
        "Industry Pages Revamp"
    )
    assert normalize_task_name("AJ7P-T24 - Industry Pages Revamp") == (
        "Industry Pages Revamp"
    )
    assert normalize_task_name("Industry Pages Revamp") == "Industry Pages Revamp"


def test_classify_completed() -> None:
    status = _client()._classify_status(
        {"completed": True, "end_date": "01-01-2020"},
        today=date(2026, 10, 5),
    )
    assert status == "Completed"


def test_classify_delayed() -> None:
    status = _client()._classify_status(
        {"completed": False, "end_date": "01-10-2026", "status": {"type": "open"}},
        today=date(2026, 10, 5),
    )
    assert status == "Delayed"


def test_classify_on_track() -> None:
    status = _client()._classify_status(
        {"completed": False, "end_date": "10-10-2026", "status": {"type": "open"}},
        today=date(2026, 10, 5),
    )
    assert status == "On Track"


def test_group_and_format() -> None:
    tasks = [
        TaskRow(
            "Bob",
            "Write brief",
            "2026-10-06",
            "On Track",
            "Ops",
            tasklist_name="Daily Ops",
        ),
        TaskRow(
            "Alice",
            "Greenonion changes",
            "2026-10-01",
            "Delayed",
            "App",
            tasklist_name="Swap Pixel & Greenonion",
        ),
        TaskRow(
            "Alice",
            "Brand Context ingestion",
            "2026-10-02",
            "Delayed",
            "App",
            tasklist_name="Analytics Dashboard",
        ),
    ]
    grouped = group_tasks_by_person(tasks)
    assert list(grouped.keys()) == ["Alice", "Bob"]

    flockml = build_flockml(tasks, timezone_name="Asia/Kolkata")
    assert "Alice" in flockml
    assert "Swap Pixel &amp; Greenonion" in flockml or "Swap Pixel & Greenonion" in flockml
    assert "Analytics Dashboard" in flockml
    assert "&emsp;•" in flockml
    assert flockml.startswith("<flockml>")
    assert flockml.endswith("</flockml>")
    preview = build_plain_preview(tasks)
    assert "Task - 2 · Delayed - 2 · Completed - 0" in preview
    assert "Swap Pixel & Greenonion" in preview
    assert "Analytics Dashboard" in preview
    assert "\t• Greenonion changes · 2026-10-01 · Delayed" in preview
    assert "\t• Brand Context ingestion · 2026-10-02 · Delayed" in preview
    assert "\t• Write brief · 2026-10-06 · On Track" in preview
