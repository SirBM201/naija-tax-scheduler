# scheduler/run_jobs.py
from __future__ import annotations

import os
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional, List

from supabase import create_client


# -----------------------------
# time helpers
# -----------------------------
def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(value: str) -> Optional[datetime]:
    try:
        v = value.replace("Z", "+00:00")
        return datetime.fromisoformat(v)
    except Exception:
        return None


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


# -----------------------------
# env + client
# -----------------------------
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()

if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
    raise RuntimeError("Missing SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY")

sb = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


# -----------------------------
# helpers
# -----------------------------
def _get_plan(plan_code: str) -> Optional[Dict[str, Any]]:
    if not plan_code:
        return None
    res = sb.table("plans").select("*").eq("plan_code", plan_code).limit(1).execute()
    return res.data[0] if res.data else None


def _build_expiry_from_plan(plan_code: str, starts_at: datetime) -> datetime:
    plan = _get_plan(plan_code)
    duration_days = 30
    if plan:
        try:
            duration_days = int(plan.get("duration_days") or 30)
        except Exception:
            duration_days = 30
    return starts_at + timedelta(days=duration_days)


def _deactivate_row(row_id: str, reason: str) -> None:
    try:
        sb.table("user_subscriptions").update(
            {"is_active": False, "status": reason, "updated_at": _iso(_now_utc())}
        ).eq("id", row_id).execute()
    except Exception:
        pass


def _activate_new_subscription(account_id: str, plan_code: str) -> None:
    """
    Creates a fresh active subscription row.
    NOTE: credit reset is handled by your API when plan activates (or later you can add it here as RPC).
    """
    try:
        sb.table("user_subscriptions").update(
            {"is_active": False, "status": "replaced", "updated_at": _iso(_now_utc())}
        ).eq("account_id", account_id).eq("is_active", True).execute()
    except Exception:
        pass

    starts = _now_utc()
    expires = _build_expiry_from_plan(plan_code, starts)

    payload = {
        "account_id": account_id,
        "plan_code": plan_code,
        "status": "active",
        "started_at": _iso(starts),
        "expires_at": _iso(expires),
        "is_active": True,
        "pending_plan_code": None,
        "pending_starts_at": None,
        "updated_at": _iso(_now_utc()),
    }

    try:
        sb.table("user_subscriptions").insert(payload).execute()
    except Exception:
        pass


def _fetch_active_rows_page(limit: int = 1000, offset: int = 0) -> List[Dict[str, Any]]:
    res = (
        sb.table("user_subscriptions")
        .select("id,account_id,plan_code,expires_at,is_active,pending_plan_code,pending_starts_at")
        .eq("is_active", True)
        .range(offset, offset + limit - 1)
        .execute()
    )
    return res.data or []


def apply_scheduled_upgrades() -> int:
    """
    If an active row has:
      pending_plan_code not null
      pending_starts_at <= now
    then activate new subscription row.
    """
    now = _now_utc()
    count = 0
    offset = 0
    page_size = 1000

    while True:
        rows = _fetch_active_rows_page(limit=page_size, offset=offset)
        if not rows:
            break

        for row in rows:
            pending_plan = (row.get("pending_plan_code") or "").strip()
            pending_starts_at = row.get("pending_starts_at")
            starts_dt = _parse_iso(pending_starts_at) if isinstance(pending_starts_at, str) else None

            if not pending_plan or not starts_dt:
                continue
            if now < starts_dt:
                continue

            # Clear pending on old row (best effort)
            try:
                sb.table("user_subscriptions").update(
                    {"pending_plan_code": None, "pending_starts_at": None, "updated_at": _iso(_now_utc())}
                ).eq("id", row["id"]).execute()
            except Exception:
                pass

            _activate_new_subscription(row["account_id"], pending_plan)
            count += 1

        offset += page_size

    return count


def deactivate_expired_subscriptions() -> int:
    """
    Deactivate any is_active=true row where:
      now > expires_at (+ grace_days from plan)
    """
    now = _now_utc()
    count = 0
    offset = 0
    page_size = 1000

    while True:
        rows = _fetch_active_rows_page(limit=page_size, offset=offset)
        if not rows:
            break

        for row in rows:
            exp = row.get("expires_at")
            exp_dt = _parse_iso(exp) if isinstance(exp, str) else None
            if not exp_dt:
                continue

            plan_code = (row.get("plan_code") or "").strip()
            plan = _get_plan(plan_code)
            grace_days = 0
            if plan and plan.get("grace_days") is not None:
                try:
                    grace_days = int(plan.get("grace_days") or 0)
                except Exception:
                    grace_days = 0

            grace_until = exp_dt + timedelta(days=grace_days)

            if now > grace_until:
                _deactivate_row(row["id"], reason="expired")
                count += 1

        offset += page_size

    return count


def main() -> None:
    upgraded = apply_scheduled_upgrades()
    expired = deactivate_expired_subscriptions()
    print(f"OK: scheduled_upgrades_applied={upgraded} expired_deactivated={expired}")


if __name__ == "__main__":
    main()
