from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = "postgresql+asyncpg://shopassistant:shopassistant@localhost:5433/shopassistant"
    jwt_secret: str = "change-me-to-a-long-random-string"
    jwt_algorithm: str = "HS256"
    # There's no refresh-token flow (see docs/python-backend-plan.md) — the
    # access token itself is what's stored in the browser and used until it
    # expires. Now that this backend is the app's only login (not a
    # secondary connection alongside Supabase's own session handling), a
    # short expiry would log a shop's staff out mid-shift, so this is long
    # on purpose. Real refresh-token rotation would be the more correct
    # long-term fix, not something to build speculatively before this
    # actually causes a problem for someone.
    access_token_expire_minutes: int = 60 * 24 * 14  # 14 days
    # Safe as a wildcard here — see the comment on CORSMiddleware in main.py.
    cors_origins: str = "*"

    # ---- password reset email (see app/email.py) ----
    # Any SMTP provider works here (Gmail app password, Mailtrap for dev,
    # a transactional service's SMTP relay, self-hosted Postfix, ...) — this
    # isn't tied to one vendor. Leave smtp_host empty to disable sending
    # (forgot-password then logs the reset link instead of emailing it,
    # which is what local dev without real SMTP configured should do).
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True
    smtp_from: str = "no-reply@shopassistant.local"
    # Where the emailed link points — the frontend's own URL, since that's
    # what opens the "set a new password" screen with ?reset_token=...
    frontend_url: str = "http://localhost:8791/index.html"
    password_reset_token_expire_minutes: int = 30

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
