# Zoho Projects Daily Brief → Flock

Python automation that pulls tasks from **Zoho Projects**, groups them by assignee, and posts a daily summary to a **Flock** channel. Hosted on **Vercel**; scheduled via **Supabase Cron** (project *Internal Tools*).

## Message format

```
Zoho Projects Daily Brief — 05 Oct 2026
Total tasks: 12 | People: 4

Alice
Task · Deadline · Status
• Fix bug · due 01 Oct · Delayed
• Ship feature · due 08 Oct · In Progress

Bob
Task · Deadline · Status
• Write brief · due 06 Oct · Open
```

Statuses come from **Zoho Projects** as-is (e.g. Open, In Progress, In Review, On Hold, Delayed). Closed tasks are shown as **Completed**.

Tasks whose deadline is **5 or more days away** are omitted from the brief (configurable via `HIDE_IF_DEADLINE_DAYS_AHEAD`; set `0` to show everything). Zoho **Delayed** tasks and tasks with no deadline always appear.

## Layout

```
app.py                 # FastAPI entrypoint (Vercel)
run_local.py           # Local CLI runner
services/              # Zoho + Flock logic
vercel.json            # maxDuration (no Vercel cron)
supabase/              # SQL to create Supabase Cron job
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
# set ZOHO_PROJECTS_CRON_SECRET in .env first
uvicorn app:app --reload
curl -H "Authorization: Bearer YOUR_ZOHO_PROJECTS_CRON_SECRET" ^
  "http://127.0.0.1:8000/api/daily-brief?dry_run=true&include_preview=true"
```

## 4. Vercel deploy

This app is a **FastAPI** project. Vercel detects `app.py` + `fastapi` in `requirements.txt` and deploys it as one Python function. Scheduling is **not** done on Vercel — use Supabase Cron (section 5).

### A. Import from GitHub

1. Go to [vercel.com/new](https://vercel.com/new) → import `Zoho_Projects_Daily_Brief`.
2. Framework preset: leave **Other** / auto (Python FastAPI from `app.py`).
3. Root directory: `.` (project root).
4. Do **not** override the build command unless needed.

### B. Environment variables (required on Vercel)

In **Project → Settings → Environment Variables**, add for **Production** (and Preview if you want):

| Variable | Required |
|----------|----------|
| `ZOHO_CLIENT_ID` | yes |
| `ZOHO_CLIENT_SECRET` | yes |
| `ZOHO_REFRESH_TOKEN` | yes |
| `FLOCK_WEBHOOK_URL` | yes |
| `ZOHO_PROJECTS_CRON_SECRET` | yes (same value as in `.env` / Supabase Vault) |

Optional (defaults already match India setup):

- `ZOHO_ACCOUNTS_DOMAIN=https://accounts.zoho.in`
- `ZOHO_PROJECTS_DOMAIN=https://projectsapi.zoho.in`
- `BRIEF_TIMEZONE=Asia/Kolkata`
- `SKIP_WEEKENDS=true`
- `SHOW_COMPLETED_IN_LIST=false`
- `DEADLINE_DATE_ORDER=DMY`
- `HIDE_IF_DEADLINE_DAYS_AHEAD=5`

### C. Deploy

After pushing to `main`, Vercel deploys automatically. Or CLI:

```bash
npm i -g vercel
vercel login
vercel link
vercel env pull   # optional
vercel --prod
```

### D. Test after deploy

```bash
# Health
curl https://YOUR_PROJECT.vercel.app/

# Dry-run (no Flock post) + preview
curl -H "Authorization: Bearer YOUR_ZOHO_PROJECTS_CRON_SECRET" ^
  "https://YOUR_PROJECT.vercel.app/api/daily-brief?dry_run=true&include_preview=true"

# Real post to Flock
curl -H "Authorization: Bearer YOUR_ZOHO_PROJECTS_CRON_SECRET" ^
  https://YOUR_PROJECT.vercel.app/api/daily-brief
```

Check **Deployments → Functions / Logs** if something fails.

## 5. Supabase Cron (Internal Automations)

Schedule: **Mon–Fri 10:30 AM IST** (`0 5 * * 1-5` UTC). Saturdays and Sundays are not scheduled.

1. Open the Supabase project **Internal Tools**.
2. SQL Editor → run [`supabase/cron_zoho_projects_daily_brief.sql`](supabase/cron_zoho_projects_daily_brief.sql) after replacing:
   - `<VERCEL_APP_URL>` → your live `https://….vercel.app/api/daily-brief`
   - `<SAME_SECRET_AS_VERCEL>` → same string as `ZOHO_PROJECTS_CRON_SECRET` on Vercel
3. Confirm under **Integrations → Cron** that job `zoho-projects-daily-brief` is active.
4. Optional smoke test: run the `net.http_get(…)` snippet from that file once manually, then check `net._http_response` and Vercel function logs.

Secrets for the cron live in **Supabase Vault** (`zoho_projects_brief_url`, `zoho_projects_cron_secret`) — not as Edge Function env vars.

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ZOHO_CLIENT_ID` | yes | OAuth client ID |
| `ZOHO_CLIENT_SECRET` | yes | OAuth client secret |
| `ZOHO_REFRESH_TOKEN` | yes | Refresh token with Projects scopes |
| `FLOCK_WEBHOOK_URL` | yes | Incoming webhook URL |
| `ZOHO_PROJECTS_CRON_SECRET` | yes (prod) | Bearer token for `/api/daily-brief` (Supabase Cron + manual curls) |
| `ZOHO_ACCOUNTS_DOMAIN` | no | Default `https://accounts.zoho.in` |
| `ZOHO_PROJECTS_DOMAIN` | no | Default `https://projectsapi.zoho.in` |
| `ZOHO_PORTAL_ID` | no | Auto-detected if empty |
| `SHOW_COMPLETED_IN_LIST` | no | Default `false` (counts still include completed) |
| `DEADLINE_DATE_ORDER` | no | `DMY` (India) or `MDY` |
| `BRIEF_TIMEZONE` | no | Default `Asia/Kolkata` |
| `SKIP_WEEKENDS` | no | Default `true` (extra weekend guard) |
| `HIDE_IF_DEADLINE_DAYS_AHEAD` | no | Default `5` |

## Notes

- Each run refreshes the OAuth token and calls Zoho with `status=all` so completed counts stay accurate.
- By default, completed tasks appear in the summary only (`SHOW_COMPLETED_IN_LIST=false`); open/delayed tasks are listed under each task list.
- Multi-owner tasks appear under each owner.
- Prefer epoch deadline (`end_date_long`) from Zoho when available for due-date filtering.
