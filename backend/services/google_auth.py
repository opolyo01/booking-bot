from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlencode

import httpx
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import get_settings
from backend.db.models import OAuthToken

settings = get_settings()

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "openid",
    "email",
]
_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_URL = "https://oauth2.googleapis.com/token"


def build_authorization_url(state: str) -> str:
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return f"{_AUTH_URL}?{urlencode(params)}"


async def exchange_code_for_tokens(code: str) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            _TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": settings.google_redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        resp.raise_for_status()
        return resp.json()


async def save_tokens(db: AsyncSession, token_data: dict) -> None:
    result = await db.execute(
        select(OAuthToken).where(OAuthToken.provider == "google")
    )
    record = result.scalars().first()

    expiry = None
    if "expires_in" in token_data:
        from datetime import timedelta
        expiry = datetime.now(timezone.utc) + timedelta(seconds=token_data["expires_in"])

    if record:
        record.access_token = token_data["access_token"]
        if "refresh_token" in token_data:
            record.refresh_token = token_data["refresh_token"]
        record.token_expiry = expiry
    else:
        db.add(
            OAuthToken(
                provider="google",
                access_token=token_data["access_token"],
                refresh_token=token_data.get("refresh_token", ""),
                token_expiry=expiry,
            )
        )
    await db.commit()


async def get_credentials(db: AsyncSession) -> Optional[Credentials]:
    result = await db.execute(
        select(OAuthToken).where(OAuthToken.provider == "google")
    )
    record = result.scalars().first()
    if not record:
        return None

    creds = Credentials(
        token=record.access_token,
        refresh_token=record.refresh_token,
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        token_uri=_TOKEN_URL,
        scopes=SCOPES,
    )

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        await save_tokens(db, {"access_token": creds.token, "expires_in": 3600})

    return creds
