"""Zoho Projects OAuth + task fetching."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from services.config import Settings

_ZOHO_TASK_KEY_PREFIX = re.compile(
    r"^\[?(?P<key>[A-Z0-9]+-T\d+)\]?\s*[-:–—]?\s*",
    re.IGNORECASE,
)


def normalize_task_name(raw_name: str, task_key: str | None = None) -> str:
    """Strip Zoho task keys like AJ7P-T24 from display titles."""
    name = html.unescape((raw_name or "").strip())
    key = (task_key or "").strip()
    if key:
        for prefix in (f"[{key}]", key, f"{key} -", f"{key}-", f"{key}:"):
            if name.casefold().startswith(prefix.casefold()):
                name = name[len(prefix) :].strip()
                break
    name = _ZOHO_TASK_KEY_PREFIX.sub("", name).strip()
    return name or "Untitled task"


def normalize_tasklist_name(raw_name: str) -> str:
    return html.unescape((raw_name or "General").strip()) or "General"


@dataclass
class TaskRow:
    owner_name: str
    task_name: str
    deadline: str
    status: str
    project_name: str
    tasklist_name: str = ""


class ZohoProjectsClient:
    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self.settings = settings
        self._client = client or httpx.Client(timeout=60.0)
        self._owns_client = client is None
        self._access_token: str | None = None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "ZohoProjectsClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def refresh_access_token(self) -> str:
        response = self._client.post(
            f"{self.settings.zoho_accounts_domain}/oauth/v2/token",
            data={
                "refresh_token": self.settings.zoho_refresh_token,
                "client_id": self.settings.zoho_client_id,
                "client_secret": self.settings.zoho_client_secret,
                "grant_type": "refresh_token",
            },
        )
        response.raise_for_status()
        payload = response.json()
        token = payload.get("access_token")
        if not token:
            raise RuntimeError("Failed to refresh Zoho access token")
        self._access_token = token
        return token

    def _headers(self) -> dict[str, str]:
        if not self._access_token:
            self.refresh_access_token()
        assert self._access_token is not None
        return {
            "Authorization": f"Zoho-oauthtoken {self._access_token}",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        }

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.settings.zoho_projects_domain}{path}"
        response = self._client.get(url, headers=self._headers(), params=params)
        if response.status_code == 401:
            self.refresh_access_token()
            response = self._client.get(url, headers=self._headers(), params=params)
        if response.status_code == 429:
            raise RuntimeError("Zoho API rate limit hit (HTTP 429). Retry later.")
        response.raise_for_status()
        if not response.content:
            return {}
        return response.json()

    def get_portal_id(self) -> str:
        if self.settings.zoho_portal_id:
            return self.settings.zoho_portal_id

        payload = self._get("/restapi/portals/")
        portals = payload.get("portals") or []
        if not portals:
            raise RuntimeError("No Zoho Projects portals found for this account.")

        default = next((p for p in portals if p.get("default")), None)
        portal = default or portals[0]
        portal_id = str(portal.get("id_string") or portal.get("id"))
        if not portal_id:
            raise RuntimeError("Unable to resolve Zoho portal id")
        return portal_id

    def list_project_ids(self, portal_id: str) -> list[str]:
        project_ids: list[str] = []
        index = 1
        page_size = 100

        while True:
            payload = self._get(
                f"/restapi/portal/{portal_id}/projects/",
                params={"index": index, "range": page_size, "status": "active"},
            )
            projects = payload.get("projects") or []
            if not projects:
                break

            for project in projects:
                project_ids.append(str(project.get("id_string") or project["id"]))

            if len(projects) < page_size:
                break
            index += page_size

        return project_ids

    def list_tasks_for_project(
        self,
        portal_id: str,
        project_id: str,
    ) -> list[dict[str, Any]]:
        """Fetch all tasks (open + closed) so counts stay accurate on every run."""
        tasks: list[dict[str, Any]] = []
        index = 1
        page_size = 100

        while True:
            payload = self._get(
                f"/restapi/portal/{portal_id}/projects/{project_id}/tasks/",
                params={
                    "index": index,
                    "range": page_size,
                    "owner": "all",
                    "status": "all",
                    "all_tasks": "true",
                    "sort_column": "last_modified_time",
                    "sort_order": "descending",
                },
            )
            batch = payload.get("tasks") or []
            if not batch:
                break

            tasks.extend(batch)
            if len(batch) < page_size:
                break
            index += page_size

        return tasks

    def fetch_all_task_rows(self, today: date | None = None) -> list[TaskRow]:
        if today is None:
            today = datetime.now(ZoneInfo(self.settings.timezone_name)).date()

        # New access token on every trigger — no stale OAuth session.
        self._access_token = None
        self.refresh_access_token()

        portal_id = self.get_portal_id()
        project_ids = self.list_project_ids(portal_id)

        rows: list[TaskRow] = []
        for project_id in project_ids:
            for task in self.list_tasks_for_project(portal_id, project_id):
                rows.extend(self._task_to_rows(task, today))

        rows.sort(
            key=lambda row: (
                row.owner_name.lower(),
                row.tasklist_name.lower(),
                row.deadline,
                row.task_name.lower(),
            )
        )
        return rows

    def _task_to_rows(self, task: dict[str, Any], today: date) -> list[TaskRow]:
        task_key = str(task.get("key") or "").strip()
        raw_name = str(task.get("name") or "").strip()
        if task_key and raw_name == task_key:
            return []

        owners = ((task.get("details") or {}).get("owners")) or [{"name": "Unassigned"}]
        deadline = self._format_deadline(task)
        status = self._classify_status(task, today)
        project_name = html.unescape(((task.get("project") or {}).get("name")) or "")
        tasklist_name = normalize_tasklist_name(((task.get("tasklist") or {}).get("name")) or "")
        task_name = normalize_task_name(raw_name, task_key=task_key or None)
        rows: list[TaskRow] = []
        for owner in owners:
            owner_name = str(owner.get("name") or "Unassigned").strip() or "Unassigned"
            if owner_name.lower() == "unassigned" and len(owners) > 1:
                continue
            rows.append(
                TaskRow(
                    owner_name=owner_name,
                    task_name=task_name,
                    deadline=deadline or "—",
                    status=status,
                    project_name=project_name,
                    tasklist_name=tasklist_name,
                )
            )
        return rows or [
            TaskRow(
                owner_name="Unassigned",
                task_name=task_name,
                deadline=deadline or "—",
                status=status,
                project_name=project_name,
                tasklist_name=tasklist_name,
            )
        ]

    def _format_deadline(self, task: dict[str, Any]) -> str:
        end_long = task.get("end_date_long")
        if end_long:
            try:
                return datetime.fromtimestamp(int(end_long) / 1000).date().isoformat()
            except (TypeError, ValueError, OSError):
                pass

        value = str(task.get("end_date") or task.get("end_date_format") or "").strip()
        parsed = self._parse_deadline_date(value)
        return parsed.isoformat() if parsed else (value.split(" ")[0] if value else "")

    # Portal statuses from Zoho Projects (open board); closed → Completed.
    _STATUS_ALIASES = {
        "open": "Open",
        "in progress": "In Progress",
        "inprogress": "In Progress",
        "in review": "In Review",
        "inreview": "In Review",
        "on hold": "On Hold",
        "onhold": "On Hold",
        "delayed": "Delayed",
        "completed": "Completed",
        "closed": "Completed",
        "done": "Completed",
        "complete": "Completed",
    }

    # Keep these Zoho board labels even when the due date has passed.
    _PRESERVE_WHEN_OVERDUE = frozenset(
        {"In Progress", "In Review", "On Hold", "Delayed"}
    )

    def _classify_status(self, task: dict[str, Any], today: date) -> str:
        completed = bool(task.get("completed"))
        status_raw = task.get("status")
        if isinstance(status_raw, str):
            status_obj: dict[str, Any] = {"name": status_raw}
        else:
            status_obj = status_raw or {}
        status_type = str(status_obj.get("type") or "").lower()
        raw_name = str(
            status_obj.get("name")
            or status_obj.get("status_name")
            or task.get("status_name")
            or ""
        ).strip()
        status_name = " ".join(raw_name.lower().split())
        is_closed_type = bool(status_obj.get("is_closed_type"))

        try:
            percent = float(task.get("percent_complete") or 0)
        except (TypeError, ValueError):
            percent = 0.0

        if (
            completed
            or is_closed_type
            or percent >= 100
            or status_type in {"closed", "completed"}
            or status_name in {"closed", "completed", "done", "complete"}
        ):
            return "Completed"

        zoho_label = (
            self._STATUS_ALIASES.get(status_name, raw_name) if status_name else "Open"
        )

        # Past due + still Open → Delayed (Zoho board status). Keep In Progress / etc.
        deadline = self._deadline_date_from_task(task)
        if (
            deadline
            and deadline < today
            and zoho_label not in self._PRESERVE_WHEN_OVERDUE
        ):
            return "Delayed"

        return zoho_label

    def _deadline_date_from_task(self, task: dict[str, Any]) -> date | None:
        end_long = task.get("end_date_long")
        if end_long:
            try:
                return datetime.fromtimestamp(int(end_long) / 1000).date()
            except (TypeError, ValueError, OSError):
                pass
        return self._parse_deadline_date(
            str(task.get("end_date") or task.get("end_date_format") or "")
        )

    def _parse_deadline_date(self, value: str) -> date | None:
        value = (value or "").strip()
        if not value:
            return None
        date_part = value.split(" ")[0]

        if self.settings.deadline_date_order == "MDY":
            formats = ("%m-%d-%Y", "%m/%d/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y")
        else:
            formats = ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%m-%d-%Y", "%m/%d/%Y")

        for fmt in formats:
            try:
                return datetime.strptime(date_part, fmt).date()
            except ValueError:
                continue
        return None
