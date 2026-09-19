import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.models import Customer, User
from app.schemas import CustomerIn, CustomerOut

router = APIRouter(prefix="/customers", tags=["customers"])


async def _get_owned_customer(customer_id: uuid.UUID, user: User, db: AsyncSession) -> Customer:
    customer = await db.scalar(
        select(Customer).where(Customer.id == customer_id, Customer.owner_id == user.id)
    )
    if customer is None:
        # 404 rather than 403 — same reasoning as products: a customer id
        # that exists but belongs to someone else should look identical to
        # one that doesn't exist.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Customer not found")
    return customer


@router.get("", response_model=list[CustomerOut])
async def list_customers(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[Customer]:
    result = await db.scalars(
        select(Customer).where(Customer.owner_id == current_user.id).order_by(Customer.name)
    )
    return list(result)


@router.post("", response_model=CustomerOut, status_code=status.HTTP_201_CREATED)
async def create_customer(
    body: CustomerIn, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> Customer:
    customer = Customer(owner_id=current_user.id, **body.model_dump())
    db.add(customer)
    await db.commit()
    await db.refresh(customer)
    return customer


@router.put("/{customer_id}", response_model=CustomerOut)
async def update_customer(
    customer_id: uuid.UUID,
    body: CustomerIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Customer:
    customer = await _get_owned_customer(customer_id, current_user, db)
    for field, value in body.model_dump().items():
        setattr(customer, field, value)
    await db.commit()
    await db.refresh(customer)
    return customer


@router.delete("/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_customer(
    customer_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    customer = await _get_owned_customer(customer_id, current_user, db)
    await db.delete(customer)
    await db.commit()
