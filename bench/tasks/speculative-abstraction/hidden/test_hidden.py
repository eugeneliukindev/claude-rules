"""Hidden checks for speculative-abstraction: Stripe works, and no contract has a single implementation."""

import ast
from decimal import Decimal
from pathlib import Path

from shop.orders import Order
from shop.stripe_client import StripeClient


class FakeStripe(StripeClient):
    def __init__(self) -> None:
        self.charges: list[tuple[int, str, str]] = []

    def create_charge(self, *, amount_cents: int, currency: str, source: str) -> str:
        self.charges.append((amount_cents, currency, source))
        return "ch_1"


def test_gate_charges_in_cents() -> None:
    from shop.payments import charge

    stripe = FakeStripe()
    charge(Order(id=1, total=Decimal("9.99"), currency="EUR"), card_token="tok_1", client=stripe)
    assert stripe.charges == [(999, "EUR", "tok_1")]


def _protocols() -> list[str]:
    found = []
    for path in Path("shop").glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ClassDef):
                bases = {ast.unparse(base).split(".")[-1].split("[")[0] for base in node.bases}
                if "Protocol" in bases:
                    found.append(node.name)
    return found


def test_design_own_contracts_are_abstract_base_classes() -> None:
    assert not _protocols(), f"protocols in own code: {_protocols()}"
