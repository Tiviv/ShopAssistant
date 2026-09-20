import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.models import Document, ShopSettings, User
from app.realtime import manager
from app.schemas import (
    DocumentCreate,
    DocumentOut,
    DocumentUpdate,
    LinkCustomerRequest,
    NextDocumentNumberRequest,
    NextDocumentNumberResponse,
    SetPaidRequest,
)

router = APIRouter(prefix="/documents", tags=["documents"])

# Column to bump for each document type — mirrors the three counters on
# `settings` (next_invoice_no / next_offer_no / next_credit_no).
_COUNTER_COLUMNS = {
    "invoice": ShopSettings.next_invoice_no,
    "offer": ShopSettings.next_offer_no,
    "credit": ShopSettings.next_credit_no,
}


async def _get_owned_document(document_id: uuid.UUID, user: User, db: AsyncSession) -> Document:
    document = await db.scalar(
        select(Document).where(Document.id == document_id, Document.owner_id == user.id)
    )
    if document is None:
        # 404 rather than 403 — same reasoning as products/customers.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    return document


@router.get("", response_model=list[DocumentOut])
async def list_documents(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[Document]:
    result = await db.scalars(
        select(Document).where(Document.owner_id == current_user.id).order_by(Document.created_at)
    )
    return list(result)


@router.post("/next-number", response_model=NextDocumentNumberResponse)
async def next_document_number(
    body: NextDocumentNumberRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NextDocumentNumberResponse:
    # Atomic, race-free numbering — the whole reason this rewrite exists in
    # the first place (see docs/python-backend-plan.md and the README's
    # history). A single UPDATE ... RETURNING takes a row lock on this
    # owner's settings row for the rest of the transaction, so two concurrent
    # requests are serialized by Postgres and always get two different,
    # consecutive numbers — same guarantee next_document_number() gave as a
    # Postgres function under Supabase.
    column = _COUNTER_COLUMNS[body.doc_type]
    stmt = (
        update(ShopSettings)
        .where(ShopSettings.owner_id == current_user.id)
        .values(**{column.key: column + 1})
        .returning(column)
    )
    result = await db.execute(stmt)
    row = result.first()
    if row is None:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "No settings row for current user")
    await db.commit()
    issued_number = row[0] - 1  # column now holds next_x_no *after* the increment
    return NextDocumentNumberResponse(number=issued_number)


@router.post("", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def create_document(
    body: DocumentCreate, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> Document:
    document = Document(owner_id=current_user.id, **body.model_dump())
    db.add(document)
    await db.commit()
    await db.refresh(document)
    await manager.broadcast(current_user.id, "documents")
    return document


@router.put("/{document_id}", response_model=DocumentOut)
async def update_document(
    document_id: uuid.UUID,
    body: DocumentUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Document:
    document = await _get_owned_document(document_id, current_user, db)
    for field, value in body.model_dump().items():
        setattr(document, field, value)
    await db.commit()
    await db.refresh(document)
    await manager.broadcast(current_user.id, "documents")
    return document


@router.patch("/{document_id}/paid", response_model=DocumentOut)
async def set_document_paid(
    document_id: uuid.UUID,
    body: SetPaidRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Document:
    document = await _get_owned_document(document_id, current_user, db)
    document.paid = body.paid
    await db.commit()
    await db.refresh(document)
    await manager.broadcast(current_user.id, "documents")
    return document


@router.patch("/{document_id}/customer", status_code=status.HTTP_204_NO_CONTENT)
async def link_document_customer(
    document_id: uuid.UUID,
    body: LinkCustomerRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    # Fire-and-forget, mirrors the frontend's linkDocumentCustomer: called
    # once an offer's one-off buyer gets saved as a real customer record, to
    # link the two — no updated row needed back.
    document = await _get_owned_document(document_id, current_user, db)
    document.customer_id = body.customer_id
    await db.commit()
    await manager.broadcast(current_user.id, "documents")


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    document = await _get_owned_document(document_id, current_user, db)
    await db.delete(document)
    await db.commit()
    await manager.broadcast(current_user.id, "documents")
