"""Notification email: one message per event, delivery isolated from the work it reports."""

from __future__ import annotations

import smtplib
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.types import utcnow
from app.models import EmailOutbox, User
from app.seed.base import DEMO_STUDENT_EMAIL
from app.services import email_outbox, mailer
from app.services.email_outbox import MAX_ATTEMPTS, deliver, due_messages
from app.services.email_templates import OUTBOX_TEMPLATES, RenderedEmail, application_decided, password_reset
from app.services.mailer import SMTPMailer
from tests.conftest import NB_OFFICER
from tests.test_application_workflows import _officer_review, _submitted

pytestmark = pytest.mark.seeded

SECRET_WORDS = ("risk", "fraud", "score", "investigat")


class RecordingMailer:
    def __init__(self, fail: bool = False) -> None:
        self.sent: list[tuple[str, RenderedEmail]] = []
        self.fail = fail

    def send(self, *, recipient: str, content: RenderedEmail) -> None:
        if self.fail:
            raise smtplib.SMTPServerDisconnected(f"could not deliver to {recipient}")
        self.sent.append((recipient, content))


@pytest.fixture
def smtp_mode(monkeypatch: pytest.MonkeyPatch) -> RecordingMailer:
    recorder = RecordingMailer()
    settings = get_settings().model_copy(update={"email_provider": "smtp"})
    monkeypatch.setattr(email_outbox, "get_settings", lambda: settings)
    monkeypatch.setattr(email_outbox, "get_mailer", lambda _settings=None: recorder)
    return recorder


def _templates(db: Session) -> list[str]:
    db.expire_all()
    return sorted(db.scalars(select(EmailOutbox.template)).all())


