"""Gmail SMTP helper for Bol Do call reports.

Single function: send a plain-text email summarizing how a call went.
Uses STARTTLS on port 587. App-password auth (Gmail blocks plain passwords).
"""

from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from typing import Iterable

from loguru import logger


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def send_call_report(
    *,
    to_number: str,
    task: str,
    tone: str,
    outcome: str,
    summary: str,
    transcript: Iterable[tuple[str, str]] | None = None,
) -> bool:
    """Send a call summary email. Returns True on success, False otherwise."""
    host = _env("SMTP_HOST", "smtp.gmail.com")
    port = int(_env("SMTP_PORT", "587"))
    user = _env("SMTP_USER")
    pwd = _env("SMTP_PASS").replace(" ", "")  # Gmail shows app pwd with spaces
    to_addr = _env("SMTP_TO") or user

    if not (user and pwd and to_addr):
        logger.warning("SMTP not configured (need SMTP_USER + SMTP_PASS); skipping email")
        return False

    lines = [
        f"To number : {to_number}",
        f"Task      : {task}",
        f"Tone      : {tone}",
        f"Outcome   : {outcome}",
        "",
        "Summary:",
        summary or "(none provided by bot)",
    ]
    # transcript parameter kept for compatibility, no longer included in email body

    msg = EmailMessage()
    msg["Subject"] = f"Bol Do · {outcome} · {to_number}"
    msg["From"] = user
    msg["To"] = to_addr
    msg.set_content("\n".join(lines))

    try:
        with smtplib.SMTP(host, port, timeout=15) as s:
            s.starttls()
            s.login(user, pwd)
            s.send_message(msg)
        logger.info(f"Call report emailed to {to_addr}")
        return True
    except Exception as e:
        logger.error(f"SMTP send failed: {e}")
        return False
