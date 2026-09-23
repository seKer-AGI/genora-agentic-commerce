"""Payment provider abstraction.

Business logic depends only on :class:`PaymentProvider`. Two implementations ship:

* ``SandboxPaymentProvider`` — deterministic test provider for development/CI. It moves no money.
  Payment method tokens ``pm_card_visa`` (approve) and ``pm_card_declined`` (decline) mirror the
  conventions of common gateways so flows can be tested end-to-end.
* ``StripePaymentProvider`` — creates and confirms Stripe PaymentIntents over the Stripe REST API.
  Requires ``STRIPE_API_KEY``; it has not been exercised against live Stripe in this repository.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from functools import lru_cache
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.errors import ServiceUnavailable
from app.models.enums import PaymentStatus


@dataclass
class PaymentResult:
    status: PaymentStatus
    provider_reference: str | None
    failure_reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def succeeded(self) -> bool:
        return self.status in (PaymentStatus.AUTHORIZED, PaymentStatus.CAPTURED)


class PaymentProvider(ABC):
    name: str

    @abstractmethod
    def charge(self, *, amount: Decimal, currency: str, payment_method: str, idempotency_key: str,
               description: str, metadata: dict[str, str]) -> PaymentResult: ...

    @abstractmethod
    def refund(self, *, provider_reference: str, amount: Decimal, idempotency_key: str) -> PaymentResult: ...


class SandboxPaymentProvider(PaymentProvider):
    name = "sandbox"
    DECLINE_TOKENS = {"pm_card_declined", "pm_card_insufficient_funds"}

    def charge(self, *, amount: Decimal, currency: str, payment_method: str, idempotency_key: str,
               description: str, metadata: dict[str, str]) -> PaymentResult:
        ref = f"sbx_{uuid.uuid5(uuid.NAMESPACE_URL, idempotency_key).hex[:24]}"
        if payment_method in self.DECLINE_TOKENS:
            return PaymentResult(PaymentStatus.FAILED, ref, "Card was declined (sandbox)", {"sandbox": True})
        if amount <= 0:
            return PaymentResult(PaymentStatus.FAILED, ref, "Invalid amount", {"sandbox": True})
        return PaymentResult(PaymentStatus.CAPTURED, ref, None, {"sandbox": True, "method": payment_method})

    def refund(self, *, provider_reference: str, amount: Decimal, idempotency_key: str) -> PaymentResult:
        return PaymentResult(PaymentStatus.REFUNDED, provider_reference, None, {"sandbox": True})


class StripePaymentProvider(PaymentProvider):
    name = "stripe"
    API = "https://api.stripe.com/v1"

    def __init__(self, api_key: str, transport: httpx.BaseTransport | None = None) -> None:
        self._client = httpx.Client(base_url=self.API, auth=(api_key, ""), timeout=20, transport=transport)

    def _post(self, path: str, data: dict[str, Any], idem: str) -> dict[str, Any]:
        try:
            resp = self._client.post(path, data=data, headers={"Idempotency-Key": idem})
        except httpx.HTTPError as exc:
            raise ServiceUnavailable("Payment provider is unreachable", code="PAYMENT_PROVIDER_DOWN") from exc
        body = resp.json()
        if resp.status_code >= 500:
            raise ServiceUnavailable("Payment provider error", code="PAYMENT_PROVIDER_DOWN")
        return body

    def charge(self, *, amount: Decimal, currency: str, payment_method: str, idempotency_key: str,
               description: str, metadata: dict[str, str]) -> PaymentResult:
        data: dict[str, Any] = {
            "amount": int((amount * 100).to_integral_value()),
            "currency": currency.lower(),
            "payment_method": payment_method,
            "confirm": "true",
            "description": description,
            "automatic_payment_methods[enabled]": "true",
            "automatic_payment_methods[allow_redirects]": "never",
        }
        for k, v in metadata.items():
            data[f"metadata[{k}]"] = v
        body = self._post("/payment_intents", data, idempotency_key)
        if "error" in body:
            err = body["error"]
            ref = (err.get("payment_intent") or {}).get("id")
            return PaymentResult(PaymentStatus.FAILED, ref, err.get("message", "Payment failed"))
        status = {
            "succeeded": PaymentStatus.CAPTURED,
            "requires_capture": PaymentStatus.AUTHORIZED,
            "processing": PaymentStatus.PENDING,
        }.get(body.get("status"), PaymentStatus.FAILED)
        return PaymentResult(status, body.get("id"), None if status != PaymentStatus.FAILED else body.get("status"))

    def refund(self, *, provider_reference: str, amount: Decimal, idempotency_key: str) -> PaymentResult:
        body = self._post("/refunds", {"payment_intent": provider_reference,
                                       "amount": int((amount * 100).to_integral_value())}, idempotency_key)
        if "error" in body:
            return PaymentResult(PaymentStatus.FAILED, provider_reference, body["error"].get("message"))
        return PaymentResult(PaymentStatus.REFUNDED, provider_reference, None, {"refund_id": body.get("id")})


@lru_cache
def get_payment_provider() -> PaymentProvider:
    s = get_settings()
    if s.payment_provider == "stripe":
        if not s.stripe_api_key:
            raise RuntimeError("STRIPE_API_KEY is required when PAYMENT_PROVIDER=stripe")
        return StripePaymentProvider(s.stripe_api_key.get_secret_value())
    return SandboxPaymentProvider()
