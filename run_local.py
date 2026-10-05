"""Run the daily brief locally.

Usage:
  python run_local.py
  python run_local.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys

from services.runner import run_daily_brief


def main() -> int:
    parser = argparse.ArgumentParser(description="Zoho Projects → Flock daily brief")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and print the message without posting to Flock",
    )
    args = parser.parse_args()

    try:
        result = run_daily_brief(dry_run=args.dry_run)
    except Exception as exc:  # noqa: BLE001
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(result.get("preview") or "")
    print()
    print(json.dumps({k: v for k, v in result.items() if k != "flockml"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
