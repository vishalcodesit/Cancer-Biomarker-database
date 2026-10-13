"""Minimal write protection for a teaching deployment.

Read endpoints are public. Endpoints that change data (CSV import with dry_run=false, score recompute)
require the X-Admin-Token header when ADMIN_TOKEN is configured. With no token configured (local demo),
writes stay open, as in the original version. Comparison uses a constant-time function.
"""
import hmac

from fastapi import HTTPException, Request

from app.config import get_settings


def require_admin(request: Request) -> None:
    token = get_settings().admin_token
    if not token:
        return
    supplied = request.headers.get("X-Admin-Token", "")
    if not hmac.compare_digest(supplied.encode(), token.encode()):
        raise HTTPException(status_code=401, detail={
            "code": "unauthorized",
            "message": "This write operation requires a valid X-Admin-Token header.",
        })
