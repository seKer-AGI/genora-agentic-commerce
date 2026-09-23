"""E-mail abstraction. The default sender queues messages in `email_outbox`.

A production deployment plugs in an SMTP/SES/SendGrid sender that drains the outbox. Tokens are
never written to application logs.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from sqlalchemy.orm import Session

from app.models.identity import EmailOutbox


class EmailSender(ABC):
    @abstractmethod
    def send(self, db: Session, *, to: str, subject: str, body: str, template: str) -> None: ...


class OutboxEmailSender(EmailSender):
    def send(self, db: Session, *, to: str, subject: str, body: str, template: str) -> None:
        db.add(EmailOutbox(to_email=to, subject=subject, body=body, template=template))


def get_email_sender() -> EmailSender:
    return OutboxEmailSender()
