# Naija Tax Guide - Scheduler

This repo runs background maintenance jobs:
- Apply scheduled plan changes (pending_plan_code)
- Deactivate expired subscriptions (after grace)

## Env vars required
- SUPABASE_URL
- SUPABASE_SERVICE_ROLE_KEY

## Run locally
python -m scheduler.run_jobs

## Deploy later (Koyeb paid / other cron)
Run command:
python -m scheduler.run_jobs
