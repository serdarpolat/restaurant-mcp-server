"""Generate a realistic, reproducible dataset for a Turkish kebab restaurant.

The data is synthetic but follows real-world patterns so that analytical
questions have meaningful answers:

- Lunch (12-14) and dinner (19-21) peaks; busier Fridays and weekends.
- Seasonality: cold drinks fade and soups/tea rise as summer turns to autumn.
- A menu-wide price increase ~45 days ago (historical prices are preserved).
- "Beyti" is a rising star; one waiter consistently outsells the others.
- A public holiday (Oct 29) with a traffic spike.
- ~1.5% voided items and ~1.5% cancelled orders, with reasons.
- A full stock ledger (daily sales, purchases, waste). A few ingredients end
  below their reorder level because of a supplier delay in the last days.
- Today's data stops at the current time, with a few tables still open.

Usage:
    python -m pos_api.db.seed            # create tables + seed (if empty)
    python -m pos_api.db.seed --reset    # drop everything and reseed
"""

from __future__ import annotations

import argparse
import random
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

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
)

SEED = 42
DAYS = 90
BASE_ORDERS_PER_DAY = 95
PRICE_INCREASE_DAYS_AGO = 45
PRICE_INCREASE_RATE = Decimal("1.08")
SUPPLIER_DELAY_DAYS = 5
DELAYED_INGREDIENTS = {"Dana Kıyma", "Lavaş", "Patlıcan"}

D = Decimal


def q2(value: Decimal) -> Decimal:
    return value.quantize(D("0.01"), rounding=ROUND_HALF_UP)


def q3(value: Decimal) -> Decimal:
    return value.quantize(D("0.001"), rounding=ROUND_HALF_UP)


# --------------------------------------------------------------------------- #
# Static reference data
# --------------------------------------------------------------------------- #

STAFF = [
    ("Mehmet Yılmaz", StaffRole.manager),
    ("Ayşe Demir", StaffRole.cashier),
    ("Emre Kaya", StaffRole.waiter),
    ("Zeynep Çelik", StaffRole.waiter),
    ("Burak Şahin", StaffRole.waiter),
    ("Elif Arslan", StaffRole.waiter),
    ("Can Öztürk", StaffRole.waiter),
    ("Selin Aydın", StaffRole.waiter),
]
# Relative share of tables each waiter serves (Emre is the star performer).
WAITER_WEIGHTS = {
    "Emre Kaya": 1.6,
    "Zeynep Çelik": 1.2,
    "Burak Şahin": 1.0,
    "Elif Arslan": 1.0,
    "Can Öztürk": 0.8,
    "Selin Aydın": 0.9,
}

TABLES = (
    [(f"Salon {i}", "Salon", c) for i, c in enumerate([2, 2, 4, 4, 4, 6, 6, 8], start=1)]
    + [(f"Bahçe {i}", "Bahçe", c) for i, c in enumerate([2, 4, 4, 4, 6], start=1)]
    + [(f"Teras {i}", "Teras", c) for i, c in enumerate([4, 6], start=1)]
)

# name: (unit, unit_cost)
INGREDIENTS = {
    "Dana Kıyma": ("kg", 650),
    "Kuzu Eti": ("kg", 900),
    "Kuzu Pirzola": ("kg", 1400),
    "Tavuk But": ("kg", 280),
    "Lavaş": ("adet", 6),
    "Pide Hamuru": ("adet", 12),
    "Lahmacun Hamuru": ("adet", 8),
    "Kaşar Peyniri": ("kg", 450),
    "Yumurta": ("adet", 6),
    "Kırmızı Mercimek": ("kg", 90),
    "Bulgur": ("kg", 50),
    "Pirinç": ("kg", 70),
    "Domates": ("kg", 40),
    "Soğan": ("kg", 25),
    "Sivri Biber": ("kg", 60),
    "Patlıcan": ("kg", 50),
    "Maydanoz": ("demet", 15),
    "Limon": ("kg", 60),
    "Yoğurt": ("kg", 90),
    "Tereyağı": ("kg", 600),
    "Künefe (hazır)": ("adet", 90),
    "Fıstıklı Baklava": ("kg", 1000),
    "Sütlaç (hazır)": ("adet", 40),
    "Ayran": ("adet", 15),
    "Kola": ("adet", 30),
    "Su": ("adet", 6),
    "Şalgam": ("adet", 25),
    "Soda": ("adet", 18),
    "Çay": ("kg", 400),
    "Türk Kahvesi": ("kg", 900),
}

