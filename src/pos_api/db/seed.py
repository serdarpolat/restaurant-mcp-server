"""Generate a realistic, reproducible dataset for a kebab restaurant.

The data is synthetic but follows real-world patterns so that analytical
questions have meaningful answers:

- Lunch (12-14) and dinner (19-21) peaks; busier Fridays and weekends.
- Seasonality: cold drinks fade and soups/tea rise as summer turns to autumn.
- A menu-wide price increase ~45 days ago (historical prices are preserved).
- "Beyti Kebab" is a rising star; one waiter consistently outsells the others.
- A public holiday (Oct 29) with a traffic spike.
- ~1.5% voided items and ~1.5% cancelled orders, with reasons.
- A full stock ledger (daily sales, purchases, waste). A few ingredients end
  below their reorder level because of a supplier delay in the last days.
- Every order belongs to a user: a reused registered customer (70%) or a
  fresh one-off guest checkout (30%, no persistent guest identity).
- Today's data stops at the current time, with a few tables still open.

Usage:
    python -m pos_api.db.seed            # create tables + seed (if empty)
    python -m pos_api.db.seed --reset    # drop everything and reseed
"""

from __future__ import annotations

import argparse
import os
import random
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal

from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from pos_api.db.database import (
    RESTAURANT_TZ,
    create_db_and_tables,
    drop_db_and_tables,
    engine,
)
from pos_api.db.models import (
    Category,
    DiningTable,
    Ingredient,
    MenuItem,
    Modifier,
    ModifierGroup,
    Order,
    OrderChannel,
    OrderItem,
    OrderItemStatus,
    OrderStatus,
    Payment,
    PaymentMethod,
    RecipeItem,
    Staff,
    StaffRole,
    StockMovement,
    StockReason,
    TableStatus,
    User,
    UserType,
)
from pos_api.stock import COUNT_UNITS, line_consumption, portion_multiplier

SEED = 42
DAYS = 90
BASE_ORDERS_PER_DAY = 95
PRICE_INCREASE_DAYS_AGO = 45
PRICE_INCREASE_RATE = Decimal("1.08")
SUPPLIER_DELAY_DAYS = 5
DELAYED_INGREDIENTS = {"Ground Beef", "Flatbread", "Eggplant"}
N_REGISTERED_USERS = 150

D = Decimal


def q2(value: Decimal) -> Decimal:
    return value.quantize(D("0.01"), rounding=ROUND_HALF_UP)


def q3(value: Decimal) -> Decimal:
    return value.quantize(D("0.001"), rounding=ROUND_HALF_UP)


# --------------------------------------------------------------------------- #
# Static reference data
# --------------------------------------------------------------------------- #

STAFF = [
    ("James Wilson", StaffRole.manager),
    ("Patricia Moore", StaffRole.cashier),
    ("Daniel Carter", StaffRole.waiter),
    ("Olivia Bennett", StaffRole.waiter),
    ("Ryan Mitchell", StaffRole.waiter),
    ("Sophia Turner", StaffRole.waiter),
    ("Ethan Brooks", StaffRole.waiter),
    ("Grace Foster", StaffRole.waiter),
]
# Relative share of tables each waiter serves (Daniel is the star performer).
WAITER_WEIGHTS = {
    "Daniel Carter": 1.6,
    "Olivia Bennett": 1.2,
    "Ryan Mitchell": 1.0,
    "Sophia Turner": 1.0,
    "Ethan Brooks": 0.8,
    "Grace Foster": 0.9,
}

TABLES = (
    [(f"Hall {i}", "Hall", c) for i, c in enumerate([2, 2, 4, 4, 4, 6, 6, 8], start=1)]
    + [(f"Garden {i}", "Garden", c) for i, c in enumerate([2, 4, 4, 4, 6], start=1)]
    + [(f"Terrace {i}", "Terrace", c) for i, c in enumerate([4, 6], start=1)]
)

FIRST_NAMES = [
    "James", "Mary", "John", "Patricia", "Robert", "Jennifer", "Michael", "Linda",
    "David", "Elizabeth", "William", "Barbara", "Richard", "Susan", "Joseph", "Jessica",
    "Thomas", "Sarah", "Charles", "Karen", "Daniel", "Nancy", "Matthew", "Lisa",
    "Anthony", "Betty", "Mark", "Margaret", "Donald", "Sandra", "Steven", "Ashley",
    "Paul", "Kimberly", "Andrew", "Emily", "Joshua", "Donna", "Kevin", "Michelle",
]  # fmt: skip
LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson",
    "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson",
    "White", "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson",
]  # fmt: skip

