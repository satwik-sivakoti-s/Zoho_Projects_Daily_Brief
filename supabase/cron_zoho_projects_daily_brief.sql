-- Zoho Projects Daily Brief → triggered from Supabase Cron (Internal Tools)
-- Schedule: Mon–Fri 10:30 AM IST  (= 05:00 UTC)
--
-- How to apply:
-- 1. Open Supabase project "Internal Tools"
-- 2. SQL Editor → New query → paste this file
-- 3. Replace the two placeholders below, then Run
--
-- Vault stores the Vercel URL + bearer secret (not Edge Function env vars).

create extension if not exists pg_net with schema extensions;
create extension if not exists pg_cron;

-- Replace these before running:
--   <VERCEL_APP_URL>  e.g. https://zoho-projects-daily-brief.vercel.app/api/daily-brief
--   <SAME_SECRET_AS_VERCEL>  must match ZOHO_PROJECTS_CRON_SECRET on Vercel

do $$
declare
  brief_url text := '<VERCEL_APP_URL>';
  cron_secret text := '<SAME_SECRET_AS_VERCEL>';
  existing uuid;
begin
  if brief_url like '%<%' or cron_secret like '%<%' then
    raise exception 'Replace <VERCEL_APP_URL> and <SAME_SECRET_AS_VERCEL> before running';
  end if;

  select id into existing from vault.secrets where name = 'zoho_projects_brief_url';
  if existing is null then
    perform vault.create_secret(brief_url, 'zoho_projects_brief_url', 'Vercel /api/daily-brief URL');
  else
    perform vault.update_secret(existing, brief_url);
  end if;

  select id into existing from vault.secrets where name = 'zoho_projects_cron_secret';
  if existing is null then
    perform vault.create_secret(
      cron_secret,
      'zoho_projects_cron_secret',
      'Bearer token matching ZOHO_PROJECTS_CRON_SECRET on Vercel'
    );
  else
    perform vault.update_secret(existing, cron_secret);
  end if;
end $$;

-- Idempotent: same job name overwrites any previous schedule
select cron.schedule(
  'zoho-projects-daily-brief',
  '0 5 * * 1-5', -- 05:00 UTC Mon–Fri = 10:30 IST weekdays
  $$
  select net.http_get(
    url := (
      select decrypted_secret
      from vault.decrypted_secrets
      where name = 'zoho_projects_brief_url'
    ),
    headers := jsonb_build_object(
      'Authorization',
      'Bearer ' || (
        select decrypted_secret
        from vault.decrypted_secrets
        where name = 'zoho_projects_cron_secret'
      )
    ),
    timeout_milliseconds := 120000
  ) as request_id;
  $$
);

-- Verify
select jobid, jobname, schedule, active
from cron.job
where jobname = 'zoho-projects-daily-brief';
