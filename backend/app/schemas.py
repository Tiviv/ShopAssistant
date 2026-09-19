import uuid

from pydantic import BaseModel, EmailStr


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
