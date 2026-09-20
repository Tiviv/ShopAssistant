import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.models import CashEntry, User
from app.realtime import manager
from app.schemas import CashEntryIn, CashEntryOut

router = APIRouter(prefix="/cash_entries", tags=["cash"])


@router.get("", response_model=list[CashEntryOut])
async def list_cash_entries(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[CashEntry]:
    result = await db.scalars(
        select(CashEntry).where(CashEntry.owner_id == current_user.id).order_by(CashEntry.created_at)
    )
    return list(result)


@router.post("", response_model=CashEntryOut, status_code=status.HTTP_201_CREATED)
async def create_cash_entry(
    body: CashEntryIn, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> CashEntry:
    entry = CashEntry(owner_id=current_user.id, **body.model_dump())
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    await manager.broadcast(current_user.id, "cash_entries")
    return entry


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_cash_entry(
    entry_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    entry = await db.scalar(
        select(CashEntry).where(CashEntry.id == entry_id, CashEntry.owner_id == current_user.id)
    )
    if entry is None:
        # 404 rather than 403 — same reasoning as products/customers/documents.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cash entry not found")
    await db.delete(entry)
    await db.commit()
    await manager.broadcast(current_user.id, "cash_entries")