def test_the_lifecycle_queues_one_message_per_event(as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
    student, officer = as_user(DEMO_STUDENT_EMAIL), as_user(NB_OFFICER)
    app = _submitted(student)
    assert _templates(db) == ["application_submitted"]

    _officer_review(
        officer, app["id"], application_status="additional_information_required", student_message="Upload the letter."
    )
    assert student.post(f"/api/v1/student-applications/{app['id']}/submit").status_code == 200
    assert _templates(db) == [
        "additional_information_requested",
        "application_response_received",
        "application_submitted",
        "application_submitted",
    ]

    _officer_review(officer, app["id"], application_status="approved")
    assert _officer_review(officer, app["id"], application_status="approved").status_code == 409
    assert _templates(db).count("application_decided") == 1


def test_staff_who_asked_are_told_when_the_student_responds(as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
    student, officer = as_user(DEMO_STUDENT_EMAIL), as_user(NB_OFFICER)
    app = _submitted(student)
    _officer_review(
        officer, app["id"], application_status="additional_information_required", student_message="Upload the letter."
    )
    student.post(f"/api/v1/student-applications/{app['id']}/submit")
    item = db.scalar(select(EmailOutbox).where(EmailOutbox.template == "application_response_received"))
    requester = db.scalar(select(User).where(User.email == NB_OFFICER))
    assert item is not None and requester is not None and item.recipient_user_id == requester.id


def test_development_never_reports_mail_as_delivered(as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
    _submitted(as_user(DEMO_STUDENT_EMAIL))
    item = db.scalar(select(EmailOutbox))
    assert item is not None
    assert deliver(item.id) in ("suppressed", None)
    db.refresh(item)
    assert item.status == "suppressed" and item.sent_at is None


def test_outbox_stores_no_address_or_private_content(as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
    app = _submitted(as_user(DEMO_STUDENT_EMAIL))
    item = db.scalar(select(EmailOutbox))
    assert item is not None and item.context == {"reference": app["reference"]}


def test_delivery_sends_once_even_if_dispatched_twice(  # type: ignore[no-untyped-def]
    as_user, db: Session, smtp_mode: RecordingMailer
) -> None:
    _submitted(as_user(DEMO_STUDENT_EMAIL))
    item = db.scalar(select(EmailOutbox))
    assert item is not None and item.status == "sent"
    assert deliver(item.id) is None
    assert [recipient for recipient, _ in smtp_mode.sent] == [DEMO_STUDENT_EMAIL]


def test_provider_failures_retry_a_bounded_number_of_times_without_keeping_the_message(  # type: ignore[no-untyped-def]
    as_user, db: Session, smtp_mode: RecordingMailer
) -> None:
    app = _submitted(as_user(DEMO_STUDENT_EMAIL))
    smtp_mode.fail = True
    item = db.scalar(select(EmailOutbox))
    assert item is not None
    item.status = "queued"
    db.commit()
    for _ in range(MAX_ATTEMPTS):
        item.next_attempt_at = None
        db.commit()
        deliver(item.id)
        db.refresh(item)
    assert item.status == "failed" and item.error_code == "SMTPServerDisconnected"
    assert item.id not in due_messages()
    # The student's application is unaffected by the email failing.
    assert as_user(DEMO_STUDENT_EMAIL).get(f"/api/v1/student-applications/{app['id']}").json()["status"] == "submitted"


def test_retry_waits_for_its_backoff(as_user, db: Session, smtp_mode: RecordingMailer) -> None:  # type: ignore[no-untyped-def]
    _submitted(as_user(DEMO_STUDENT_EMAIL))
    smtp_mode.fail = True
    item = db.scalar(select(EmailOutbox))
    assert item is not None
    item.status = "queued"
    db.commit()
    assert deliver(item.id) == "retry"
    db.refresh(item)
    assert item.id not in due_messages() and deliver(item.id) is None
    item.next_attempt_at = utcnow() - timedelta(seconds=1)
    db.commit()
    assert item.id in due_messages()


def test_deactivated_recipients_are_not_emailed(  # type: ignore[no-untyped-def]
    as_user, db: Session, smtp_mode: RecordingMailer
) -> None:
    _submitted(as_user(DEMO_STUDENT_EMAIL))
    item = db.scalar(select(EmailOutbox))
    user = db.scalar(select(User).where(User.email == DEMO_STUDENT_EMAIL))
    assert item is not None and user is not None
    smtp_mode.sent.clear()
    item.status, user.is_active = "queued", False
    db.commit()
    assert deliver(item.id) == "cancelled" and smtp_mode.sent == []


@pytest.mark.parametrize("name", sorted(OUTBOX_TEMPLATES))
def test_templates_never_mention_internal_assessment(name: str) -> None:
    content = OUTBOX_TEMPLATES[name]({"reference": "FA-1"}, "https://aid.example.edu")
    assert "FA-1" in content.text and "https://aid.example.edu/login" in content.text
    assert not any(word in (content.subject + content.text).lower() for word in SECRET_WORDS)


def test_decision_email_does_not_state_the_outcome() -> None:
    content = application_decided({"reference": "FA-1"}, "https://aid.example.edu")
    assert "approved" not in content.text.lower() and "rejected" not in content.text.lower()


def test_operations_counts_outbox_states_for_the_institution(as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
    from tests.conftest import NB_ADMIN

    _submitted(as_user(DEMO_STUDENT_EMAIL))
    item = db.scalar(select(EmailOutbox))
    assert item is not None
    item.status = "failed"
    db.commit()
    body = as_user(NB_ADMIN).get("/api/v1/operations/overview").json()
    assert body["email"]["failed"] == 1
    assert any(f["kind"] == "email" for f in body["jobs"]["recent_failures"])


class FakeSMTP:
    instances: list[FakeSMTP] = []

    def __init__(self, host: str, port: int, timeout: int, **kwargs: object) -> None:
        self.host, self.port, self.timeout, self.kwargs = host, port, timeout, kwargs
        self.started_tls_with: object = None
        self.message = None
        FakeSMTP.instances.append(self)

    def __enter__(self) -> FakeSMTP:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def starttls(self, context: object) -> None:
        self.started_tls_with = context

    def login(self, username: str, password: str) -> None:
        self.login_as = (username, password)

    def send_message(self, message) -> None:  # type: ignore[no-untyped-def]
        self.message = message


@pytest.mark.parametrize(("port", "attribute"), [(587, "SMTP"), (465, "SMTP_SSL")])
def test_smtp_verifies_the_server_certificate(monkeypatch: pytest.MonkeyPatch, port: int, attribute: str) -> None:
    import ssl

    FakeSMTP.instances.clear()
    monkeypatch.setattr(mailer.smtplib, attribute, FakeSMTP)
    settings = get_settings().model_copy(
        update={
            "smtp_host": "smtp.resend.com",
            "smtp_port": port,
            "smtp_username": "resend",
            "smtp_password": _Secret(),
        }
    )
    SMTPMailer(settings).send(
        recipient="s@example.edu", content=password_reset(reset_url="https://x/r", ttl_minutes=30)
    )
    server = FakeSMTP.instances[0]
    context = server.started_tls_with if port == 587 else server.kwargs["context"]
    assert isinstance(context, ssl.SSLContext) and context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
    assert server.login_as == ("resend", "api-key") and server.message["To"] == "s@example.edu"


class _Secret:
    def get_secret_value(self) -> str:
        return "api-key"


def test_unknown_outbox_id_is_ignored() -> None:
    assert deliver(uuid.uuid4()) is None
