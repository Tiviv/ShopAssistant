from datetime import date as date_
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.models import CashClosing, User
from app.realtime import manager
from app.schemas import CashClosingIn, CashClosingOut, CloseForgottenDaysResponse

router = APIRouter(prefix="/cash_closings", tags=["cash"])

# The shop's own calendar day decides whether a day is over — mirrors
# public.shop_today() in supabase/schema.sql. Change this if the shop isn't
# in Bulgaria.
SHOP_TIMEZONE = ZoneInfo("Europe/Sofia")

# Mirrors close_finished_days() in supabase/schema.sql as closely as
# possible: sum each day's invoice/credit totals and cash-register entries
# by payment method, for every day before "today" that has no closing yet,
# and insert one closing row per day. Written as one raw statement (rather
# than fetched-and-summed-in-Python) so the money math is exactly Postgres's
# own aggregate arithmetic, not a second implementation that could drift
# from it.
_CLOSE_FORGOTTEN_DAYS_SQL = text("""
    WITH activity AS (
        SELECT d.date, d.payment_method, d.total AS amount,
               CASE WHEN d.doc_type = 'invoice' THEN 1 ELSE 0 END AS invoices, 0 AS entries
          FROM documents d
          WHERE d.owner_id = :owner_id AND d.doc_type IN ('invoice', 'credit')
        UNION ALL
        SELECT e.date, e.payment_method, e.amount, 0, 1
          FROM cash_entries e
          WHERE e.owner_id = :owner_id
    ), sums AS (
        SELECT a.date,
               COALESCE(SUM(a.amount) FILTER (WHERE a.payment_method = 'cash'), 0) AS total_cash,
               COALESCE(SUM(a.amount) FILTER (WHERE a.payment_method = 'card'), 0) AS total_card,
               COALESCE(SUM(a.amount) FILTER (WHERE a.payment_method = 'bank'), 0) AS total_bank,
               COALESCE(SUM(a.amount), 0) AS total,
               SUM(a.invoices) AS invoice_count,
               SUM(a.entries) AS entry_count
          FROM activity a
          WHERE a.date < :today
          GROUP BY a.date
    )
    INSERT INTO cash_closings (owner_id, date, counted_cash, note, closed_at,
                                total_cash, total_card, total_bank, total,
                                invoice_count, entry_count, auto_closed)
    SELECT :owner_id, s.date, 0, '', now(),
           s.total_cash, s.total_card, s.total_bank, s.total, s.invoice_count, s.entry_count, true
      FROM sums s
    ON CONFLICT (owner_id, date) DO NOTHING
    RETURNING date
""")


@router.get("", response_model=list[CashClosingOut])
async def list_cash_closings(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[CashClosing]:
    result = await db.scalars(
        select(CashClosing).where(CashClosing.owner_id == current_user.id).order_by(CashClosing.date)
    )
    return list(result)


@router.post("/close-forgotten-days", response_model=CloseForgottenDaysResponse)
async def close_forgotten_days(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> CloseForgottenDaysResponse:
    # Only ever adds closings for days that are already over, so calling
    # this on every load (which the frontend does) is safe — an already
    # -closed day just gets skipped by ON CONFLICT DO NOTHING.
    shop_today = datetime.now(SHOP_TIMEZONE).date()
    result = await db.execute(
        _CLOSE_FORGOTTEN_DAYS_SQL, {"owner_id": str(current_user.id), "today": shop_today}
    )
    closed_dates = result.fetchall()
    await db.commit()
    if closed_dates:
        # This runs on every load (see the comment above), so only broadcast
        # when something actually changed — otherwise every device would
        # nudge every other device to refetch on every page open, for
        # nothing.
        await manager.broadcast(current_user.id, "cash_closings")
    return CloseForgottenDaysResponse(closed=len(closed_dates))


@router.put("/{closing_date}", response_model=CashClosingOut)
async def upsert_cash_closing(
    closing_date: date_,
    body: CashClosingIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CashClosing:
    closing = await db.get(CashClosing, {"owner_id": current_user.id, "date": closing_date})
    if closing is None:
        closing = CashClosing(owner_id=current_user.id, date=closing_date)
        db.add(closing)
    for field, value in body.model_dump().items():
        setattr(closing, field, value)
    await db.commit()
    await db.refresh(closing)
    await manager.broadcast(current_user.id, "cash_closings")
    return closing


@router.delete("/{closing_date}", status_code=204)
async def delete_cash_closing(
    closing_date: date_,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    closing = await db.get(CashClosing, {"owner_id": current_user.id, "date": closing_date})
    if closing is not None:
        await db.delete(closing)
        await db.commit()
        await manager.broadcast(current_user.id, "cash_closings")