CATEGORIES = [
    "Çorbalar",
    "Başlangıçlar",
    "Kebaplar",
    "Izgaralar",
    "Pide & Lahmacun",
    "Salatalar",
    "Tatlılar",
    "İçecekler",
]

# Modifier groups: name -> (min, max, [(modifier, price_delta)])
MODIFIER_GROUPS = {
    "Acı Seviyesi": (1, 1, [("Acılı", 0), ("Az Acılı", 0), ("Acısız", 0)]),
    "Porsiyon": (0, 1, [("1.5 Porsiyon", 250)]),
    "Pide Ekstraları": (0, 2, [("Ekstra Kaşar", 60), ("Ekstra Yumurta", 30)]),
    "Boy": (0, 1, [("Büyük Boy", 20)]),
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


KEBAB_GROUPS = ["Acı Seviyesi", "Porsiyon"]

MENU: list[ItemSpec] = [
    # Çorbalar
    ItemSpec(
        "Mercimek Çorbası",
        "Çorbalar",
        150,
        "Tereyağlı, limonla servis edilir.",
        {"Kırmızı Mercimek": 0.06, "Soğan": 0.02, "Tereyağı": 0.01, "Limon": 0.02},
        6,
    ),
    ItemSpec(
        "Ezogelin Çorbası",
        "Çorbalar",
        150,
        "Bulgurlu, naneli geleneksel çorba.",
        {"Kırmızı Mercimek": 0.05, "Bulgur": 0.02, "Soğan": 0.02},
        3,
    ),
    ItemSpec(
        "Yayla Çorbası",
        "Çorbalar",
        160,
        "Yoğurtlu, pirinçli, naneli.",
        {"Yoğurt": 0.1, "Pirinç": 0.02, "Tereyağı": 0.01},
        2,
    ),
    # Başlangıçlar
    ItemSpec("Haydari", "Başlangıçlar", 140, "Süzme yoğurt, sarımsak, nane.", {"Yoğurt": 0.15}, 3),
    ItemSpec(
        "Acılı Ezme",
        "Başlangıçlar",
        130,
        "İnce kıyılmış domates, biber ve soğan.",
        {"Domates": 0.1, "Sivri Biber": 0.03, "Soğan": 0.03, "Maydanoz": 0.1},
        5,
    ),
    ItemSpec(
        "İçli Köfte",
        "Başlangıçlar",
        90,
        "Adet fiyatıdır.",
        {"Dana Kıyma": 0.03, "Bulgur": 0.05, "Soğan": 0.01},
        3,
    ),
    # Kebaplar
    ItemSpec(
        "Adana Kebap",
        "Kebaplar",
        560,
        "Acılı zırh kıyması, lavaş, közlenmiş domates-biber.",
        {"Dana Kıyma": 0.2, "Lavaş": 1, "Domates": 0.05, "Sivri Biber": 0.03, "Soğan": 0.05},
        10,
        KEBAB_GROUPS,
    ),
    ItemSpec(
        "Urfa Kebap",
        "Kebaplar",
        560,
        "Acısız zırh kıyması, lavaş, közlenmiş sebzeler.",
        {"Dana Kıyma": 0.2, "Lavaş": 1, "Domates": 0.05, "Sivri Biber": 0.03, "Soğan": 0.05},
        5,
        ["Porsiyon"],
    ),
    ItemSpec(
        "Beyti",
        "Kebaplar",
        640,
        "Lavaşa sarılı kebap, yoğurt ve tereyağı ile.",
        {"Dana Kıyma": 0.2, "Lavaş": 2, "Yoğurt": 0.1, "Tereyağı": 0.02},
        4,
        KEBAB_GROUPS,
    ),
    ItemSpec(
        "İskender",
        "Kebaplar",
        620,
        "Pide üzerinde kuzu, domates sos, yoğurt, tereyağı.",
        {"Kuzu Eti": 0.2, "Pide Hamuru": 0.5, "Yoğurt": 0.1, "Tereyağı": 0.03, "Domates": 0.05},
        6,
        ["Porsiyon"],
    ),
    ItemSpec(
        "Patlıcan Kebabı",
        "Kebaplar",
        600,
        "Patlıcan ve kıyma şişte, lavaş ile.",
        {"Dana Kıyma": 0.18, "Patlıcan": 0.25, "Lavaş": 1, "Domates": 0.05},
        2,
        KEBAB_GROUPS,
    ),
    ItemSpec(
        "Ali Nazik",
        "Kebaplar",
        650,
        "Közlenmiş patlıcanlı yoğurt üzerinde kuzu.",
        {"Kuzu Eti": 0.18, "Patlıcan": 0.2, "Yoğurt": 0.1, "Tereyağı": 0.02},
        2,
    ),
    ItemSpec(
        "Kuzu Şiş",
        "Kebaplar",
        720,
        "Marine edilmiş kuzu kuşbaşı.",
        {"Kuzu Eti": 0.22, "Lavaş": 1, "Domates": 0.05, "Sivri Biber": 0.03},
        3,
        ["Porsiyon"],
    ),
    ItemSpec(
        "Tavuk Şiş",
        "Kebaplar",
        420,
        "Yoğurtlu marine tavuk but.",
        {"Tavuk But": 0.22, "Lavaş": 1, "Domates": 0.05, "Sivri Biber": 0.03},
        6,
        ["Porsiyon"],
    ),
    ItemSpec(
        "Tavuk Kanat",
        "Kebaplar",
        400,
        "Közde baharatlı kanat.",
        {"Tavuk But": 0.3, "Lavaş": 1},
        4,
        KEBAB_GROUPS,
    ),
    ItemSpec(
        "Karışık Izgara",
        "Kebaplar",
        950,
        "Adana, kuzu şiş, tavuk şiş bir arada.",
        {"Dana Kıyma": 0.1, "Kuzu Eti": 0.1, "Tavuk But": 0.1, "Lavaş": 1, "Domates": 0.05},
        2,
    ),
    # Izgaralar
    ItemSpec(
        "Kuzu Pirzola",
        "Izgaralar",
        950,
        "Közde kuzu pirzola, pilav ile.",
        {"Kuzu Pirzola": 0.25, "Pirinç": 0.08, "Tereyağı": 0.01},
        2,
    ),
    ItemSpec(
        "Izgara Köfte",
        "Izgaralar",
        480,
        "Ev yapımı köfte, piyaz ve pilav ile.",
        {"Dana Kıyma": 0.2, "Pirinç": 0.08, "Soğan": 0.03},
        4,
    ),
    ItemSpec(
        "Kaşarlı Köfte",
        "Izgaralar",
        520,
        "İçi kaşar dolgulu köfte.",
        {"Dana Kıyma": 0.2, "Kaşar Peyniri": 0.04, "Pirinç": 0.08},
        2,
    ),
    # Pide & Lahmacun
    ItemSpec(
        "Lahmacun",
        "Pide & Lahmacun",
        160,
        "İnce hamur, kıymalı harç. Yeşillik ve limonla.",
        {
            "Lahmacun Hamuru": 1,
            "Dana Kıyma": 0.05,
            "Domates": 0.03,
            "Soğan": 0.02,
            "Maydanoz": 0.1,
            "Limon": 0.02,
        },
        9,
        ["Acı Seviyesi"],
    ),
    ItemSpec(
        "Kıymalı Pide",
        "Pide & Lahmacun",
        380,
        "Taş fırında kıymalı pide.",
        {"Pide Hamuru": 1, "Dana Kıyma": 0.12, "Domates": 0.03},
        4,
        ["Pide Ekstraları"],
    ),
    ItemSpec(
        "Kaşarlı Pide",
        "Pide & Lahmacun",
        340,
        "Bol kaşarlı pide.",
        {"Pide Hamuru": 1, "Kaşar Peyniri": 0.12},
        3,
        ["Pide Ekstraları"],
    ),
    ItemSpec(
        "Kuşbaşılı Pide",
        "Pide & Lahmacun",
        450,
        "Kuzu kuşbaşılı pide.",
        {"Pide Hamuru": 1, "Kuzu Eti": 0.12, "Domates": 0.03},
        3,
        ["Pide Ekstraları"],
    ),
    ItemSpec(
        "Karışık Pide",
        "Pide & Lahmacun",
        460,
        "Kıyma, kaşar ve yumurta.",
        {"Pide Hamuru": 1, "Dana Kıyma": 0.06, "Kaşar Peyniri": 0.08, "Yumurta": 1},
        3,
        ["Pide Ekstraları"],
    ),
    # Salatalar
    ItemSpec(
        "Çoban Salata",
        "Salatalar",
        150,
        "Domates, salatalık, biber, soğan, maydanoz.",
        {"Domates": 0.2, "Sivri Biber": 0.05, "Soğan": 0.05, "Maydanoz": 0.2},
        5,
    ),
    ItemSpec(
        "Gavurdağı Salata",
        "Salatalar",
        190,
        "Cevizli, nar ekşili.",
        {"Domates": 0.2, "Sivri Biber": 0.05, "Soğan": 0.05, "Maydanoz": 0.2},
        3,
    ),
    # Tatlılar
    ItemSpec("Künefe", "Tatlılar", 280, "Hatay usulü, sıcak servis.", {"Künefe (hazır)": 1}, 6),
    ItemSpec(
        "Fıstıklı Baklava",
        "Tatlılar",
        340,
        "4 dilim, Antep fıstıklı.",
        {"Fıstıklı Baklava": 0.12},
        4,
    ),
    ItemSpec("Sütlaç", "Tatlılar", 160, "Fırın sütlaç.", {"Sütlaç (hazır)": 1}, 3),
    # İçecekler
    ItemSpec("Ayran", "İçecekler", 50, "Yayık ayran.", {"Ayran": 1}, 10, ["Boy"]),
    ItemSpec("Kola", "İçecekler", 80, "330 ml kutu.", {"Kola": 1}, 5),
    ItemSpec("Su", "İçecekler", 25, "500 ml.", {"Su": 1}, 4),
    ItemSpec("Şalgam", "İçecekler", 60, "Acılı veya acısız.", {"Şalgam": 1}, 4),
    ItemSpec("Soda", "İçecekler", 50, "200 ml.", {"Soda": 1}, 2),
    ItemSpec("Limonata", "İçecekler", 90, "Ev yapımı, taze nane ile.", {"Limon": 0.1}, 2),
    ItemSpec("Çay", "İçecekler", 30, "İnce belli bardakta.", {"Çay": 0.005}, 6),
    ItemSpec("Türk Kahvesi", "İçecekler", 90, "Lokum ile.", {"Türk Kahvesi": 0.008}, 2),
]

MAINS = {"Kebaplar", "Izgaralar", "Pide & Lahmacun"}
COLD_DRINKS = {"Ayran", "Kola", "Su", "Şalgam", "Soda", "Limonata"}
VOID_REASONS = [
    "Müşteri vazgeçti",
    "Yanlış sipariş girildi",
    "Uzun bekleme süresi",
    "Ürün beğenilmedi",
]
CANCEL_REASONS = ["Müşteri siparişi iptal etti", "Kurye bulunamadı", "Mükerrer sipariş"]
DISCOUNT_REASONS = [
    ("Personel indirimi", D("0.20")),
    ("Sadakat indirimi", D("0.10")),
    ("Online kampanya", D("0.15")),
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
HOLIDAYS = {(10, 29): 1.30}  # Cumhuriyet Bayramı


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
    """Price before the increase, rounded to the nearest 5 TL."""
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
        if name == "Çay":
            weight *= 0.4 + 1.6 * (1 - w)
        if name == "Beyti":  # rising star: x1 -> x3 over the period
            weight *= 1 + 2 * day_index / ctx.days
        out[name] = weight
    return out


def choose_modifiers(ctx: Ctx, spec: ItemSpec) -> list[Modifier]:
    rng = ctx.rng
    chosen: list[Modifier] = []
    for group in spec.groups:
        mods = {m.name: m for m in ctx.modifiers[group]}
        if group == "Acı Seviyesi":
            chosen.append(mods[weighted_pick(rng, {"Acılı": 55, "Az Acılı": 25, "Acısız": 20})])
        elif group == "Porsiyon" and rng.random() < 0.12:
            chosen.append(mods["1.5 Porsiyon"])
        elif group == "Pide Ekstraları":
            if rng.random() < 0.15:
                chosen.append(mods["Ekstra Kaşar"])
            if rng.random() < 0.05:
                chosen.append(mods["Ekstra Yumurta"])
        elif group == "Boy" and rng.random() < 0.3:
            chosen.append(mods["Büyük Boy"])
    return chosen


def build_basket(ctx: Ctx, channel: OrderChannel, day: date, day_index: int) -> list[tuple]:
    """Return a list of (item_name, quantity, [modifiers])."""
    rng = ctx.rng
    w = warmth(day)
    if channel == OrderChannel.dine_in:
        guests = rng.choice([1, 2, 2, 2, 3, 4, 4, 5, 6])
    elif channel == OrderChannel.takeaway:
        guests = rng.choice([1, 1, 2, 3])
    else:
        guests = rng.choice([1, 2, 2, 3, 4])

    lines: list[tuple] = []
    mains = item_weights(ctx, MAINS, day, day_index)
    drinks = item_weights(ctx, {"İçecekler"}, day, day_index)
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
            lines.append(
                (weighted_pick(rng, item_weights(ctx, {"Çorbalar"}, day, day_index)), 1, [])
            )
        dessert_p = 0.35 if channel == OrderChannel.dine_in else 0.15
        if rng.random() < dessert_p:
            lines.append(
                (weighted_pick(rng, item_weights(ctx, {"Tatlılar"}, day, day_index)), 1, [])
            )
        if channel == OrderChannel.dine_in:
            if rng.random() < 0.35 + 0.4 * (1 - w):
                lines.append(("Çay", rng.choice([1, 1, 2]), []))
            elif rng.random() < 0.1:
                lines.append(("Türk Kahvesi", 1, []))

    if channel == OrderChannel.dine_in:
        if rng.random() < 0.5:
            for _ in range(rng.choice([1, 1, 2])):
                lines.append(
                    (weighted_pick(rng, item_weights(ctx, {"Başlangıçlar"}, day, day_index)), 1, [])
                )
        if rng.random() < 0.45:
            lines.append(
                (weighted_pick(rng, item_weights(ctx, {"Salatalar"}, day, day_index)), 1, [])
            )

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


def seed_reference_data(session: Session) -> Ctx:
    staff = [Staff(name=n, role=r) for n, r in STAFF]
    session.add_all(staff)

    tables = [DiningTable(name=n, area=a, capacity=c) for n, a, c in TABLES]
    session.add_all(tables)

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
        rng=random.Random(SEED),
        items=items,
        specs={s.name: s for s in MENU},
        modifiers=modifiers,
        waiters=waiters,
        cashier=cashier,
        tables=tables,
    )


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

            channel = OrderChannel(
                weighted_pick(rng, {"dine_in": 65, "takeaway": 15, "delivery": 20})
            )
            minutes_open = {
                OrderChannel.dine_in: (35, 90),
                OrderChannel.takeaway: (5, 15),
                OrderChannel.delivery: (25, 50),
            }[channel]
            closed_at = opened_at + timedelta(minutes=rng.randint(*minutes_open))
            still_open = closed_at > now

            table = None
            if channel == OrderChannel.dine_in:
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
                    mult = D("1.5") if any(m.name == "1.5 Porsiyon" for m in mods) else D("1")
                    for ing, per_portion in ctx.specs[name].recipe.items():
                        consumption[day][ing] += D(str(per_portion)) * oi.quantity * mult

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
    if channel == OrderChannel.delivery:
        method = PaymentMethod.online if rng.random() < 0.85 else PaymentMethod.cash
        return [Payment(method=method, amount=total, paid_at=paid_at)]
    card_share = 0.7 if channel == OrderChannel.dine_in else 0.6
    if channel == OrderChannel.dine_in and total > 400 and rng.random() < 0.08:
        cash_part = q2(total * D(str(round(rng.uniform(0.3, 0.6), 2))))
        return [
            Payment(method=PaymentMethod.cash, amount=cash_part, paid_at=paid_at),
            Payment(method=PaymentMethod.card, amount=total - cash_part, paid_at=paid_at),
        ]
    method = PaymentMethod.card if rng.random() < card_share else PaymentMethod.cash
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
    perishables = {"Domates", "Maydanoz", "Sivri Biber", "Patlıcan", "Limon"}

    for name, ing in ingredients.items():
        daily = [consumption[d].get(name, D("0")) for d in days]
        avg = sum(daily, D("0")) / len(daily)
        precision = D("1") if ing.unit in ("adet", "demet") else D("0.5")
        ing.reorder_level = max(precision, (avg * 2 / precision).quantize(D("1")) * precision)
        target = max(precision, (avg * 6 / precision).quantize(D("1")) * precision)

        stock = target
        first_day = days[0]
        session.add(
            StockMovement(
                ingredient_id=ing.id,
                change=q3(stock),
                reason=StockReason.adjustment,
                note="Açılış sayımı",
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
                            note="Tedarikçi teslimatı",
                            created_at=at(d, 9, 0),
                        )
                    )
            if name in DELAYED_INGREDIENTS and d >= delay_start and stock - used < avg * D("0.4"):
                # Supplier is late: only a small emergency purchase from the market
                qty = q3(max(used, avg * D("0.6")) - (stock - used))
                if qty > 0:
                    stock += qty
                    session.add(
                        StockMovement(
                            ingredient_id=ing.id,
                            change=qty,
                            reason=StockReason.purchase,
                            note="Acil alım (tedarikçi gecikmesi)",
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
                        note="Günlük satış tüketimi",
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
                            note="Haftalık fire",
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
        ctx = seed_reference_data(session)
        ctx.days = days
        consumption = seed_orders(session, ctx, now)
        seed_stock(session, ctx, consumption, now)
        session.commit()

        if verbose:
            n_orders = len(session.exec(select(Order.id)).all())
            low = session.exec(
                select(Ingredient).where(Ingredient.stock_qty < Ingredient.reorder_level)
            ).all()
            print(
                f"Seeded {len(MENU)} menu items, {len(TABLES)} tables, {n_orders} orders "
                f"over {days} days (until {now:%Y-%m-%d %H:%M})."
            )
            print("Below reorder level:", ", ".join(i.name for i in low) or "none")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the mock restaurant POS database.")
    parser.add_argument("--reset", action="store_true", help="Drop all tables and reseed.")
    parser.add_argument("--days", type=int, default=DAYS, help="Days of history to generate.")
    args = parser.parse_args()
    seed(reset=args.reset, days=args.days)


if __name__ == "__main__":
    main()
