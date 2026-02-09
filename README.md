# Naija Tax Guide Scheduler

Runs background maintenance jobs for Naija Tax Guide using Supabase Service Role.

## What it does
- Applies scheduled plan changes (pending_plan_code)
- Deactivates expired subscriptions (expires_at + grace_days)
- Cleans up old daily_question_usage rows

## Setup (GitHub Actions)
Add these repo secrets:
- SUPABASE_URL
- SUPABASE_SERVICE_ROLE_KEY

The workflow runs every 30 minutes and can be triggered manually.
