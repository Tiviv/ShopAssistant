from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.models import ShopSettings, User
from app.realtime import manager
from app.schemas import SettingsOut, SettingsUpdate

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=SettingsOut)
async def get_settings(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> ShopSettings:
    settings = await db.get(ShopSettings, current_user.id)
    if settings is None:
        # Shouldn't happen — signup always creates one — but a stray account
        # from before that trigger existed (or manual DB surgery) shouldn't
        # 500 forever; POST /settings below recovers it.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No settings row for current user")
    return settings


@router.post("", response_model=SettingsOut, status_code=status.HTTP_200_OK)
async def ensure_settings(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> ShopSettings:
    # Idempotent: creates the row only if missing, mirrors the frontend's
    # own insert-if-missing fallback in loadAllData().
    settings = await db.get(ShopSettings, current_user.id)
    if settings is None:
        settings = ShopSettings(owner_id=current_user.id)
        db.add(settings)
        await db.commit()
        await db.refresh(settings)
    return settings


@router.patch("", response_model=SettingsOut)
async def update_settings(
    body: SettingsUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ShopSettings:
    settings = await db.get(ShopSettings, current_user.id)
    if settings is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No settings row for current user")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(settings, field, value)
    await db.commit()
    await db.refresh(settings)
    await manager.broadcast(current_user.id, "settings")
    return settings
