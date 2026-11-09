"""Message content, kept apart from delivery and business logic.

Notifications deliberately say little: reasons, staff notes and risk information stay behind
sign-in, because email is a far weaker channel than the portal.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RenderedEmail:
    subject: str
    text: str


_FOOTER = "\n\nThis is an automated message from EduShield AI. Please do not reply."


def student_invitation(*, student_ref: str, organization_name: str, activation_url: str) -> RenderedEmail:
    return RenderedEmail(
        subject=f"Activate your {organization_name} student portal",
        text=(
            f"You have been invited to activate your student portal account ({student_ref}).\n\n"
            f"Activate your account: {activation_url}\n\n"
            "This link can be used once and will expire. If you did not expect this invitation, "
            f"contact your institution.{_FOOTER}"
        ),
    )


def staff_invitation(*, organization_name: str, role_name: str, activation_url: str) -> RenderedEmail:
    return RenderedEmail(
        subject=f"You have been invited to EduShield AI at {organization_name}",
        text=(
            f"{organization_name} has invited you to EduShield AI as: {role_name}.\n\n"
            f"Set your password: {activation_url}\n\n"
            "This link can be used once and will expire. If you did not expect this invitation, "
            f"contact your institution's administrator.{_FOOTER}"
        ),
    )


def password_reset(*, reset_url: str, ttl_minutes: int) -> RenderedEmail:
    return RenderedEmail(
        subject="Reset your EduShield AI password",
        text=(
            f"Use this link to choose a new password: {reset_url}\n\n"
            f"The link works once and expires in {ttl_minutes} minutes. If you did not ask for this, you can "
            f"ignore this message and your password will not change.{_FOOTER}"
        ),
    )


def _sign_in(app_url: str) -> str:
    return f"Sign in to view the details: {app_url}/login"


def application_submitted(context: dict[str, Any], app_url: str) -> RenderedEmail:
    reference = context["reference"]
    return RenderedEmail(
        subject=f"We received your financial aid application {reference}",
        text=f"Your application {reference} has been submitted for review.\n\n{_sign_in(app_url)}{_FOOTER}",
    )


def additional_information_requested(context: dict[str, Any], app_url: str) -> RenderedEmail:
    reference = context["reference"]
    return RenderedEmail(
        subject=f"More information is needed for application {reference}",
        text=f"Your financial aid office needs more information for {reference}.\n\n{_sign_in(app_url)}{_FOOTER}",
    )


def application_decided(context: dict[str, Any], app_url: str) -> RenderedEmail:
    reference = context["reference"]
    return RenderedEmail(
        subject=f"A decision is available for application {reference}",
        text=f"A decision has been recorded for your application {reference}.\n\n{_sign_in(app_url)}{_FOOTER}",
    )


def application_response_received(context: dict[str, Any], app_url: str) -> RenderedEmail:
    reference = context["reference"]
    return RenderedEmail(
        subject=f"Student responded on application {reference}",
        text=f"The student has responded to your information request on {reference}.\n\n{_sign_in(app_url)}{_FOOTER}",
    )


OUTBOX_TEMPLATES: dict[str, Callable[[dict[str, Any], str], RenderedEmail]] = {
    "application_submitted": application_submitted,
    "additional_information_requested": additional_information_requested,
    "application_decided": application_decided,
    "application_response_received": application_response_received,
}
