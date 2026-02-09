# app/scheduler/run_once.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from ..core.supabase_client import supabase
from ..services.subscriptions_service import apply_scheduled_change_if_due


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def expire_ai_credits_best_effort() -> Dict[str, Any]:
    """
    Calls your SQL function expire_ai_credits() if it exists.
    """
    try:
        res = supabase().rpc("expire_ai_credits", {}).execute()
        return {"ok": True, "result": res.data}
    except Exception as e:
        return {"ok": False, "error": f"expire_ai_credits failed: {e}"}


def apply_due_plan_changes_best_effort() -> Dict[str, Any]:
    """
    Finds all active subs that have pending plan changes due, then applies them.
    """
    db = supabase()
    now = _now_utc().isoformat()

    try:
        rows = (
            db.table("user_subscriptions")
            .select("account_id,pending_plan_code,pending_starts_at,is_active")
            .eq("is_active", True)
            .not_.is_("pending_plan_code", "null")
            .not_.is_("pending_starts_at", "null")
            .lte("pending_starts_at", now)
            .limit(5000)
            .execute()
        )
        data: List[Dict[str, Any]] = rows.data or []
    except Exception as e:
        return {"ok": False, "error": f"query pending subs failed: {e}"}

    changed = 0
    errors = 0
    for r in data:
        aid = (r.get("account_id") or "").strip()
        if not aid:
            continue
        try:
            out = apply_scheduled_change_if_due(aid)
            if out:
                changed += 1
        except Exception:
            errors += 1

    return {"ok": True, "checked": len(data), "changed": changed, "errors": errors}


def run_once() -> Dict[str, Any]:
    """
    One scheduler tick.
    """
    out1 = expire_ai_credits_best_effort()
    out2 = apply_due_plan_changes_best_effort()
    return {"ok": True, "expire_ai_credits": out1, "apply_due_plan_changes": out2}
