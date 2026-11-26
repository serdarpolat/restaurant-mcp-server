"""Recipe-based stock consumption, shared by live orders and the demo data generator."""

from collections.abc import Iterable
from decimal import ROUND_CEILING, Decimal

# Modifiers that scale how much of every ingredient a portion uses.
PORTION_MULTIPLIERS = {"1.5 Portion": Decimal("1.5")}

# Units that only exist in whole pieces: a kitchen cannot use 1.5 flatbreads or half a can of cola.
COUNT_UNITS = frozenset({"piece"})


def portion_multiplier(modifier_names: Iterable[str]) -> Decimal:
    mult = Decimal(1)
    for name in modifier_names:
        mult *= PORTION_MULTIPLIERS.get(name, Decimal(1))
    return mult


def line_consumption(
    per_portion: Decimal, quantity: int, multiplier: Decimal, unit: str
) -> Decimal:
    """Ingredient used by one order line. Count units are rounded up to whole pieces."""
    used = per_portion * quantity * multiplier
    if unit in COUNT_UNITS:
        used = used.to_integral_value(rounding=ROUND_CEILING)
    return used
