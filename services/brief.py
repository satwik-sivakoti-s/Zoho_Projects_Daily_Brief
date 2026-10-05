"""Build and send the daily Flock brief."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

import httpx

from services.config import Settings
from services.zoho import TaskRow


def group_tasks_by_person(tasks: list[TaskRow]) -> dict[str, list[TaskRow]]:
    grouped: dict[str, list[TaskRow]] = defaultdict(list)
    for task in tasks:
        grouped[task.owner_name].append(task)
    return dict(sorted(grouped.items(), key=lambda item: item[0].lower()))


def group_tasks_by_tasklist(tasks: list[TaskRow]) -> dict[str, list[TaskRow]]:
    """Mirror Zoho's 'Grouped by Task List' view."""
    grouped: dict[str, list[TaskRow]] = defaultdict(list)
    for task in tasks:
        grouped[task.tasklist_name or "General"].append(task)
    return dict(sorted(grouped.items(), key=lambda item: item[0].lower()))


def _person_status_counts(tasks: list[TaskRow]) -> tuple[int, int, int]:
    total = len(tasks)
    delayed = sum(1 for t in tasks if t.status == "Delayed")
    completed = sum(1 for t in tasks if t.status == "Completed")
    return total, delayed, completed


def _person_summary_line(tasks: list[TaskRow], *, html: bool) -> str:
    total, delayed, completed = _person_status_counts(tasks)
    if html:
        return (
            f"<b>Task</b> - {total} · <b>Delayed</b> - {delayed} · "
            f"<b>Completed</b> - {completed}"
        )
    return f"Task - {total} · Delayed - {delayed} · Completed - {completed}"


def _status_label(status: str) -> str:
    # Incoming webhooks accept a small FlockML subset (no <font>, etc.).
    return f"<b>{escape(status)}</b>"


def _task_detail_plain(task: TaskRow) -> str:
    return f"{task.task_name} · {task.deadline} · {task.status}"


def _task_detail_flockml(task: TaskRow) -> str:
    return (
        f"{escape(task.task_name)} · {escape(task.deadline)} · "
        f"{_status_label(task.status)}"
    )


def _render_person_hierarchy_plain(tasks: list[TaskRow]) -> str:
    """
    Satwik
    Task - n · Delayed - n · Completed - n

    Swap Pixel & Greenonion
        • task · deadline · status

    Analytics Dashboard
        • task · deadline · status
    """
    lines: list[str] = []
    by_list = group_tasks_by_tasklist(tasks)
    for tasklist_name, list_tasks in by_list.items():
        lines.append(tasklist_name)
        for task in list_tasks:
            lines.append(f"\t• {_task_detail_plain(task)}")
        lines.append("")
    return "\n".join(lines).rstrip()


def _render_person_hierarchy_flockml(tasks: list[TaskRow]) -> str:
    parts: list[str] = []
    by_list = group_tasks_by_tasklist(tasks)
    for tasklist_name, list_tasks in by_list.items():
        parts.append(f"<b>{escape(tasklist_name)}</b>")
        for task in list_tasks:
            # &emsp; ≈ tab indent under the task-list title
            parts.append(f"&emsp;• {_task_detail_flockml(task)}")
        parts.append("")
    return "<br/>".join(parts).rstrip()


def build_flockml(tasks: list[TaskRow], *, timezone_name: str = "Asia/Kolkata") -> str:
    now = datetime.now(ZoneInfo(timezone_name))
    date_label = now.strftime("%d %b %Y")
    grouped = group_tasks_by_person(tasks)

    parts = [
        f"<b>Zoho Projects Daily Brief</b> — {escape(date_label)}",
        f"Total tasks: {len(tasks)} | People: {len(grouped)}",
        "",
    ]

    if not grouped:
        parts.append("No open tasks found.")
        inner = "<br/>".join(parts)
        return f"<flockml>{inner}</flockml>"

    for person, person_tasks in grouped.items():
        parts.append(f"<b>{escape(person)}</b>")
        parts.append(_person_summary_line(person_tasks, html=True))
        parts.append(_render_person_hierarchy_flockml(person_tasks))
        parts.append("")

    inner = "<br/>".join(parts).rstrip()
    return f"<flockml>{inner}</flockml>"


def _parse_flock_response(response: httpx.Response) -> dict:
    if not response.content:
        return {"ok": True}
    try:
        return response.json()
    except ValueError:
        return {"ok": True, "raw": response.text}


def send_to_flock(settings: Settings, flockml: str, plain_text: str | None = None) -> dict:
    """Incoming webhooks only accept ``text`` and/or ``flockml`` (no attachments)."""
    notification = plain_text or "Zoho Projects Daily Brief"
    if len(notification) > 200:
        notification = notification.splitlines()[0][:200]

    payload: dict[str, str] = {
        "text": notification,
        "flockml": flockml,
    }
    with httpx.Client(timeout=30.0) as client:
        response = client.post(settings.flock_webhook_url, json=payload)
        if response.status_code == 400 and "flockml" in payload:
            # Fallback: plain text only if FlockML is rejected
            response = client.post(
                settings.flock_webhook_url,
                json={"text": plain_text or notification},
            )
        response.raise_for_status()
        return _parse_flock_response(response)


def send_brief_to_flock(
    settings: Settings,
    _tasks: list[TaskRow],
    *,
    flockml: str,
    plain_text: str,
) -> dict:
    return send_to_flock(settings, flockml=flockml, plain_text=plain_text)


def build_plain_preview(tasks: list[TaskRow]) -> str:
    grouped = group_tasks_by_person(tasks)
    lines = ["Zoho Projects Daily Brief", ""]
    for person, person_tasks in grouped.items():
        lines.append(person)
        lines.append(_person_summary_line(person_tasks, html=False))
        lines.append("")
        lines.append(_render_person_hierarchy_plain(person_tasks))
        lines.append("")
    return "\n".join(lines).strip()
