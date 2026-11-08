"""Email delivery boundary.

Development deliberately sends nothing and records no link or token. Production requires SMTP.
Message content lives in email_templates; swapping the transport only changes this module.
"""

from __future__ import annotations

import logging
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Protocol

from app.core.config import Settings, get_settings
from app.services import email_templates
from app.services.email_templates import RenderedEmail

log = logging.getLogger("edushield.mail")
_SMTPS_PORTS = {465, 2465}


class Mailer(Protocol):
    def send(self, *, recipient: str, content: RenderedEmail) -> None: ...


class InvitationMailer(Mailer, Protocol):
    def send_activation(
        self, *, recipient: str, student_ref: str, organization_name: str, activation_url: str
    ) -> None: ...


class _ActivationMixin:
    def send(self, *, recipient: str, content: RenderedEmail) -> None:
        raise NotImplementedError

    def send_activation(self, *, recipient: str, student_ref: str, organization_name: str, activation_url: str) -> None:
        self.send(
            recipient=recipient,
            content=email_templates.student_invitation(
                student_ref=student_ref, organization_name=organization_name, activation_url=activation_url
            ),
        )


class DevelopmentMailer(_ActivationMixin):
    """Safe local boundary: never sends, and never writes message bodies (which can hold links) to logs."""

    def send(self, *, recipient: str, content: RenderedEmail) -> None:
        log.info("email_delivery_development", extra={"recipient": recipient, "subject": content.subject})


@dataclass(frozen=True)
class SMTPMailer(_ActivationMixin):
    settings: Settings

    def send(self, *, recipient: str, content: RenderedEmail) -> None:
        message = EmailMessage()
        message["From"] = self.settings.email_from
        message["To"] = recipient
        message["Subject"] = content.subject
        message.set_content(content.text)
        context = ssl.create_default_context()  # verifies the server's certificate and hostname
        if self.settings.smtp_port in _SMTPS_PORTS:
            with smtplib.SMTP_SSL(
                self.settings.smtp_host, self.settings.smtp_port, timeout=10, context=context
            ) as server:
                self._login_and_send(server, message)
            return
        with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port, timeout=10) as server:
            server.starttls(context=context)
            self._login_and_send(server, message)

    def _login_and_send(self, server: smtplib.SMTP, message: EmailMessage) -> None:
        server.login(self.settings.smtp_username, self.settings.smtp_password.get_secret_value())
        server.send_message(message)


def get_mailer(settings: Settings | None = None) -> InvitationMailer:
    settings = settings or get_settings()
    return SMTPMailer(settings) if settings.email_provider == "smtp" else DevelopmentMailer()


get_invitation_mailer = get_mailer
