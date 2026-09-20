import logging
from email.message import EmailMessage
from email.policy import default as default_email_policy

import aiosmtplib

from app.config import settings

logger = logging.getLogger(__name__)

# The default policy soft-wraps body lines at 78 columns (RFC 5322's
# recommendation) — fine for prose, but it folds a long reset URL mid-token,
# corrupting the link for any client (or, as this bit in testing, a script)
# that doesn't reassemble folded lines. 998 is RFC 5321's actual hard limit
# on a single SMTP line, so this only avoids the wrap, not the standard.
_EMAIL_POLICY = default_email_policy.clone(max_line_length=998)


async def send_password_reset_email(to_email: str, reset_url: str) -> None:
    subject = "Reset your ShopAssistant password"
    body = (
        f"Someone (hopefully you) asked to reset the password for this ShopAssistant account.\n\n"
        f"Reset it here (expires in {settings.password_reset_token_expire_minutes} minutes):\n"
        f"{reset_url}\n\n"
        f"If you didn't ask for this, you can ignore this email — your password hasn't changed."
    )

    if not settings.smtp_host:
        # No SMTP configured (the default for local dev) — log the link
        # instead of failing, so forgot-password is still usable without
        # setting up a real mail server first.
        logger.warning("SMTP not configured; password reset link for %s: %s", to_email, reset_url)
        return

    message = EmailMessage(policy=_EMAIL_POLICY)
    message["From"] = settings.smtp_from
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(body)

    await aiosmtplib.send(
        message,
        hostname=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_user or None,
        password=settings.smtp_password or None,
        start_tls=settings.smtp_use_tls,
    )