# name: (unit, unit_cost)
INGREDIENTS = {
    "Ground Beef": ("kg", 650),
    "Lamb Meat": ("kg", 900),
    "Lamb Chops (raw)": ("kg", 1400),
    "Chicken Thigh": ("kg", 280),
    "Flatbread": ("piece", 6),
    "Pide Dough": ("piece", 12),
    "Lahmacun Dough": ("piece", 8),
    "Kashar Cheese": ("kg", 450),
    "Egg": ("piece", 6),
    "Red Lentils": ("kg", 90),
    "Bulgur": ("kg", 50),
    "Rice": ("kg", 70),
    "Tomato": ("kg", 40),
    "Onion": ("kg", 25),
    "Green Pepper": ("kg", 60),
    "Eggplant": ("kg", 50),
    "Parsley": ("bunch", 15),
    "Lemon": ("kg", 60),
    "Yogurt": ("kg", 90),
    "Butter": ("kg", 600),
    "Kunefe (ready-made)": ("piece", 90),
    "Pistachio Baklava (bulk)": ("kg", 1000),
    "Rice Pudding (ready-made)": ("piece", 40),
    "Ayran": ("piece", 15),
    "Cola": ("piece", 30),
    "Water": ("piece", 6),
    "Turnip Juice": ("piece", 25),
    "Soda": ("piece", 18),
    "Tea": ("kg", 400),
    "Turkish Coffee": ("kg", 900),
}

CATEGORIES = [
    "Soups",
    "Starters",
    "Kebabs",
    "Grills",
    "Flatbreads",
    "Salads",
    "Desserts",
    "Beverages",
]

# Modifier groups: name -> (min, max, [(modifier, price_delta)])
MODIFIER_GROUPS = {
    "Spice Level": (1, 1, [("Spicy", 0), ("Mild", 0), ("Not Spicy", 0)]),
    "Portion": (0, 1, [("1.5 Portion", 250)]),
    "Pide Extras": (0, 2, [("Extra Cheese", 60), ("Extra Egg", 30)]),
    "Size": (0, 1, [("Large", 20)]),
}


@dataclass
class ItemSpec:
    name: str
    category: str
    price: int
    description: str
    recipe: dict[str, float]
    weight: float = 1.0
    groups: list[str] = field(default_factory=list)


KEBAB_GROUPS = ["Spice Level", "Portion"]

