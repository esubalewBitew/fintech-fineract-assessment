import pytest

from app.domain.states import InvalidTransition, transition


@pytest.mark.parametrize(
    "current,new",
    [
        ("RECEIVED", "RAIL_PENDING"),
        ("RAIL_PENDING", "RAIL_CONFIRMED"),
        ("RAIL_CONFIRMED", "FINERACT_PENDING"),
        ("FINERACT_PENDING", "FINERACT_DONE"),
        ("FINERACT_DONE", "ERP_PENDING"),
        ("ERP_PENDING", "COMPLETED"),
    ],
)
def test_happy_path_transitions(current: str, new: str):
    assert transition(current, new) == new


def test_rejects_illegal():
    with pytest.raises(InvalidTransition):
        transition("COMPLETED", "RECEIVED")
