from decimal import Decimal

from app.domain.models import Beneficiary, Payer, RailEvent, RailResult, RailStatus


class OfflineRail:
    """Immediately confirmed rail for cash / already-settled assessment flows."""

    name = "offline"

    def initiate_payout(
        self,
        *,
        idempotency_key: str,
        amount: Decimal,
        currency: str,
        beneficiary: Beneficiary,
    ) -> RailResult:
        return RailResult(status=RailStatus.CONFIRMED, rail_reference=f"OFF-{idempotency_key}")

    def initiate_collection(
        self,
        *,
        idempotency_key: str,
        amount: Decimal,
        currency: str,
        payer: Payer,
    ) -> RailResult:
        return RailResult(status=RailStatus.CONFIRMED, rail_reference=f"OFF-{idempotency_key}")

    def get_status(self, rail_reference: str) -> RailResult:
        return RailResult(status=RailStatus.CONFIRMED, rail_reference=rail_reference)

    def parse_callback(self, headers: dict, body: bytes) -> RailEvent:
        raise NotImplementedError("offline rail has no callbacks")