MENU: list[ItemSpec] = [
    # Soups
    ItemSpec(
        "Lentil Soup",
        "Soups",
        150,
        "Served with butter and lemon.",
        {"Red Lentils": 0.06, "Onion": 0.02, "Butter": 0.01, "Lemon": 0.02},
        6,
    ),
    ItemSpec(
        "Ezogelin Soup",
        "Soups",
        150,
        "Traditional soup with bulgur and mint.",
        {"Red Lentils": 0.05, "Bulgur": 0.02, "Onion": 0.02},
        3,
    ),
    ItemSpec(
        "Yayla Soup",
        "Soups",
        160,
        "Yogurt soup with rice and mint.",
        {"Yogurt": 0.1, "Rice": 0.02, "Butter": 0.01},
        2,
    ),
    # Starters
    ItemSpec("Haydari", "Starters", 140, "Strained yogurt, garlic, mint.", {"Yogurt": 0.15}, 3),
    ItemSpec(
        "Spicy Ezme",
        "Starters",
        130,
        "Finely chopped tomato, pepper and onion.",
        {"Tomato": 0.1, "Green Pepper": 0.03, "Onion": 0.03, "Parsley": 0.1},
        5,
    ),
    ItemSpec(
        "Stuffed Bulgur Balls",
        "Starters",
        90,
        "Priced per piece.",
        {"Ground Beef": 0.03, "Bulgur": 0.05, "Onion": 0.01},
        3,
    ),
    # Kebabs
    ItemSpec(
        "Adana Kebab",
        "Kebabs",
        560,
        "Spicy ground meat skewer, flatbread, grilled tomato-pepper.",
        {"Ground Beef": 0.2, "Flatbread": 1, "Tomato": 0.05, "Green Pepper": 0.03, "Onion": 0.05},
        10,
        KEBAB_GROUPS,
    ),
    ItemSpec(
        "Urfa Kebab",
        "Kebabs",
        560,
        "Mild ground meat skewer, flatbread, grilled vegetables.",
        {"Ground Beef": 0.2, "Flatbread": 1, "Tomato": 0.05, "Green Pepper": 0.03, "Onion": 0.05},
        5,
        ["Portion"],
    ),
    ItemSpec(
        "Beyti Kebab",
        "Kebabs",
        640,
        "Kebab wrapped in flatbread, with yogurt and butter.",
        {"Ground Beef": 0.2, "Flatbread": 2, "Yogurt": 0.1, "Butter": 0.02},
        4,
        KEBAB_GROUPS,
    ),
    ItemSpec(
        "Iskender Kebab",
        "Kebabs",
        620,
        "Lamb over pide, tomato sauce, yogurt, butter.",
        {"Lamb Meat": 0.2, "Pide Dough": 0.5, "Yogurt": 0.1, "Butter": 0.03, "Tomato": 0.05},
        6,
        ["Portion"],
    ),
    ItemSpec(
        "Eggplant Kebab",
        "Kebabs",
        600,
        "Eggplant and ground meat skewer, with flatbread.",
        {"Ground Beef": 0.18, "Eggplant": 0.25, "Flatbread": 1, "Tomato": 0.05},
        2,
        KEBAB_GROUPS,
    ),
    ItemSpec(
        "Ali Nazik",
        "Kebabs",
        650,
        "Lamb over smoky eggplant-yogurt puree.",
        {"Lamb Meat": 0.18, "Eggplant": 0.2, "Yogurt": 0.1, "Butter": 0.02},
        2,
    ),
    ItemSpec(
        "Lamb Shish",
        "Kebabs",
        720,
        "Marinated cubed lamb.",
        {"Lamb Meat": 0.22, "Flatbread": 1, "Tomato": 0.05, "Green Pepper": 0.03},
        3,
        ["Portion"],
    ),
    ItemSpec(
        "Chicken Shish",
        "Kebabs",
        420,
        "Marinated chicken thigh.",
        {"Chicken Thigh": 0.22, "Flatbread": 1, "Tomato": 0.05, "Green Pepper": 0.03},
        6,
        ["Portion"],
    ),
    ItemSpec(
        "Chicken Wings",
        "Kebabs",
        400,
        "Grilled spiced wings.",
        {"Chicken Thigh": 0.3, "Flatbread": 1},
        4,
        KEBAB_GROUPS,
    ),
    ItemSpec(
        "Mixed Grill",
        "Kebabs",
        950,
        "Adana, lamb shish and chicken shish together.",
        {
            "Ground Beef": 0.1,
            "Lamb Meat": 0.1,
            "Chicken Thigh": 0.1,
            "Flatbread": 1,
            "Tomato": 0.05,
        },
        2,
    ),
    # Grills
    ItemSpec(
        "Lamb Chops",
        "Grills",
        950,
        "Grilled lamb chops with rice.",
        {"Lamb Chops (raw)": 0.25, "Rice": 0.08, "Butter": 0.01},
        2,
    ),
    ItemSpec(
        "Grilled Meatballs",
        "Grills",
        480,
        "Homemade meatballs, rice and bean salad.",
        {"Ground Beef": 0.2, "Rice": 0.08, "Onion": 0.03},
        4,
    ),
    ItemSpec(
        "Cheese-Stuffed Meatballs",
        "Grills",
        520,
        "Meatballs stuffed with cheese.",
        {"Ground Beef": 0.2, "Kashar Cheese": 0.04, "Rice": 0.08},
        2,
    ),
    # Flatbreads
    ItemSpec(
        "Lahmacun",
        "Flatbreads",
        160,
        "Thin dough, ground meat topping. Served with greens and lemon.",
        {
            "Lahmacun Dough": 1,
            "Ground Beef": 0.05,
            "Tomato": 0.03,
            "Onion": 0.02,
            "Parsley": 0.1,
            "Lemon": 0.02,
        },
        9,
        ["Spice Level"],
    ),
    ItemSpec(
        "Minced Meat Pide",
        "Flatbreads",
        380,
        "Stone-oven pide with minced meat.",
        {"Pide Dough": 1, "Ground Beef": 0.12, "Tomato": 0.03},
        4,
        ["Pide Extras"],
    ),
    ItemSpec(
        "Cheese Pide",
        "Flatbreads",
        340,
        "Pide loaded with cheese.",
        {"Pide Dough": 1, "Kashar Cheese": 0.12},
        3,
        ["Pide Extras"],
    ),
    ItemSpec(
        "Diced Lamb Pide",
        "Flatbreads",
        450,
        "Pide with diced lamb.",
        {"Pide Dough": 1, "Lamb Meat": 0.12, "Tomato": 0.03},
        3,
        ["Pide Extras"],
    ),
    ItemSpec(
        "Mixed Pide",
        "Flatbreads",
        460,
        "Minced meat, cheese and egg.",
        {"Pide Dough": 1, "Ground Beef": 0.06, "Kashar Cheese": 0.08, "Egg": 1},
        3,
        ["Pide Extras"],
    ),
    # Salads
    ItemSpec(
        "Shepherd's Salad",
        "Salads",
        150,
        "Tomato, cucumber, pepper, onion, parsley.",
        {"Tomato": 0.2, "Green Pepper": 0.05, "Onion": 0.05, "Parsley": 0.2},
        5,
    ),
    ItemSpec(
        "Gavurdagi Salad",
        "Salads",
        190,
        "With walnuts and pomegranate sauce.",
        {"Tomato": 0.2, "Green Pepper": 0.05, "Onion": 0.05, "Parsley": 0.2},
        3,
    ),
    # Desserts
    ItemSpec("Kunefe", "Desserts", 280, "Hatay style, served hot.", {"Kunefe (ready-made)": 1}, 6),
    ItemSpec(
        "Pistachio Baklava",
        "Desserts",
        340,
        "4 pieces, with Antep pistachio.",
        {"Pistachio Baklava (bulk)": 0.12},
        4,
    ),
    ItemSpec(
        "Rice Pudding", "Desserts", 160, "Baked rice pudding.", {"Rice Pudding (ready-made)": 1}, 3
    ),
    # Beverages
    ItemSpec("Ayran", "Beverages", 50, "Churned yogurt drink.", {"Ayran": 1}, 10, ["Size"]),
    ItemSpec("Cola", "Beverages", 80, "330 ml can.", {"Cola": 1}, 5),
    ItemSpec("Water", "Beverages", 25, "500 ml.", {"Water": 1}, 4),
    ItemSpec("Turnip Juice", "Beverages", 60, "Spicy or mild.", {"Turnip Juice": 1}, 4),
    ItemSpec("Soda", "Beverages", 50, "200 ml.", {"Soda": 1}, 2),
    ItemSpec("Lemonade", "Beverages", 90, "Homemade, with fresh mint.", {"Lemon": 0.1}, 2),
    ItemSpec("Tea", "Beverages", 30, "Served in a slim glass.", {"Tea": 0.005}, 6),
    ItemSpec(
        "Turkish Coffee",
        "Beverages",
        90,
        "Served with Turkish delight.",
        {"Turkish Coffee": 0.008},
        2,
    ),
]

