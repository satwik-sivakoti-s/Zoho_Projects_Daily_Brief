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
services/
  config.py
  zoho.py
  brief.py
  runner.py
vercel.json            # Daily cron 03:00 UTC ≈ 08:30 IST
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

## 4. Netlify deploy (recommended for your setup)

This repo includes `netlify.toml`, a static `public/` site, and two functions:

| Function | Purpose |
|----------|---------|
| `daily-brief-background` | **Scheduled** weekday run (~08:30 IST, `0 3 * * 1-5` UTC) — use for production |
| `daily-brief` | **HTTP** manual trigger at `/api/daily-brief` and `/api/daily-brief/test` |

Zoho can take 20–60+ seconds; the **background** function avoids Netlify’s short HTTP timeout.

### One-time setup

1. Install the Netlify CLI (optional but useful):

```bash
npm install -g netlify-cli
netlify login
```

2. In [Netlify](https://app.netlify.com): **Add new site → Import an existing project** → connect `satwik-sivakoti-s/Zoho_Projects_Daily_Brief`.

3. Build settings (usually auto-detected from `netlify.toml`):

   - **Build command:** `pip install -r requirements.txt`
   - **Publish directory:** `public`
   - **Functions directory:** `netlify/functions`

4. **Site configuration → Environment variables** — add every variable from `.env.example` (scope: **Functions** + **Build**). Required: Zoho OAuth vars, `FLOCK_WEBHOOK_URL`, `CRON_SECRET`.

5. Deploy:

```bash
git push origin main
```

Or from your machine:

```bash
netlify init          # link local folder to the Netlify site (first time)
netlify deploy --prod
```

### After deploy

**Scheduled brief** (automatic): runs via `daily-brief-background` on the cron in `netlify.toml`. Check **Functions → daily-brief-background → Logs**.

**Manual / test** (with auth):

```bash
curl -H "Authorization: Bearer YOUR_CRON_SECRET" \
  https://YOUR-SITE.netlify.app/api/daily-brief

curl -H "Authorization: Bearer YOUR_CRON_SECRET" \
  "https://YOUR-SITE.netlify.app/api/daily-brief/test?include_preview=true"
```

Direct function URL (same auth):

```bash
curl -H "Authorization: Bearer YOUR_CRON_SECRET" \
  https://YOUR-SITE.netlify.app/.netlify/functions/daily-brief
```

**Local Netlify dev:**

```bash
netlify dev
# then call http://localhost:8888/api/daily-brief with Bearer header
```

> **Note:** Scheduled functions on Netlify require a plan that supports **Scheduled Functions** (included on free tier with limits). Background functions require a **credit-based** Netlify plan for long runs.

---

## 5. Vercel deploy (alternative)

1. Push the repo and import it in Vercel.
2. Framework: auto-detect Python (`app.py` + FastAPI).
3. Add all vars from `.env.example` under **Settings → Environment Variables**.
4. **`CRON_SECRET` is required** — use a random 16+ character string. Vercel Cron sends it as `Authorization: Bearer <CRON_SECRET>`.
5. Deploy.

`vercel.json` schedule: `0 3 * * *` (daily ~08:30 IST). Weekends are skipped in code when `SKIP_WEEKENDS=true` (Hobby-friendly).

Manual trigger:

```bash
curl -H "Authorization: Bearer YOUR_CRON_SECRET" \
  https://YOUR_PROJECT.vercel.app/api/daily-brief
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
