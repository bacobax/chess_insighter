from __future__ import annotations

from html import escape
import hashlib

from backend.settings import settings


class EmailDeliveryUnavailable(RuntimeError):
    pass


async def send_verification_email(*, recipient: str, token: str) -> None:
    if not settings.resend_api_key or not settings.resend_from_email:
        raise EmailDeliveryUnavailable("Resend is not configured. Set RESEND_API_KEY and RESEND_FROM_EMAIL.")
    try:
        import resend
    except ImportError as exc:
        raise EmailDeliveryUnavailable("The Resend Python package is not installed.") from exc

    verification_url = f"{settings.frontend_url}/verify-email?token={token}"
    safe_url = escape(verification_url, quote=True)
    resend.api_key = settings.resend_api_key
    params: resend.Emails.SendParams = {
        "from": settings.resend_from_email,
        "to": [recipient],
        "subject": "Verify your Chess Insighter account",
        "html": (
            "<div style='background:#0e1210;color:#f3efe6;padding:40px;font-family:Arial,sans-serif'>"
            "<p style='letter-spacing:.16em;text-transform:uppercase;color:#91a38f'>Chess Insighter</p>"
            "<h1 style='font-size:32px'>Confirm your account</h1>"
            "<p style='line-height:1.7;color:#c7c3ba'>Open the link below to activate your account. "
            "It expires in 24 hours.</p>"
            f"<p><a href='{safe_url}' style='display:inline-block;background:#f3efe6;color:#0e1210;padding:14px 20px;text-decoration:none'>Verify email</a></p>"
            "</div>"
        ),
        "text": f"Verify your Chess Insighter account: {verification_url}",
    }
    try:
        await resend.Emails.send_async(
            params,
            options={"idempotency_key": f"verify-{hashlib.sha256(token.encode('utf-8')).hexdigest()}"},
        )
    except Exception as exc:
        raise EmailDeliveryUnavailable("Could not send the verification email.") from exc