MAINS = {"Kebabs", "Grills", "Flatbreads"}
COLD_DRINKS = {"Ayran", "Cola", "Water", "Turnip Juice", "Soda", "Lemonade"}
VOID_REASONS = [
    "Customer changed their mind",
    "Wrong order entered",
    "Long wait time",
    "Item not liked",
]
CANCEL_REASONS = ["Customer cancelled the order", "Courier not found", "Duplicate order"]
DISCOUNT_REASONS = [
    ("Staff discount", D("0.20")),
    ("Loyalty discount", D("0.10")),
    ("Online campaign", D("0.15")),
]

WEEKDAY_FACTOR = [0.80, 0.85, 0.90, 0.95, 1.15, 1.40, 1.30]  # Mon..Sun
# Relative share of orders opened in each hour (11:00-22:59)
HOUR_WEIGHTS = {
    11: 3,
    12: 10,
    13: 11,
    14: 6,
    15: 3,
    16: 3,
    17: 4,
    18: 7,
    19: 11,
    20: 11,
    21: 7,
    22: 3,
}
HOLIDAYS = {(10, 29): 1.30}  # Republic Day (Turkey)

# Order method mix and, per method, the payment method mix (meal vouchers only make
# sense at the counter; delivery leans on cards and mobile wallets).
ORDER_METHOD_WEIGHTS = {"dineIn": 65, "pickup": 15, "delivery": 20}
PAYMENT_WEIGHTS = {
    OrderChannel.dineIn: {
        "cash": 30,
        "credit_card": 55,
        "meal_voucher": 10,
        "apple_pay": 3,
        "google_pay": 2,
    },
    OrderChannel.pickup: {
        "cash": 40,
        "credit_card": 45,
        "meal_voucher": 5,
        "apple_pay": 5,
        "google_pay": 5,
    },
    OrderChannel.delivery: {
        "cash": 10,
        "credit_card": 35,
        "meal_voucher": 0,
        "apple_pay": 30,
        "google_pay": 25,
    },
}


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def at(day: date, hour: int, minute: int = 0, second: int = 0) -> datetime:
    """A timezone-aware timestamp in the restaurant's local time."""
    return datetime.combine(day, time(hour, minute, second), tzinfo=RESTAURANT_TZ)


def warmth(day: date) -> float:
    """1.0 = peak summer, 0.0 = winter. Rough curve for Turkey."""
    return {
        1: 0.0,
        2: 0.05,
        3: 0.2,
        4: 0.4,
        5: 0.65,
        6: 0.85,
        7: 1.0,
        8: 1.0,
        9: 0.75,
        10: 0.45,
        11: 0.2,
        12: 0.05,
    }[day.month]


def old_price(price: Decimal) -> Decimal:
    """Price before the increase, rounded to the nearest 5."""
    raw = price / PRICE_INCREASE_RATE
    return (raw / 5).quantize(D("1"), rounding=ROUND_HALF_UP) * 5


@dataclass
class Ctx:
    rng: random.Random
    items: dict[str, MenuItem]
    specs: dict[str, ItemSpec]
    modifiers: dict[str, list[Modifier]]  # group name -> modifiers
    waiters: list[Staff]
    cashier: Staff
    tables: list[DiningTable]
    registered_users: list[User]
    days: int = DAYS


def weighted_pick(rng: random.Random, options: dict[str, float]) -> str:
    names = list(options)
    return rng.choices(names, weights=[options[n] for n in names])[0]


