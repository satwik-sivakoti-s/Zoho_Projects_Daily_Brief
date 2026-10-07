"""Shared configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    zoho_accounts_domain: str
    zoho_projects_domain: str
    zoho_client_id: str
    zoho_client_secret: str
    zoho_refresh_token: str
    zoho_portal_id: str | None
    flock_webhook_url: str
    cron_secret: str | None
    show_completed_in_list: bool
    timezone_name: str
    deadline_date_order: str
    skip_weekends: bool
    hide_if_deadline_days_ahead: int

    @classmethod
    def from_env(cls) -> "Settings":
        missing = [
            key
            for key in (
                "ZOHO_CLIENT_ID",
                "ZOHO_CLIENT_SECRET",
                "ZOHO_REFRESH_TOKEN",
                "FLOCK_WEBHOOK_URL",
            )
            if not os.getenv(key)
        ]
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

        date_order = os.getenv("DEADLINE_DATE_ORDER", "DMY").upper()
        if date_order not in {"DMY", "MDY"}:
            date_order = "DMY"

        return cls(
            zoho_accounts_domain=os.getenv(
                "ZOHO_ACCOUNTS_DOMAIN", "https://accounts.zoho.in"
            ).rstrip("/"),
            zoho_projects_domain=os.getenv(
                "ZOHO_PROJECTS_DOMAIN", "https://projectsapi.zoho.in"
            ).rstrip("/"),
            zoho_client_id=os.environ["ZOHO_CLIENT_ID"],
            zoho_client_secret=os.environ["ZOHO_CLIENT_SECRET"],
            zoho_refresh_token=os.environ["ZOHO_REFRESH_TOKEN"],
            zoho_portal_id=os.getenv("ZOHO_PORTAL_ID") or None,
            flock_webhook_url=os.environ["FLOCK_WEBHOOK_URL"],
            cron_secret=os.getenv("ZOHO_PROJECTS_CRON_SECRET") or None,
            show_completed_in_list=os.getenv("SHOW_COMPLETED_IN_LIST", "true").lower()
            in {"1", "true", "yes"},
            timezone_name=os.getenv("BRIEF_TIMEZONE", "Asia/Kolkata"),
            deadline_date_order=date_order,
            skip_weekends=os.getenv("SKIP_WEEKENDS", "true").lower()
            in {"1", "true", "yes"},
            hide_if_deadline_days_ahead=int(
                os.getenv("HIDE_IF_DEADLINE_DAYS_AHEAD", "5")
            ),
        )
