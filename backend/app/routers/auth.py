from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import (
    create_access_token,
    generate_password_reset_token,
    get_current_user,
    hash_password,
    hash_reset_token,
    verify_password,
)
from app.config import settings
from app.database import get_db
from app.email import send_password_reset_email
from app.models import PasswordResetToken, ShopSettings, User
from app.schemas import ForgotPasswordRequest, LoginRequest, ResetPasswordRequest, SignupRequest, Token, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=Token, status_code=status.HTTP_201_CREATED)
async def signup(body: SignupRequest, db: AsyncSession = Depends(get_db)) -> Token:
    existing = await db.scalar(select(User).where(User.email == body.email))
    if existing:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Email already registered")

    user = User(email=body.email, password_hash=hash_password(body.password))
    db.add(user)
    await db.flush()
    # Mirrors handle_new_user in supabase/schema.sql: every signup gets an
    # empty settings row immediately, so the frontend never has to special-case
    # "no settings yet" beyond the one insert-if-missing it already does.
    db.add(ShopSettings(owner_id=user.id))
    await db.commit()

    return Token(access_token=create_access_token(user.id))


@router.post("/login", response_model=Token)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)) -> Token:
    user = await db.scalar(select(User).where(User.email == body.email))
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    return Token(access_token=create_access_token(user.id))


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.post("/forgot-password", status_code=status.HTTP_200_OK)
async def forgot_password(body: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)) -> dict:
    user = await db.scalar(select(User).where(User.email == body.email))
    if user is not None:
        raw_token, token_hash, expires_at = generate_password_reset_token()
        db.add(PasswordResetToken(user_id=user.id, token_hash=token_hash, expires_at=expires_at))
        await db.commit()
        reset_url = f"{settings.frontend_url}?reset_token={raw_token}"
        await send_password_reset_email(user.email, reset_url)
    # Always the same response whether or not that email is registered —
    # otherwise this endpoint becomes a way to check who has an account.
    return {"detail": "If that email has an account, a reset link has been sent."}


@router.post("/reset-password", status_code=status.HTTP_200_OK)
async def reset_password(body: ResetPasswordRequest, db: AsyncSession = Depends(get_db)) -> dict:
    token_hash = hash_reset_token(body.token)
    reset_token = await db.scalar(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)
    )
    now = datetime.now(timezone.utc)
    if (
        reset_token is None
        or reset_token.used_at is not None
        or reset_token.expires_at < now
    ):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired reset link")

    user = await db.get(User, reset_token.user_id)
    user.password_hash = hash_password(body.new_password)
    reset_token.used_at = now
    await db.commit()
    return {"detail": "Password updated."}
