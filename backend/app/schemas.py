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
    categories: list

    model_config = {"from_attributes": True}
