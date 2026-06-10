from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from backend.core.config import get_settings

settings = get_settings()

ALGORITHM = "HS256"
CANCEL_TOKEN_EXPIRE_DAYS = 30
ADMIN_TOKEN_EXPIRE_HOURS = 24


def create_cancel_token(booking_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=CANCEL_TOKEN_EXPIRE_DAYS)
    return jwt.encode(
        {"sub": booking_id, "type": "cancel", "exp": expire},
        settings.secret_key,
        algorithm=ALGORITHM,
    )


def verify_cancel_token(token: str) -> str:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        if payload.get("type") != "cancel":
            raise HTTPException(status_code=400, detail="Invalid token type")
        booking_id: Optional[str] = payload.get("sub")
        if not booking_id:
            raise HTTPException(status_code=400, detail="Malformed token")
        return booking_id
    except JWTError:
        raise HTTPException(status_code=400, detail="Invalid or expired cancel token")


def create_admin_token(email: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=ADMIN_TOKEN_EXPIRE_HOURS)
    return jwt.encode(
        {"sub": email, "type": "admin", "exp": expire},
        settings.secret_key,
        algorithm=ALGORITHM,
    )


_bearer = HTTPBearer()


async def get_current_admin(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> str:
    try:
        payload = jwt.decode(
            credentials.credentials, settings.secret_key, algorithms=[ALGORITHM]
        )
        if payload.get("type") != "admin":
            raise ValueError("Wrong token type")
        email: Optional[str] = payload.get("sub")
        if not email:
            raise ValueError("Missing subject")
        return email
    except (JWTError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
