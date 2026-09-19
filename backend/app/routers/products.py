import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.models import Product, User
from app.schemas import ProductIn, ProductOut, RenameCategoryRequest

router = APIRouter(prefix="/products", tags=["products"])


async def _get_owned_product(product_id: uuid.UUID, user: User, db: AsyncSession) -> Product:
    product = await db.scalar(
        select(Product).where(Product.id == product_id, Product.owner_id == user.id)
    )
    if product is None:
        # 404 rather than 403 — a product id that exists but belongs to
        # someone else should look identical to one that doesn't exist.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
    return product


@router.get("", response_model=list[ProductOut])
async def list_products(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[Product]:
    result = await db.scalars(
        select(Product).where(Product.owner_id == current_user.id).order_by(Product.name)
    )
    return list(result)


@router.post("", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
async def create_product(
    body: ProductIn, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> Product:
    product = Product(owner_id=current_user.id, **body.model_dump())
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return product


@router.post("/rename-category", status_code=status.HTTP_204_NO_CONTENT)
async def rename_category(
    body: RenameCategoryRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    # Mirrors the frontend's renameCategory flow: every product filed under
    # the old name moves with it in one step, so the old name can't reappear
    # in the category list as still-in-use.
    await db.execute(
        update(Product)
        .where(Product.owner_id == current_user.id, Product.category == body.old_name)
        .values(category=body.new_name)
    )
    await db.commit()


@router.put("/{product_id}", response_model=ProductOut)
async def update_product(
    product_id: uuid.UUID,
    body: ProductIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Product:
    product = await _get_owned_product(product_id, current_user, db)
    for field, value in body.model_dump().items():
        setattr(product, field, value)
    await db.commit()
    await db.refresh(product)
    return product


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(
    product_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    product = await _get_owned_product(product_id, current_user, db)
    await db.delete(product)
    await db.commit()
