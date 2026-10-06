"""Vercel-compatible FastAPI entrypoint for the Zoho → Flock daily brief."""

from __future__ import annotations

import logging
import os
import secrets
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import JSONResponse

from services.config import Settings
from services.runner import run_daily_brief

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Zoho Projects Daily Brief",
    description="Fetches Zoho Projects tasks and posts a daily summary to Flock.",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


def _is_authorized(authorization: str | None, cron_secret: str | None) -> bool:
    """Expect Authorization: Bearer <ZOHO_PROJECTS_CRON_SECRET> from Supabase Cron."""
    if not cron_secret:
        return False
    if not authorization or not authorization.startswith("Bearer "):
        return False
    token = authorization.removeprefix("Bearer ").strip()
    return secrets.compare_digest(token, cron_secret)


@app.get("/")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "zoho-projects-daily-brief"}


@app.get("/api/daily-brief")
@app.post("/api/daily-brief")
def daily_brief(
    dry_run: bool = Query(False, description="Fetch and format without posting to Flock"),
    include_preview: bool = Query(
        False, description="Include message preview in the JSON response"
    ),
    authorization: str | None = Header(default=None),
) -> JSONResponse:
    cron_secret = os.getenv("ZOHO_PROJECTS_CRON_SECRET")
    if not _is_authorized(authorization, cron_secret):
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        settings = Settings.from_env()
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    # Extra guard if a schedule ever includes weekends
    if settings.skip_weekends:
        weekday = datetime.now(ZoneInfo(settings.timezone_name)).weekday()
        if weekday >= 5:
            return JSONResponse(
                {"ok": True, "skipped": True, "reason": "weekend"}
            )

    try:
        result = run_daily_brief(settings, dry_run=dry_run)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Daily brief failed")
        raise HTTPException(
            status_code=502, detail="Failed to generate daily brief"
        ) from exc

    payload = {
        "ok": True,
        "task_count": result["task_count"],
        "people_count": result["people_count"],
        "dry_run": result["dry_run"],
    }
    if include_preview:
        payload["preview"] = result.get("preview")
        if dry_run:
            payload["flockml"] = result.get("flockml")

    return JSONResponse(payload)


@app.get("/api/daily-brief/test")
@app.post("/api/daily-brief/test")
def daily_brief_test(
    authorization: str | None = Header(default=None),
) -> JSONResponse:
    """Fetch Zoho tasks and print the brief to the server terminal (no Flock post)."""
    cron_secret = os.getenv("ZOHO_PROJECTS_CRON_SECRET")
    # Local: open when ZOHO_PROJECTS_CRON_SECRET is unset. Production: require Bearer.
    if cron_secret and not _is_authorized(authorization, cron_secret):
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        settings = Settings.from_env()
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    try:
        result = run_daily_brief(settings, dry_run=True)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Daily brief test failed")
        raise HTTPException(
            status_code=502, detail="Failed to generate daily brief"
        ) from exc

    preview = result.get("preview") or "(no tasks)"
    separator = "=" * 60
    print(f"\n{separator}")
    print("ZOHO PROJECTS DAILY BRIEF — TEST")
    print(separator)
    print(preview)
    print(separator)
    print(
        f"tasks={result['task_count']} people={result['people_count']} "
        "(not sent to Flock)"
    )
    print(f"{separator}\n", flush=True)

    return JSONResponse(
        {
            "ok": True,
            "mode": "test",
            "printed_to_terminal": True,
            "task_count": result["task_count"],
            "people_count": result["people_count"],
        }
    )
