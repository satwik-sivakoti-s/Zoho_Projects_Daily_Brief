# Zoho Projects Daily Brief → Flock

Python automation that pulls tasks from **Zoho Projects**, groups them by assignee, and posts a daily summary to a **Flock** channel. Built to deploy on **Vercel** with a cron trigger.

## Message format

```
Zoho Projects Daily Brief — 05 Oct 2026
Total tasks: 12 | People: 4

Alice
Task · Deadline · Status
• Fix bug (App) · 2026-10-01 · Delayed
• Ship feature (App) · 2026-10-08 · On Track

Bob
Task · Deadline · Status
• Write brief (Ops) · 2026-10-06 · On Track
```

| Status | Rule |
|--------|------|
| **Completed** | Task marked completed / closed |
| **Delayed** | Not completed and deadline is before today (in `BRIEF_TIMEZONE`) |
| **On Track** | Not completed and deadline is today/future (or missing) |

## Layout

```
app.py                 # FastAPI entrypoint (Vercel)
run_local.py           # Local CLI runner
services/              # Zoho + Flock logic
vercel.json            # Cron + maxDuration
.python-version        # Python 3.12 on Vercel
requirements.txt
.env.example
```

## 1. Zoho setup

1. Open [Zoho API Console (IN)](https://api-console.zoho.in) (or your data center).
2. Create a **Server-based** or **Self Client** app.
3. Generate a refresh token with:
   ```
   ZohoProjects.portals.READ,ZohoProjects.projects.READ,ZohoProjects.tasks.READ
   ```
4. Put Client ID, Client Secret, and Refresh Token in `.env`.

> A Zoho **People** refresh token will **not** work. You need `ZohoProjects.*` scopes.

Optional: set `ZOHO_PORTAL_ID`. Otherwise the default portal is used.

India domains:

- Accounts: `https://accounts.zoho.in`
- Projects API: `https://projectsapi.zoho.in`

## 2. Flock setup

1. Flock → **Admin / Manage Team → Incoming Webhooks**.
2. Create a webhook for the target channel.
3. Paste the URL into `FLOCK_WEBHOOK_URL`.

## 3. Local run

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env   # fill values

python run_local.py --dry-run
python run_local.py
```

API locally:

```bash
# set CRON_SECRET in .env first
uvicorn app:app --reload
curl -H "Authorization: Bearer YOUR_CRON_SECRET" ^
  "http://127.0.0.1:8000/api/daily-brief?dry_run=true&include_preview=true"
```

## 4. Vercel deploy

This app is a **FastAPI** project. Vercel detects `app.py` + `fastapi` in `requirements.txt` and deploys it as one Python function.

### A. Import from GitHub

1. Go to [vercel.com/new](https://vercel.com/new) → import `Zoho_Projects_Daily_Brief`.
2. Framework preset: leave **Other** / auto (Python FastAPI from `app.py`).
3. Root directory: `.` (project root).
4. Do **not** override the build command unless needed.

### B. Environment variables (required)

In **Project → Settings → Environment Variables**, add for **Production** (and Preview if you want):

| Variable | Required |
|----------|----------|
| `ZOHO_CLIENT_ID` | yes |
| `ZOHO_CLIENT_SECRET` | yes |
| `ZOHO_REFRESH_TOKEN` | yes |
| `FLOCK_WEBHOOK_URL` | yes |
| `CRON_SECRET` | yes (same value as in `.env`) |

Optional (defaults already match India setup):

- `ZOHO_ACCOUNTS_DOMAIN=https://accounts.zoho.in`
- `ZOHO_PROJECTS_DOMAIN=https://projectsapi.zoho.in`
- `BRIEF_TIMEZONE=Asia/Kolkata`
- `SKIP_WEEKENDS=true`
- `SHOW_COMPLETED_IN_LIST=false`
- `DEADLINE_DATE_ORDER=DMY`

> When `CRON_SECRET` is set, **Vercel Cron** automatically sends  
> `Authorization: Bearer <CRON_SECRET>` on scheduled invocations.

### C. Deploy

After pushing to `main`, Vercel deploys automatically. Or CLI:

```bash
npm i -g vercel
vercel login
vercel link
vercel env pull   # optional
vercel --prod
```

### D. Cron schedule

`vercel.json` runs daily at **03:00 UTC** (~08:30 IST):

```json
"crons": [{ "path": "/api/daily-brief", "schedule": "0 3 * * *" }]
```

Weekends are skipped in code when `SKIP_WEEKENDS=true` (works on Hobby’s once-per-day cron limit).

`maxDuration` is **60 seconds** (needs a plan that allows it; Hobby Fluid often supports this — if the job times out, upgrade or reduce projects).

### E. Test after deploy

```bash
# Health
curl https://YOUR_PROJECT.vercel.app/

# Dry-run (no Flock post) + preview
curl -H "Authorization: Bearer YOUR_CRON_SECRET" ^
  "https://YOUR_PROJECT.vercel.app/api/daily-brief?dry_run=true&include_preview=true"

# Real post to Flock
curl -H "Authorization: Bearer YOUR_CRON_SECRET" ^
  https://YOUR_PROJECT.vercel.app/api/daily-brief
```

Check **Deployments → Functions / Logs** if something fails.

### Local with Vercel

```bash
vercel dev
```

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ZOHO_CLIENT_ID` | yes | OAuth client ID |
| `ZOHO_CLIENT_SECRET` | yes | OAuth client secret |
| `ZOHO_REFRESH_TOKEN` | yes | Refresh token with Projects scopes |
| `FLOCK_WEBHOOK_URL` | yes | Incoming webhook URL |
| `CRON_SECRET` | yes (prod) | Bearer token for manual `/api/daily-brief` calls |
| `ZOHO_ACCOUNTS_DOMAIN` | no | Default `https://accounts.zoho.in` |
| `ZOHO_PROJECTS_DOMAIN` | no | Default `https://projectsapi.zoho.in` |
| `ZOHO_PORTAL_ID` | no | Auto-detected if empty |
| `SHOW_COMPLETED_IN_LIST` | no | Default `false` (counts still include completed) |
| `DEADLINE_DATE_ORDER` | no | `DMY` (India) or `MDY` |
| `BRIEF_TIMEZONE` | no | Default `Asia/Kolkata` |
| `SKIP_WEEKENDS` | no | Default `true` |

## Notes

- Each run refreshes the OAuth token and calls Zoho with `status=all` so completed counts stay accurate.
- By default, completed tasks appear in the summary only (`SHOW_COMPLETED_IN_LIST=false`); open/delayed tasks are listed under each task list.
- Multi-owner tasks appear under each owner.
- Prefer epoch deadline (`end_date_long`) from Zoho when available for accurate Delayed/On Track.
