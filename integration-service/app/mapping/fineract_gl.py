from app.domain.models import TYPE_TO_FINERACT, USAGE_TO_FINERACT, CoAAccount, FineractGlCreate


def to_fineract_gl(account: CoAAccount) -> FineractGlCreate:
    return FineractGlCreate(
        external_reference=account.external_reference,  # pass-through
        gl_code=account.code,
        name=account.name,
        type=TYPE_TO_FINERACT[account.type.upper()],
        usage=USAGE_TO_FINERACT.get(account.usage.upper(), 1),
        description=account.description or account.name,
        manual_entries_allowed=account.manual_entries_allowed,
    )
