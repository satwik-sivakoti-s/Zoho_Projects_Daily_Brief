"""Build and send the daily Flock brief."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
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


def _parse_task_deadline(deadline: str) -> date | None:
    value = (deadline or "").strip()
    if not value or value == "—":
        return None
    try:
        return date.fromisoformat(value.split(" ")[0])
    except ValueError:
        return None


def _is_deadline_too_far(
    task: TaskRow, *, today: date, hide_if_deadline_days_ahead: int
) -> bool:
    """Hide open tasks whose deadline is 7+ days away (configurable)."""
    if hide_if_deadline_days_ahead <= 0:
        return False
    if task.status == "Delayed":
        return False
    parsed = _parse_task_deadline(task.deadline)
    if parsed is None:
        return False
    days_until = (parsed - today).days
    return days_until >= hide_if_deadline_days_ahead


def _tasks_in_brief_scope(
    tasks: list[TaskRow],
    *,
    today: date,
    hide_if_deadline_days_ahead: int,
) -> list[TaskRow]:
    return [
        task
        for task in tasks
        if not _is_deadline_too_far(
            task,
            today=today,
            hide_if_deadline_days_ahead=hide_if_deadline_days_ahead,
        )
    ]


def _tasks_for_display(
    tasks: list[TaskRow],
    *,
    show_completed_in_list: bool,
    today: date,
    hide_if_deadline_days_ahead: int,
) -> list[TaskRow]:
    scoped = _tasks_in_brief_scope(
        tasks,
        today=today,
        hide_if_deadline_days_ahead=hide_if_deadline_days_ahead,
    )
    if show_completed_in_list:
        return scoped
    return [task for task in scoped if task.status != "Completed"]


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


def _render_person_hierarchy_plain(
    tasks: list[TaskRow],
    *,
    show_completed_in_list: bool,
    today: date,
    hide_if_deadline_days_ahead: int,
) -> str:
    """
    Satwik
    Task - n · Delayed - n · Completed - n

    Swap Pixel & Greenonion
        • task · deadline · status

    Analytics Dashboard
        • task · deadline · status
    """
    lines: list[str] = []
    visible = _tasks_for_display(
        tasks,
        show_completed_in_list=show_completed_in_list,
        today=today,
        hide_if_deadline_days_ahead=hide_if_deadline_days_ahead,
    )
    by_list = group_tasks_by_tasklist(visible)
    for tasklist_name, list_tasks in by_list.items():
        if not list_tasks:
            continue
        lines.append(tasklist_name)
        for task in list_tasks:
            lines.append(f"\t• {_task_detail_plain(task)}")
        lines.append("")
    return "\n".join(lines).rstrip()


def _join_flockml_lines(parts: list[str]) -> str:
    """Mobile Flock ignores self-closing <br/> and HTML entities like &emsp;."""
    return "<br>".join(parts).rstrip()


def _render_person_hierarchy_flockml(
    tasks: list[TaskRow],
    *,
    show_completed_in_list: bool,
    today: date,
    hide_if_deadline_days_ahead: int,
) -> str:
    parts: list[str] = []
    visible = _tasks_for_display(
        tasks,
        show_completed_in_list=show_completed_in_list,
        today=today,
        hide_if_deadline_days_ahead=hide_if_deadline_days_ahead,
    )
    by_list = group_tasks_by_tasklist(visible)
    for tasklist_name, list_tasks in by_list.items():
        if not list_tasks:
            continue
        parts.append(f"<b>{escape(tasklist_name)}</b>")
        for task in list_tasks:
            # Plain spaces — mobile Flock shows &emsp; literally
            parts.append(f"  • {_task_detail_flockml(task)}")
        parts.append("")
    return _join_flockml_lines(parts)


def build_flockml(
    tasks: list[TaskRow],
    *,
    timezone_name: str = "Asia/Kolkata",
    show_completed_in_list: bool = False,
    hide_if_deadline_days_ahead: int = 7,
    today: date | None = None,
) -> str:
    now = datetime.now(ZoneInfo(timezone_name))
    if today is None:
        today = now.date()
    date_label = now.strftime("%d %b %Y")
    grouped = group_tasks_by_person(tasks)

    scoped_total = 0
    visible_people = 0
    for person_tasks in grouped.values():
        scoped = _tasks_in_brief_scope(
            person_tasks,
            today=today,
            hide_if_deadline_days_ahead=hide_if_deadline_days_ahead,
        )
        if scoped:
            visible_people += 1
            scoped_total += len(scoped)

    parts = [
        f"<b>Zoho Projects Daily Brief</b> — {escape(date_label)}",
        f"Total tasks: {scoped_total} | People: {visible_people}",
        "",
    ]

    if scoped_total == 0:
        parts.append("No tasks due within the next week.")
        return f"<flockml>{_join_flockml_lines(parts)}</flockml>"

    for person, person_tasks in grouped.items():
        scoped = _tasks_in_brief_scope(
            person_tasks,
            today=today,
            hide_if_deadline_days_ahead=hide_if_deadline_days_ahead,
        )
        if not scoped:
            continue
        parts.append(f"<b>{escape(person)}</b>")
        parts.append(_person_summary_line(scoped, html=True))
        parts.append(
            _render_person_hierarchy_flockml(
                person_tasks,
                show_completed_in_list=show_completed_in_list,
                today=today,
                hide_if_deadline_days_ahead=hide_if_deadline_days_ahead,
            )
        )
        parts.append("")

    return f"<flockml>{_join_flockml_lines(parts)}</flockml>"


def _parse_flock_response(response: httpx.Response) -> dict:
    if not response.content:
        return {"ok": True}
    try:
        return response.json()
    except ValueError:
        return {"ok": True, "raw": response.text}


def send_to_flock(settings: Settings, flockml: str, plain_text: str | None = None) -> dict:
    """Incoming webhooks only accept ``text`` and/or ``flockml`` (no attachments)."""
    # Full plain body as fallback — mobile clients sometimes ignore FlockML breaks.
    notification = plain_text or "Zoho Projects Daily Brief"

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


def build_plain_preview(
    tasks: list[TaskRow],
    *,
    show_completed_in_list: bool = False,
    hide_if_deadline_days_ahead: int = 7,
    today: date | None = None,
    timezone_name: str = "Asia/Kolkata",
) -> str:
    if today is None:
        today = datetime.now(ZoneInfo(timezone_name)).date()
    grouped = group_tasks_by_person(tasks)
    lines = ["Zoho Projects Daily Brief", ""]
    for person, person_tasks in grouped.items():
        scoped = _tasks_in_brief_scope(
            person_tasks,
            today=today,
            hide_if_deadline_days_ahead=hide_if_deadline_days_ahead,
        )
        if not scoped:
            continue
        lines.append(person)
        lines.append(_person_summary_line(scoped, html=False))
        lines.append("")
        lines.append(
            _render_person_hierarchy_plain(
                person_tasks,
                show_completed_in_list=show_completed_in_list,
                today=today,
                hide_if_deadline_days_ahead=hide_if_deadline_days_ahead,
            )
        )
        lines.append("")
    return "\n".join(lines).strip()
