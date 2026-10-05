"""Netlify background function: scheduled daily brief (long Zoho fetch)."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.config import Settings
from services.runner import run_daily_brief


def handler(event, context):
    del context, event

    try:
        settings = Settings.from_env()
    except ValueError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return {"statusCode": 500, "body": str(exc)}

    if settings.skip_weekends:
        weekday = datetime.now(ZoneInfo(settings.timezone_name)).weekday()
        if weekday >= 5:
            print(json.dumps({"ok": True, "skipped": True, "reason": "weekend"}))
            return {"statusCode": 200, "body": "skipped weekend"}

    try:
        result = run_daily_brief(settings, dry_run=False)
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(exc)}))
        return {"statusCode": 500, "body": str(exc)}

    summary = {
        "ok": True,
        "task_count": result["task_count"],
        "people_count": result["people_count"],
    }
    print(json.dumps(summary))
    return {"statusCode": 200, "body": json.dumps(summary)}
