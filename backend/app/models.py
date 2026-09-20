import uuid
from datetime import date as date_, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    settings: Mapped["ShopSettings"] = relationship(back_populates="owner", uselist=False)


# Mirrors supabase/schema.sql's `settings` table (renamed to ShopSettings here
# since "Settings" already names the app config class in config.py).
class ShopSettings(Base):
    __tablename__ = "settings"

    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    company_name: Mapped[str] = mapped_column(String, nullable=False, default="")
    eik: Mapped[str] = mapped_column(String, nullable=False, default="")
    vat_number: Mapped[str] = mapped_column(String, nullable=False, default="")
    address: Mapped[str] = mapped_column(String, nullable=False, default="")
    mol: Mapped[str] = mapped_column(String, nullable=False, default="")
    iban: Mapped[str] = mapped_column(String, nullable=False, default="")
    next_invoice_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    next_offer_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    next_credit_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    categories: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    owner: Mapped["User"] = relationship(back_populates="settings")


# Mirrors supabase/schema.sql's `products` table. stock is nullable on
# purpose (same as there): null means "not tracked", 0 means "out of stock".
class Product(Base):
    __tablename__ = "products"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False, default="")
    unit: Mapped[str] = mapped_column(String, nullable=False, default="")
    price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    stock: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# Mirrors supabase/schema.sql's `customers` table.
class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    eik: Mapped[str] = mapped_column(String, nullable=False, default="")
    vat_number: Mapped[str] = mapped_column(String, nullable=False, default="")
    address: Mapped[str] = mapped_column(String, nullable=False, default="")
    phone: Mapped[str] = mapped_column(String, nullable=False, default="")
    email: Mapped[str] = mapped_column(String, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# Mirrors supabase/schema.sql's `documents` table (invoices, offers, and
# credit notes all live in one table, distinguished by doc_type). Line items
# are stored as opaque JSON, same as there — the backend never validates
# their shape, just persists whatever the frontend sends.
class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint("doc_type in ('invoice', 'offer', 'credit')", name="documents_doc_type_check"),
        CheckConstraint("payment_method in ('cash', 'card', 'bank')", name="documents_payment_method_check"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    doc_type: Mapped[str] = mapped_column(String, nullable=False)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    date: Mapped[date_] = mapped_column(Date, nullable=False)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="SET NULL"), nullable=True
    )
    customer_name: Mapped[str] = mapped_column(String, nullable=False, default="")
    customer_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    items: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    vat_rate: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=20)
    subtotal: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    vat_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    total: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    paid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    related_invoice_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    converted_from_offer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    payment_method: Mapped[str] = mapped_column(String, nullable=False, default="cash")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# Mirrors supabase/schema.sql's `cash_entries` table — walk-in/till sales
# that never go through the invoice flow.
class CashEntry(Base):
    __tablename__ = "cash_entries"
    __table_args__ = (
        CheckConstraint("payment_method in ('cash', 'card', 'bank')", name="cash_entries_payment_method_check"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    date: Mapped[date_] = mapped_column(Date, nullable=False, index=True)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    payment_method: Mapped[str] = mapped_column(String, nullable=False, default="cash")
    note: Mapped[str] = mapped_column(String, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# Mirrors supabase/schema.sql's `cash_closings` table — one row per calendar
# day, keyed by (owner_id, date) rather than its own id, same as there.
# total* stays nullable: a day closed before these columns existed has no
# snapshot, and the frontend recomputes it live instead of showing 0.
class CashClosing(Base):
    __tablename__ = "cash_closings"

    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    date: Mapped[date_] = mapped_column(Date, primary_key=True)
    counted_cash: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    note: Mapped[str] = mapped_column(String, nullable=False, default="")
    closed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    total_cash: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    total_card: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    total_bank: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    total: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    invoice_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    entry_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    auto_closed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


# A forgot-password link's token, hashed before storage (so a DB dump alone
# can't be used to reset anyone's password — the raw token only ever exists
# in the emailed link and in memory here just long enough to hash it) and
# single-use (used_at set on redemption, checked before honoring a token
# again). No table for access tokens themselves since those are plain JWTs,
# stateless by design — this one needs server-side state specifically so it
# can be invalidated after one use and enumerated/expired independent of
# its own claimed expiry.
class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