def item_weights(ctx: Ctx, categories: set[str], day: date, day_index: int) -> dict[str, float]:
    w = warmth(day)
    out = {}
    for name, spec in ctx.specs.items():
        if spec.category not in categories:
            continue
        weight = spec.weight
        if name in COLD_DRINKS:
            weight *= 0.6 + 0.8 * w
        if name == "Tea":
            weight *= 0.4 + 1.6 * (1 - w)
        if name == "Beyti Kebab":  # rising star: x1 -> x3 over the period
            weight *= 1 + 2 * day_index / ctx.days
        out[name] = weight
    return out


def choose_modifiers(ctx: Ctx, spec: ItemSpec) -> list[Modifier]:
    rng = ctx.rng
    chosen: list[Modifier] = []
    for group in spec.groups:
        mods = {m.name: m for m in ctx.modifiers[group]}
        if group == "Spice Level":
            chosen.append(mods[weighted_pick(rng, {"Spicy": 55, "Mild": 25, "Not Spicy": 20})])
        elif group == "Portion" and rng.random() < 0.12:
            chosen.append(mods["1.5 Portion"])
        elif group == "Pide Extras":
            if rng.random() < 0.15:
                chosen.append(mods["Extra Cheese"])
            if rng.random() < 0.05:
                chosen.append(mods["Extra Egg"])
        elif group == "Size" and rng.random() < 0.3:
            chosen.append(mods["Large"])
    return chosen


def build_basket(ctx: Ctx, channel: OrderChannel, day: date, day_index: int) -> list[tuple]:
    """Return a list of (item_name, quantity, [modifiers])."""
    rng = ctx.rng
    w = warmth(day)
    if channel == OrderChannel.dineIn:
        guests = rng.choice([1, 2, 2, 2, 3, 4, 4, 5, 6])
    elif channel == OrderChannel.pickup:
        guests = rng.choice([1, 1, 2, 3])
    else:
        guests = rng.choice([1, 2, 2, 3, 4])

    lines: list[tuple] = []
    mains = item_weights(ctx, MAINS, day, day_index)
    drinks = item_weights(ctx, {"Beverages"}, day, day_index)
    cold = {k: v for k, v in drinks.items() if k in COLD_DRINKS}

    soup_p = 0.15 + 0.35 * (1 - w)
    for _ in range(guests):
        main = weighted_pick(rng, mains)
        qty = rng.choice([2, 2, 3]) if main == "Lahmacun" else 1
        lines.append((main, qty, choose_modifiers(ctx, ctx.specs[main])))
        if rng.random() < 0.6 + 0.3 * w:  # fewer cold drinks as the weather cools
            drink = weighted_pick(rng, cold)
            lines.append((drink, 1, choose_modifiers(ctx, ctx.specs[drink])))
        if rng.random() < soup_p:
            lines.append((weighted_pick(rng, item_weights(ctx, {"Soups"}, day, day_index)), 1, []))
        dessert_p = 0.35 if channel == OrderChannel.dineIn else 0.15
        if rng.random() < dessert_p:
            lines.append(
                (weighted_pick(rng, item_weights(ctx, {"Desserts"}, day, day_index)), 1, [])
            )
        if channel == OrderChannel.dineIn:
            if rng.random() < 0.35 + 0.4 * (1 - w):
                lines.append(("Tea", rng.choice([1, 1, 2]), []))
            elif rng.random() < 0.1:
                lines.append(("Turkish Coffee", 1, []))

    if channel == OrderChannel.dineIn:
        if rng.random() < 0.5:
            for _ in range(rng.choice([1, 1, 2])):
                lines.append(
                    (weighted_pick(rng, item_weights(ctx, {"Starters"}, day, day_index)), 1, [])
                )
        if rng.random() < 0.45:
            lines.append((weighted_pick(rng, item_weights(ctx, {"Salads"}, day, day_index)), 1, []))

    # Merge identical lines (same item + same modifiers)
    merged: dict[tuple, list] = {}
    for name, qty, mods in lines:
        key = (name, tuple(sorted(m.name for m in mods)))
        if key in merged:
            merged[key][1] += qty
        else:
            merged[key] = [name, qty, mods]
    return [tuple(v) for v in merged.values()]


# --------------------------------------------------------------------------- #
# Seeding steps
# --------------------------------------------------------------------------- #


