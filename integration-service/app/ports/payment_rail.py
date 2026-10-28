from decimal import Decimal
from typing import Protocol

from app.domain.models import Beneficiary, Payer, RailEvent, RailResult


class PaymentRailPort(Protocol):
    name: str

    def initiate_payout(
        self,
        *,
        idempotency_key: str,
        amount: Decimal,
        currency: str,
        beneficiary: Beneficiary,
    ) -> RailResult: ...

    def initiate_collection(
        self,
        *,
        idempotency_key: str,
        amount: Decimal,
        currency: str,
        payer: Payer,
    ) -> RailResult: ...

    def get_status(self, rail_reference: str) -> RailResult: ...

    def parse_callback(self, headers: dict, body: bytes) -> RailEvent: ...
