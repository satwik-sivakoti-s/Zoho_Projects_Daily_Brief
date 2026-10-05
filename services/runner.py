"""Orchestrates fetch → format → Flock send."""

from __future__ import annotations

from typing import Any

from services.brief import build_flockml, build_plain_preview, send_brief_to_flock
from services.config import Settings
from services.zoho import ZohoProjectsClient


def run_daily_brief(settings: Settings | None = None, *, dry_run: bool = False) -> dict[str, Any]:
    settings = settings or Settings.from_env()

    with ZohoProjectsClient(settings) as zoho:
        tasks = zoho.fetch_all_task_rows()

    flockml = build_flockml(tasks, timezone_name=settings.timezone_name)
    preview = build_plain_preview(tasks)

    result: dict[str, Any] = {
        "task_count": len(tasks),
        "people_count": len({task.owner_name for task in tasks}),
        "preview": preview,
        "dry_run": dry_run,
    }

    if dry_run:
        result["flockml"] = flockml
        return result

    flock_response = send_brief_to_flock(
        settings,
        tasks,
        flockml=flockml,
        plain_text=preview,
    )
    result["flock_response"] = flock_response
    return result
