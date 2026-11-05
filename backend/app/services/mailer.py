"""Email delivery boundary for student account activation.

Development deliberately records no token and sends no email. Production requires SMTP
configuration; replacing SMTP with a transactional provider only changes this module.
"""

from __future__ import annotations

import logging
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Protocol

from app.core.config import Settings, get_settings

log = logging.getLogger("edushield.mail")


class InvitationMailer(Protocol):
    def send_activation(
        self, *, recipient: str, student_ref: str, organization_name: str, activation_url: str
    ) -> None: ...


class DevelopmentMailer:
    """Safe local boundary: does not write or log activation URLs/tokens."""

    def send_activation(self, *, recipient: str, student_ref: str, organization_name: str, activation_url: str) -> None:
        del activation_url
        log.info(
            "student_activation_delivery_development",
            extra={"recipient": recipient, "student_ref": student_ref, "organization": organization_name},
        )


@dataclass(frozen=True)
class SMTPMailer:
    settings: Settings

    def send_activation(self, *, recipient: str, student_ref: str, organization_name: str, activation_url: str) -> None:
        message = EmailMessage()
        message["From"] = self.settings.email_from
        message["To"] = recipient
        message["Subject"] = f"Activate your {organization_name} student portal"
        message.set_content(
            f"You have been invited to activate your student portal account ({student_ref}).\n\n"
            f"Activate your account: {activation_url}\n\n"
            "This link can be used once and will expire. If you did not expect this invitation, "
            "contact your institution."
        )
        with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port, timeout=10) as server:
            server.starttls()
            server.login(self.settings.smtp_username, self.settings.smtp_password.get_secret_value())
            server.send_message(message)


def get_invitation_mailer(settings: Settings | None = None) -> InvitationMailer:
    settings = settings or get_settings()
    return SMTPMailer(settings) if settings.email_provider == "smtp" else DevelopmentMailer()
