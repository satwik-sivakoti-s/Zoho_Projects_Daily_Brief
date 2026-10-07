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
        show_completed_in_list=True,
        timezone_name="Asia/Kolkata",
        deadline_date_order="DMY",
        skip_weekends=True,
        hide_if_deadline_days_ahead=5,
    )
    return ZohoProjectsClient(settings, client=MagicMock())


_TODAY = date(2026, 10, 5)


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


def test_classify_zoho_status_names() -> None:
    client = _client()
    today = date(2026, 10, 5)
    assert (
        client._classify_status(
            {"completed": False, "status": {"name": "Open", "type": "open"}},
            today=today,
        )
        == "Open"
    )
    assert (
        client._classify_status(
            {"completed": False, "status": {"name": "In Progress", "type": "open"}},
            today=today,
        )
        == "In Progress"
    )
    assert (
        client._classify_status(
            {"completed": False, "status": {"name": "In Review", "type": "open"}},
            today=today,
        )
        == "In Review"
    )
    assert (
        client._classify_status(
            {"completed": False, "status": {"name": "On Hold", "type": "open"}},
            today=today,
        )
        == "On Hold"
    )
    assert (
        client._classify_status(
            {"completed": False, "status": {"name": "Delayed", "type": "open"}},
            today=today,
        )
        == "Delayed"
    )


def test_classify_does_not_override_open_when_past_deadline() -> None:
    status = _client()._classify_status(
        {
            "completed": False,
            "end_date": "01-10-2026",
            "status": {"name": "Open", "type": "open"},
        },
        today=date(2026, 10, 5),
    )
    assert status == "Open"


def test_group_and_format() -> None:
    tasks = [
        TaskRow(
            "Bob",
            "Write brief",
            "2026-10-06",
            "Open",
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
            "In Progress",
            "App",
            tasklist_name="Analytics Dashboard",
        ),
    ]
    grouped = group_tasks_by_person(tasks)
    assert list(grouped.keys()) == ["Alice", "Bob"]

    flockml = build_flockml(tasks, timezone_name="Asia/Kolkata", today=_TODAY)
    assert "<b>== Alice ==</b>" in flockml
    assert "<b>== Bob ==</b>" in flockml
    assert flockml.count("----") >= 2
    assert "[Swap Pixel &amp; Greenonion]" in flockml or "[Swap Pixel & Greenonion]" in flockml
    assert "[Analytics Dashboard]" in flockml
    assert "  • Greenonion changes · due 01 Oct · <b>Delayed</b>" in flockml
    assert "  • Brand Context ingestion · due 02 Oct · <b>In Progress</b>" in flockml
    assert "2026-10-01" not in flockml  # ISO dates auto-link on mobile
    assert "&emsp;" not in flockml
    assert "<br>" in flockml
    assert "<br/>" not in flockml
    assert flockml.startswith("<flockml>")
    assert flockml.endswith("</flockml>")
    preview = build_plain_preview(tasks, today=_TODAY)
    assert "== Alice ==" in preview
    assert "----" in preview
    assert "Task - 2 · Delayed - 1 · Completed - 0" in preview
    assert "[Swap Pixel & Greenonion]" in preview
    assert "[Analytics Dashboard]" in preview
    assert "\t• Greenonion changes · due 01 Oct · Delayed" in preview
    assert "\t• Brand Context ingestion · due 02 Oct · In Progress" in preview
    assert "\t• Write brief · due 06 Oct · Open" in preview


def test_completed_tasks_shown_in_list_by_default() -> None:
    tasks = [
        TaskRow("Alice", "Done task", "2026-09-01", "Completed", "App", "List A"),
        TaskRow("Alice", "Open task", "2026-10-08", "Open", "App", "List A"),
        TaskRow("Alice", "Review task", "2026-10-07", "In Review", "App", "List A"),
    ]
    preview = build_plain_preview(tasks, today=_TODAY)
    assert "Task - 3 · Delayed - 0 · Completed - 1" in preview
    assert "Done task" in preview
    assert "Open task" in preview
    assert "Review task" in preview
    assert "· Completed" in preview
    assert "· In Review" in preview

    hidden = build_plain_preview(
        tasks, show_completed_in_list=False, today=_TODAY
    )
    assert "Done task" not in hidden
    assert "Open task" in hidden


def test_hide_tasks_with_deadline_five_or_more_days_away() -> None:
    tasks = [
        TaskRow("Bob", "Soon", "2026-10-09", "Open", "Ops", "List"),  # 4 days
        TaskRow("Bob", "Far", "2026-10-10", "Open", "Ops", "List"),  # 5 days
        TaskRow("Bob", "Later", "2026-10-20", "Open", "Ops", "List"),
    ]
    preview = build_plain_preview(tasks, today=_TODAY)
    assert "Soon" in preview
    assert "Far" not in preview
    assert "Later" not in preview
    assert "Task - 1 ·" in preview

    flockml = build_flockml(tasks, today=_TODAY)
    assert "Soon" in flockml
    assert "Far" not in flockml
