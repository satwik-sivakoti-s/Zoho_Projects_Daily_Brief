"""Netlify Function: manual / test trigger for the daily brief (HTTP)."""

from __future__ import annotations

import json
import os
import secrets
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.config import Settings
from services.runner import run_daily_brief


def _authorized(headers: dict[str, str], cron_secret: str | None) -> bool:
    if not cron_secret:
        return False
    auth = headers.get("authorization") or headers.get("Authorization") or ""
    if not auth.startswith("Bearer "):
        return False
    token = auth.removeprefix("Bearer ").strip()
    return secrets.compare_digest(token, cron_secret)


def _response(status: int, payload: dict) -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(payload),
    }


def handler(event, context):
    del context
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    cron_secret = os.getenv("CRON_SECRET")

    path = (event.get("rawPath") or event.get("path") or "").lower()
    is_test = path.endswith("/test")
    qs = event.get("queryStringParameters") or {}
    dry_run = is_test or qs.get("dry_run", "false").lower() in {"1", "true", "yes"}

    if not _authorized(headers, cron_secret):
        return _response(401, {"detail": "Unauthorized"})

    try:
        settings = Settings.from_env()
    except ValueError as exc:
        return _response(500, {"detail": str(exc)})

    if settings.skip_weekends and not is_test:
        weekday = datetime.now(ZoneInfo(settings.timezone_name)).weekday()
        if weekday >= 5:
            return _response(200, {"ok": True, "skipped": True, "reason": "weekend"})

    try:
        result = run_daily_brief(settings, dry_run=dry_run)
    except Exception as exc:  # noqa: BLE001
        return _response(502, {"detail": str(exc)})

    payload = {
        "ok": True,
        "task_count": result["task_count"],
        "people_count": result["people_count"],
        "dry_run": result["dry_run"],
    }
    if is_test or qs.get("include_preview", "false").lower() in {"1", "true", "yes"}:
        payload["preview"] = result.get("preview")
        if dry_run:
            payload["flockml"] = result.get("flockml")
    if is_test:
        payload["mode"] = "test"

    return _response(200, payload)
