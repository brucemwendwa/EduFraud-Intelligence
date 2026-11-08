#!/usr/bin/env python3
"""Send one test message through the application's real mail path. Contains no token or student data.

Run where the SMTP variables are available, for example with `railway run`, from backend/:

    VERIFY_EMAIL_TO=you@example.edu .venv/bin/python ../scripts/verify_email.py

A server accepting the message is not delivery. Confirm it arrived in the inbox, and check its SPF,
DKIM and DMARC results in the message headers.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.config import get_settings  # noqa: E402
from app.services.email_templates import RenderedEmail  # noqa: E402
from app.services.mailer import SMTPMailer  # noqa: E402


def main() -> int:
    recipient = os.environ.get("VERIFY_EMAIL_TO")
    settings = get_settings()
    if not recipient:
        print("Set VERIFY_EMAIL_TO to a mailbox you can read.", file=sys.stderr)
        return 2
    if settings.email_provider != "smtp" or not settings.smtp_host or not settings.smtp_password:
        print("EMAIL_PROVIDER=smtp and the SMTP settings are required.", file=sys.stderr)
        return 2
    content = RenderedEmail(
        subject="EduShield AI delivery test",
        text="This message confirms that EduShield AI can send email. No action is needed.",
    )
    try:
        SMTPMailer(settings).send(recipient=recipient, content=content)
    except Exception as exc:  # noqa: BLE001 - the class is enough to diagnose, and the message could echo credentials
        print(f"FAILED: {type(exc).__name__}", file=sys.stderr)
        return 1
    print("ACCEPTED by the SMTP server. This is not proof of delivery: confirm it reached the inbox.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
