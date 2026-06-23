from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.security import get_current_admin
from backend.db.database import get_db
from backend.services.google_auth import get_credentials
from backend.services.gmail import mark_all_as_read

router = APIRouter(prefix="/gmail", tags=["gmail"])


@router.post("/mark-all-read")
async def mark_all_read(
    _email: str = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    creds = await get_credentials(db)
    if not creds:
        raise HTTPException(status_code=401, detail="Google account not connected")

    count = await mark_all_as_read(creds)
    return {"marked_read": count}