def seed_reference_data(session: Session, now: datetime) -> Ctx:
    rng = random.Random(SEED)

    staff = [Staff(name=n, role=r) for n, r in STAFF]
    session.add_all(staff)

    tables = [DiningTable(name=n, area=a, capacity=c) for n, a, c in TABLES]
    session.add_all(tables)

    registered_users = [
        User(
            type=UserType.registered,
            name=f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}",
            email=None,
            created_at=now - timedelta(days=rng.randint(30, 700)),
        )
        for _ in range(N_REGISTERED_USERS)
    ]
    session.add_all(registered_users)
    session.flush()  # need their ids below
    for i, u in enumerate(registered_users, start=1):
        u.email = f"{u.name.split()[0].lower()}.{u.name.split()[1].lower()}{i}@example.com"

    categories = {name: Category(name=name, sort_order=i) for i, name in enumerate(CATEGORIES)}
    session.add_all(categories.values())

    ingredients = {
        name: Ingredient(name=name, unit=u, unit_cost=D(c)) for name, (u, c) in INGREDIENTS.items()
    }
    session.add_all(ingredients.values())

    groups: dict[str, ModifierGroup] = {}
    modifiers: dict[str, list[Modifier]] = {}
    for gname, (mn, mx, mods) in MODIFIER_GROUPS.items():
        g = ModifierGroup(name=gname, min_select=mn, max_select=mx)
        g.modifiers = [Modifier(name=m, price_delta=D(p)) for m, p in mods]
        groups[gname] = g
        modifiers[gname] = g.modifiers
    session.add_all(groups.values())

    items: dict[str, MenuItem] = {}
    for spec in MENU:
        item = MenuItem(
            name=spec.name,
            description=spec.description,
            price=D(spec.price),
            category=categories[spec.category],
        )
        item.modifier_groups = [groups[g] for g in spec.groups]
        item.recipe = [
            RecipeItem(ingredient=ingredients[ing], quantity=q3(D(str(qty))))
            for ing, qty in spec.recipe.items()
        ]
        items[spec.name] = item
    session.add_all(items.values())
    session.flush()

    waiters = [s for s in staff if s.role == StaffRole.waiter]
    cashier = next(s for s in staff if s.role == StaffRole.cashier)
    return Ctx(
        rng=rng,
        items=items,
        specs={s.name: s for s in MENU},
        modifiers=modifiers,
        waiters=waiters,
        cashier=cashier,
        tables=tables,
        registered_users=registered_users,
    )


def _pick_user(ctx: Ctx, session: Session, opened_at: datetime) -> int:
    """70% of orders come from a reused registered user, 30% a one-off guest
    checkout (a fresh row, like a real guest checkout has no persistent identity)."""
    if ctx.rng.random() < 0.7:
        return ctx.rng.choice(ctx.registered_users).id
    guest = User(type=UserType.guest, name="Guest", email=None, created_at=opened_at)
    session.add(guest)
    session.flush()
    guest.name = f"Guest {guest.id}"
    return guest.id


def seed_orders(session: Session, ctx: Ctx, now: datetime) -> dict[date, dict[str, Decimal]]:
    """Create orders/items/payments. Returns daily ingredient consumption."""
    rng = ctx.rng
    today = now.date()
    start = today - timedelta(days=ctx.days - 1)
    price_change_day = today - timedelta(days=PRICE_INCREASE_DAYS_AGO)
    waiter_weights = [WAITER_WEIGHTS[w.name] for w in ctx.waiters]
    consumption: dict[date, dict[str, Decimal]] = defaultdict(lambda: defaultdict(D))
    open_tables: set[int] = set()

    for day_index in range(ctx.days):
        day = start + timedelta(days=day_index)
        factor = WEEKDAY_FACTOR[day.weekday()] * HOLIDAYS.get((day.month, day.day), 1.0)
        factor *= 1 + 0.08 * day_index / ctx.days  # gentle growth trend
        n_orders = round(BASE_ORDERS_PER_DAY * factor * rng.uniform(0.9, 1.1))

        hours = rng.choices(list(HOUR_WEIGHTS), weights=list(HOUR_WEIGHTS.values()), k=n_orders)
        for hour in sorted(hours):
            opened_at = at(day, hour, rng.randint(0, 59), rng.randint(0, 59))
            if opened_at > now:
                continue

            channel = OrderChannel(weighted_pick(rng, ORDER_METHOD_WEIGHTS))
            minutes_open = {
                OrderChannel.dineIn: (35, 90),
                OrderChannel.pickup: (5, 15),
                OrderChannel.delivery: (25, 50),
            }[channel]
            closed_at = opened_at + timedelta(minutes=rng.randint(*minutes_open))
            still_open = closed_at > now

            table = None
            if channel == OrderChannel.dineIn:
                candidates = (
                    [t for t in ctx.tables if t.id not in open_tables] if still_open else ctx.tables
                )
                if not candidates:
                    continue
                table = rng.choice(candidates)
                staff = rng.choices(ctx.waiters, weights=waiter_weights)[0]
            else:
                staff = ctx.cashier

            order = Order(
                channel=channel,
                opened_at=opened_at,
                table_id=table.id if table else None,
                staff_id=staff.id,
                user_id=_pick_user(ctx, session, opened_at),
            )

            subtotal = D("0")
            items: list[OrderItem] = []
            for name, qty, mods in build_basket(ctx, channel, day, day_index):
                menu_item = ctx.items[name]
                base = menu_item.price if day >= price_change_day else old_price(menu_item.price)
                unit_price = base + sum((m.price_delta for m in mods), D("0"))
                oi = OrderItem(
                    menu_item_id=menu_item.id,
                    quantity=qty,
                    unit_price=unit_price,
                    modifiers=", ".join(m.name for m in mods),
                )
                if not still_open and rng.random() < 0.015:
                    oi.status = OrderItemStatus.void
                    oi.void_reason = rng.choice(VOID_REASONS)
                else:
                    subtotal += unit_price * qty
                items.append(oi)
            order.items = items

            if still_open:
                order.status = OrderStatus.open
                if table:
                    open_tables.add(table.id)
            elif rng.random() < 0.015:
                order.status = OrderStatus.cancelled
                order.closed_at = closed_at
                order.discount_reason = None
                for oi in items:
                    oi.status = OrderItemStatus.void
                    oi.void_reason = rng.choice(CANCEL_REASONS)
                subtotal = D("0")
            else:
                order.status = OrderStatus.paid
                order.closed_at = closed_at

            order.subtotal = q2(subtotal)
            if order.status == OrderStatus.paid and rng.random() < 0.06:
                if channel == OrderChannel.delivery:
                    reason, rate = DISCOUNT_REASONS[2]
                else:
                    reason, rate = rng.choice(DISCOUNT_REASONS[:2])
                order.discount = q2(subtotal * rate)
                order.discount_reason = reason
            order.total = order.subtotal - order.discount

            if order.status == OrderStatus.paid:
                order.payments = make_payments(rng, channel, order.total, closed_at)

            # Consumption: everything that was actually prepared (non-void, non-cancelled)
            if order.status != OrderStatus.cancelled:
                for oi, (name, _, mods) in zip(items, build_lines_cache(items, ctx)):
                    if oi.status == OrderItemStatus.void:
                        continue
                    mult = portion_multiplier(m.name for m in mods)
                    for ing, per_portion in ctx.specs[name].recipe.items():
                        consumption[day][ing] += line_consumption(
                            D(str(per_portion)), oi.quantity, mult, INGREDIENTS[ing][0]
                        )

            session.add(order)

        session.flush()

    for t in ctx.tables:
        if t.id in open_tables:
            t.status = TableStatus.occupied
    free = [t for t in ctx.tables if t.status == TableStatus.free]
    for t in rng.sample(free, k=min(2, len(free))):
        t.status = TableStatus.reserved

    return consumption


