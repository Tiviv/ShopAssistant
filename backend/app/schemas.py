import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class SignupRequest(BaseModel):
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=6)


class UserOut(BaseModel):
    id: uuid.UUID
    email: EmailStr

    model_config = {"from_attributes": True}


class ProductIn(BaseModel):
    name: str = Field(min_length=1)
    category: str = ""
    unit: str = ""
    price: float = 0
    stock: float | None = None


class RenameCategoryRequest(BaseModel):
    old_name: str
    new_name: str


class AdjustStockRequest(BaseModel):
    qty: float


class ProductOut(BaseModel):
    id: uuid.UUID
    name: str
    category: str
    unit: str
    price: float
    stock: float | None

    model_config = {"from_attributes": True}


class CustomerIn(BaseModel):
    name: str = Field(min_length=1)
    eik: str = ""
    vat_number: str = ""
    address: str = ""
    phone: str = ""
    email: str = ""


class CustomerOut(BaseModel):
    id: uuid.UUID
    name: str
    eik: str
    vat_number: str
    address: str
    phone: str
    email: str

    model_config = {"from_attributes": True}


DocType = Literal["invoice", "offer", "credit"]
PaymentMethod = Literal["cash", "card", "bank"]


# The fields a document keeps when it's edited after creation — doc_type,
# number, related_invoice_number and converted_from_offer_id are set once at
# creation and never change from here (mirrors the frontend: saveDoc's edit
# path only ever sends this subset).
class DocumentUpdate(BaseModel):
    date: date
    customer_id: uuid.UUID | None = None
    customer_name: str = ""
    customer_snapshot: dict | None = None
    items: list = Field(default_factory=list)
    vat_rate: float = 20
    subtotal: float = 0
    vat_amount: float = 0
    total: float = 0
    paid: bool = False
    payment_method: PaymentMethod = "cash"


class DocumentCreate(DocumentUpdate):
    doc_type: DocType
    number: int
    related_invoice_number: int | None = None
    converted_from_offer_id: uuid.UUID | None = None


class DocumentOut(BaseModel):
    id: uuid.UUID
    doc_type: DocType
    number: int
    date: date
    customer_id: uuid.UUID | None
    customer_name: str
    customer_snapshot: dict | None
    items: list
    vat_rate: float
    subtotal: float
    vat_amount: float
    total: float
    paid: bool
    related_invoice_number: int | None
    converted_from_offer_id: uuid.UUID | None
    payment_method: str
    created_at: datetime

    model_config = {"from_attributes": True}


class SetPaidRequest(BaseModel):
    paid: bool


class NextDocumentNumberRequest(BaseModel):
    doc_type: DocType


class NextDocumentNumberResponse(BaseModel):
    number: int


class LinkCustomerRequest(BaseModel):
    customer_id: uuid.UUID


class CashEntryIn(BaseModel):
    date: date
    amount: float = 0
    payment_method: PaymentMethod = "cash"
    note: str = ""


class CashEntryOut(BaseModel):
    id: uuid.UUID
    date: date
    amount: float
    payment_method: str
    note: str
    created_at: datetime

    model_config = {"from_attributes": True}


# No `date` field: the date is the URL path segment (the table's composite
# key is (owner_id, date), so it's never something this body could change).
class CashClosingIn(BaseModel):
    counted_cash: float = 0
    note: str = ""
    total_cash: float | None = None
    total_card: float | None = None
    total_bank: float | None = None
    total: float | None = None
    invoice_count: int | None = None
    entry_count: int | None = None
    auto_closed: bool = False


class CashClosingOut(BaseModel):
    date: date
    counted_cash: float
    note: str
    closed_at: datetime
    total_cash: float | None
    total_card: float | None
    total_bank: float | None
    total: float | None
    invoice_count: int | None
    entry_count: int | None
    auto_closed: bool

    model_config = {"from_attributes": True}


class CloseForgottenDaysResponse(BaseModel):
    closed: int


class SettingsOut(BaseModel):
    owner_id: uuid.UUID
    company_name: str
    eik: str
    vat_number: str
    address: str
    mol: str
    iban: str
    next_invoice_no: int
    next_offer_no: int
    next_credit_no: int
    # Two shapes on purpose: a plain array (legacy) or {custom, hidden} (since
    # categories became renamable/hideable) — see the comment on catConfig()
    # in index.html. Both are valid JSONB in this column; the frontend reads
    # either.
    categories: list | dict

    model_config = {"from_attributes": True}


# Every field optional: mirrors Supabase's .update(patch), which only ever
# touched the columns actually named in the patch. The frontend sends very
# different partial shapes here — the full company-info form, a
# categories-only patch, a counters-only patch during import restore — and
# this one endpoint has to accept all of them without overwriting whatever
# wasn't included.
class SettingsUpdate(BaseModel):
    company_name: str | None = None
    eik: str | None = None
    vat_number: str | None = None
    address: str | None = None
    mol: str | None = None
    iban: str | None = None
    categories: list | dict | None = None
    next_invoice_no: int | None = None
    next_offer_no: int | None = None
    next_credit_no: int | None = None

    model_config = {"from_attributes": True}
