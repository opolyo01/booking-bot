import secrets

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import get_settings
from backend.core.security import create_admin_token, get_current_admin
from backend.db.database import get_db
from backend.services.google_auth import (
    build_authorization_url,
    exchange_code_for_tokens,
    save_tokens,
)

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()

# Simple in-memory CSRF store — fine for single-process personal tool
_pending_states: set[str] = set()


@router.get("/google")
async def google_login():
    state = secrets.token_urlsafe(32)
    _pending_states.add(state)
    url = build_authorization_url(state)
    return RedirectResponse(url)


@router.get("/google/callback")
async def google_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    if state not in _pending_states:
        raise HTTPException(status_code=400, detail="Invalid OAuth state")
    _pending_states.discard(state)

    token_data = await exchange_code_for_tokens(code)

    # Verify this is the owner's account via id_token or userinfo
    import httpx
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {token_data['access_token']}"},
        )
        resp.raise_for_status()
        user_info = resp.json()

    if user_info.get("email") != settings.google_owner_email:
        raise HTTPException(status_code=403, detail="Unauthorized Google account")

    await save_tokens(db, token_data)
    admin_jwt = create_admin_token(user_info["email"])

    return RedirectResponse(
        f"{settings.frontend_url}/admin?token={admin_jwt}"
    )


@router.get("/me")
async def get_me(email: str = Depends(get_current_admin)):
    return {"email": email}