def build_lines_cache(items: list[OrderItem], ctx: Ctx) -> list[tuple]:
    """Map OrderItems back to (name, qty, modifiers) for consumption."""
    by_id = {i.id: n for n, i in ctx.items.items()}
    mods_by_name = {m.name: m for group in ctx.modifiers.values() for m in group}
    out = []
    for oi in items:
        mods = [mods_by_name[n] for n in oi.modifiers.split(", ") if n]
        out.append((by_id[oi.menu_item_id], oi.quantity, mods))
    return out


def make_payments(
    rng: random.Random, channel: OrderChannel, total: Decimal, paid_at: datetime
) -> list[Payment]:
    method = PaymentMethod(weighted_pick(rng, PAYMENT_WEIGHTS[channel]))
    if (
        channel == OrderChannel.dineIn
        and total > 400
        and method == PaymentMethod.credit_card
        and rng.random() < 0.08
    ):
        cash_part = q2(total * D(str(round(rng.uniform(0.3, 0.6), 2))))
        return [
            Payment(method=PaymentMethod.cash, amount=cash_part, paid_at=paid_at),
            Payment(method=PaymentMethod.credit_card, amount=total - cash_part, paid_at=paid_at),
        ]
    return [Payment(method=method, amount=total, paid_at=paid_at)]


def seed_stock(
    session: Session, ctx: Ctx, consumption: dict[date, dict[str, Decimal]], now: datetime
) -> None:
    """Simulate the stock ledger: opening stock, daily sales, purchases and waste."""
    rng = ctx.rng
    ingredients = {i.name: i for i in session.exec(select(Ingredient)).all()}
    days = sorted(consumption)
    today = now.date()
    delay_start = today - timedelta(days=SUPPLIER_DELAY_DAYS - 1)
    perishables = {"Tomato", "Parsley", "Green Pepper", "Eggplant", "Lemon"}

    for name, ing in ingredients.items():
        daily = [consumption[d].get(name, D("0")) for d in days]
        avg = sum(daily, D("0")) / len(daily)
        precision = D("1") if ing.unit in ("piece", "bunch") else D("0.5")
        ing.reorder_level = max(precision, (avg * 2 / precision).quantize(D("1")) * precision)
        target = max(precision, (avg * 6 / precision).quantize(D("1")) * precision)

        stock = target
        first_day = days[0]
        session.add(
            StockMovement(
                ingredient_id=ing.id,
                change=q3(stock),
                reason=StockReason.adjustment,
                note="Opening count",
                created_at=at(first_day, 8, 0),
            )
        )
        for d, used in zip(days, daily):
            # Morning delivery if today's expected usage would push stock below reorder level
            if d != first_day and stock - avg < ing.reorder_level:
                delayed = name in DELAYED_INGREDIENTS and d >= delay_start
                if not delayed:
                    qty = target - stock
                    stock += qty
                    session.add(
                        StockMovement(
                            ingredient_id=ing.id,
                            change=q3(qty),
                            reason=StockReason.purchase,
                            note="Supplier delivery",
                            created_at=at(d, 9, 0),
                        )
                    )
            if name in DELAYED_INGREDIENTS and d >= delay_start and stock - used < avg * D("0.4"):
                # Supplier is late: only a small emergency purchase from the market
                qty = q3(max(used, avg * D("0.6")) - (stock - used))
                if ing.unit in COUNT_UNITS:
                    qty = qty.to_integral_value(rounding=ROUND_CEILING)
                if qty > 0:
                    stock += qty
                    session.add(
                        StockMovement(
                            ingredient_id=ing.id,
                            change=qty,
                            reason=StockReason.purchase,
                            note="Emergency purchase (supplier delay)",
                            created_at=at(d, 12, 0),
                        )
                    )
            if used:
                stock -= used
                ts = now if d == today else at(d, 23, 59)
                session.add(
                    StockMovement(
                        ingredient_id=ing.id,
                        change=q3(-used),
                        reason=StockReason.sale,
                        note="Daily sales consumption",
                        created_at=ts,
                    )
                )
            if name in perishables and d.weekday() == 0 and d != today:
                waste = q3(min(stock, avg * D(str(round(rng.uniform(0.1, 0.3), 2)))))
                if waste > 0:
                    stock -= waste
                    session.add(
                        StockMovement(
                            ingredient_id=ing.id,
                            change=-waste,
                            reason=StockReason.waste,
                            note="Weekly spoilage",
                            created_at=at(d, 23, 30),
                        )
                    )
        ing.stock_qty = q3(stock)


def seed(
    reset: bool = False,
    now: datetime | None = None,
    days: int = DAYS,
    db_engine: Engine | None = None,
    verbose: bool = True,
) -> None:
    now = now or datetime.now(RESTAURANT_TZ).replace(microsecond=0)
    db_engine = db_engine or engine
    if reset:
        drop_db_and_tables(db_engine)
    create_db_and_tables(db_engine)

    with Session(db_engine) as session:
        if session.exec(select(Category)).first():
            if verbose:
                print("Database already seeded. Use --reset to reseed.")
            return
        ctx = seed_reference_data(session, now)
        ctx.days = days
        consumption = seed_orders(session, ctx, now)
        seed_stock(session, ctx, consumption, now)
        session.commit()

        if verbose:
            n_orders = len(session.exec(select(Order.id)).all())
            n_users = len(session.exec(select(User.id)).all())
            low = session.exec(
                select(Ingredient).where(Ingredient.stock_qty < Ingredient.reorder_level)
            ).all()
            print(
                f"Seeded {len(MENU)} menu items, {len(TABLES)} tables, {n_users} users, "
                f"{n_orders} orders over {days} days (until {now:%Y-%m-%d %H:%M})."
            )
            print("Below reorder level:", ", ".join(i.name for i in low) or "none")


def ensure_demo_data(
    db_engine: Engine | None = None,
    days: int = DAYS,
    max_age_days: int = 1,
    now: datetime | None = None,
) -> str:
    """Make sure the demo database exists and is recent.

    Seeds an empty database, and regenerates one whose newest order is older than
    `max_age_days` so that "today" always has data when someone tries the project.
    Set POS_DEMO_REFRESH=0 to keep an old database untouched.
    Returns "seeded", "refreshed" or "fresh".
    """
    now = now or datetime.now(RESTAURANT_TZ).replace(microsecond=0)
    db_engine = db_engine or engine
    create_db_and_tables(db_engine)
    with Session(db_engine) as session:
        newest = session.exec(select(Order.opened_at).order_by(Order.opened_at.desc())).first()
    if newest is None:
        seed(days=days, db_engine=db_engine, now=now, verbose=False)
        return "seeded"
    if newest.tzinfo is None:
        newest = newest.replace(tzinfo=UTC)
    stale = now - newest > timedelta(days=max_age_days)
    if stale and os.getenv("POS_DEMO_REFRESH", "1") != "0":
        seed(reset=True, days=days, db_engine=db_engine, now=now, verbose=False)
        return "refreshed"
    return "fresh"


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the mock restaurant POS database.")
    parser.add_argument("--reset", action="store_true", help="Drop all tables and reseed.")
    parser.add_argument("--days", type=int, default=DAYS, help="Days of history to generate.")
    args = parser.parse_args()
    seed(reset=args.reset, days=args.days)


if __name__ == "__main__":
    main()
