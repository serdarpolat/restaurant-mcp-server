"""Generate a large, realistic, English test dataset as plain JSON files.

Standalone deliverable: it does NOT touch the project's real SQLite seed
(src/pos_api/db/seed.py) or its models. The real model deliberately has no
customer table ("no personal data is stored (privacy by design)",
see src/pos_api/db/models.py:9); this dataset adds a Users table on purpose,
so it is kept separate rather than wired into the live demo API.

Six linked entities, as requested:
  1. categories.json   + products.json       (products.category_id -> categories.id)
  2. order_items.json                          (order_items.product_id -> products.id)
  3. users.json                                (type: "registered" | "guest")
  4. order_methods.json                        (delivery | pickup | dineIn)
  5. payment_methods.json                      (cash | credit_card | meal_voucher | apple_pay | google_pay)
  6. orders.json  -> user_id, order_method_id, payment_method_id, table_id (dineIn only)

All foreign keys are plain integer ids, matching the parent file's "id" field.

Usage:
    python generate_testdata.py
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

SEED = 7
DAYS = 90
BASE_ORDERS_PER_DAY = 90
OUT_DIR = Path(__file__).parent

D = Decimal


def q2(value: Decimal) -> float:
    return float(value.quantize(D("0.01"), rounding=ROUND_HALF_UP))


# --------------------------------------------------------------------------- #
# Reference data
# --------------------------------------------------------------------------- #

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


@dataclass
class ProductSpec:
    name: str
    category: str
    price: int
    description: str
    weight: float = 1.0


PRODUCTS: list[ProductSpec] = [
    # Soups
    ProductSpec("Lentil Soup", "Soups", 150, "Served with butter and lemon.", 6),
    ProductSpec("Ezogelin Soup", "Soups", 150, "Traditional soup with bulgur and mint.", 3),
    ProductSpec("Yayla Soup", "Soups", 160, "Yogurt soup with rice and mint.", 2),
    # Starters
    ProductSpec("Haydari", "Starters", 140, "Strained yogurt with garlic and mint.", 3),
    ProductSpec("Spicy Ezme", "Starters", 130, "Finely chopped tomato, pepper and onion.", 5),
    ProductSpec("Stuffed Bulgur Balls", "Starters", 90, "Priced per piece.", 3),
    # Kebabs
    ProductSpec("Adana Kebab", "Kebabs", 560, "Spicy minced lamb, flatbread, grilled tomato.", 10),
    ProductSpec("Urfa Kebab", "Kebabs", 560, "Mild minced lamb, flatbread, grilled vegetables.", 5),
    ProductSpec("Beyti Kebab", "Kebabs", 640, "Wrapped in flatbread, yogurt and butter.", 4),
    ProductSpec("Iskender Kebab", "Kebabs", 620, "Lamb over flatbread, tomato sauce, yogurt.", 6),
    ProductSpec("Eggplant Kebab", "Kebabs", 600, "Eggplant and minced meat skewer.", 2),
    ProductSpec("Ali Nazik", "Kebabs", 650, "Lamb over smoky eggplant yogurt puree.", 2),
    ProductSpec("Lamb Shish", "Kebabs", 720, "Marinated cubed lamb.", 3),
    ProductSpec("Chicken Shish", "Kebabs", 420, "Marinated chicken thigh.", 6),
    ProductSpec("Chicken Wings", "Kebabs", 400, "Grilled spiced wings.", 4),
    ProductSpec("Mixed Grill", "Kebabs", 950, "Adana, lamb shish and chicken shish together.", 2),
    # Grills
    ProductSpec("Lamb Chops", "Grills", 950, "Grilled lamb chops with rice.", 2),
    ProductSpec("Grilled Meatballs", "Grills", 480, "Homemade meatballs, rice and bean salad.", 4),
    ProductSpec("Cheese-Stuffed Meatballs", "Grills", 520, "Meatballs stuffed with cheese.", 2),
    # Flatbreads
    ProductSpec("Lahmacun", "Flatbreads", 160, "Thin dough, minced meat topping, greens.", 9),
    ProductSpec("Minced Meat Pide", "Flatbreads", 380, "Stone-oven pide with minced meat.", 4),
    ProductSpec("Cheese Pide", "Flatbreads", 340, "Pide loaded with cheese.", 3),
    ProductSpec("Diced Lamb Pide", "Flatbreads", 450, "Pide with diced lamb.", 3),
    ProductSpec("Mixed Pide", "Flatbreads", 460, "Minced meat, cheese and egg.", 3),
    # Salads
    ProductSpec("Shepherd's Salad", "Salads", 150, "Tomato, cucumber, pepper, onion, parsley.", 5),
    ProductSpec("Gavurdagi Salad", "Salads", 190, "With walnuts and pomegranate sauce.", 3),
    # Desserts
    ProductSpec("Kunefe", "Desserts", 280, "Hatay style, served hot.", 6),
    ProductSpec("Pistachio Baklava", "Desserts", 340, "4 pieces, with Antep pistachio.", 4),
    ProductSpec("Rice Pudding", "Desserts", 160, "Baked rice pudding.", 3),
    # Beverages
    ProductSpec("Ayran", "Beverages", 50, "Churned yogurt drink.", 10),
    ProductSpec("Cola", "Beverages", 80, "330 ml can.", 5),
    ProductSpec("Water", "Beverages", 25, "500 ml.", 4),
    ProductSpec("Turnip Juice", "Beverages", 60, "Spicy or mild.", 4),
    ProductSpec("Soda", "Beverages", 50, "200 ml.", 2),
    ProductSpec("Lemonade", "Beverages", 90, "Homemade, with fresh mint.", 2),
    ProductSpec("Tea", "Beverages", 30, "Served in a slim glass.", 6),
    ProductSpec("Turkish Coffee", "Beverages", 90, "Served with Turkish delight.", 2),
]

TABLES = (
    [(f"Hall {i}", "Hall", c) for i, c in enumerate([2, 2, 4, 4, 4, 6, 6, 8], start=1)]
    + [(f"Garden {i}", "Garden", c) for i, c in enumerate([2, 4, 4, 4, 6], start=1)]
    + [(f"Terrace {i}", "Terrace", c) for i, c in enumerate([4, 6], start=1)]
)

ORDER_METHODS = ["delivery", "pickup", "dineIn"]
PAYMENT_METHODS = ["cash", "credit_card", "meal_voucher", "apple_pay", "google_pay"]

# Weight per order method (sums to 100)
ORDER_METHOD_WEIGHTS = {"dineIn": 60, "delivery": 25, "pickup": 15}

# Payment method weights, per order method (each sums to 100)
PAYMENT_WEIGHTS = {
    "dineIn": {"cash": 30, "credit_card": 55, "meal_voucher": 10, "apple_pay": 3, "google_pay": 2},
    "pickup": {"cash": 40, "credit_card": 45, "meal_voucher": 5, "apple_pay": 5, "google_pay": 5},
    "delivery": {
        "cash": 10,
        "credit_card": 35,
        "meal_voucher": 0,
        "apple_pay": 30,
        "google_pay": 25,
    },
}

CANCEL_REASONS = ["Customer cancelled", "Courier not found", "Duplicate order"]
DISCOUNT_REASONS = [("Staff discount", D("0.20")), ("Loyalty discount", D("0.10"))]
ONLINE_CAMPAIGN = ("Online campaign", D("0.15"))

WEEKDAY_FACTOR = [0.80, 0.85, 0.90, 0.95, 1.15, 1.40, 1.30]  # Mon..Sun
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

FIRST_NAMES = [
    "James",
    "Mary",
    "John",
    "Patricia",
    "Robert",
    "Jennifer",
    "Michael",
    "Linda",
    "David",
    "Elizabeth",
    "William",
    "Barbara",
    "Richard",
    "Susan",
    "Joseph",
    "Jessica",
    "Thomas",
    "Sarah",
    "Charles",
    "Karen",
    "Daniel",
    "Nancy",
    "Matthew",
    "Lisa",
    "Anthony",
    "Betty",
    "Mark",
    "Margaret",
    "Donald",
    "Sandra",
    "Steven",
    "Ashley",
    "Paul",
    "Kimberly",
    "Andrew",
    "Emily",
    "Joshua",
    "Donna",
    "Kevin",
    "Michelle",
]
LAST_NAMES = [
    "Smith",
    "Johnson",
    "Williams",
    "Brown",
    "Jones",
    "Garcia",
    "Miller",
    "Davis",
    "Rodriguez",
    "Martinez",
    "Hernandez",
    "Lopez",
    "Gonzalez",
    "Wilson",
    "Anderson",
    "Thomas",
    "Taylor",
    "Moore",
    "Jackson",
    "Martin",
    "Lee",
    "Perez",
    "Thompson",
    "White",
    "Harris",
    "Sanchez",
    "Clark",
    "Ramirez",
    "Lewis",
    "Robinson",
]

N_REGISTERED_USERS = 150


def weighted_pick(rng: random.Random, options: dict[str, float]) -> str:
    names = list(options)
    return rng.choices(names, weights=[options[n] for n in names])[0]


def main() -> None:
    rng = random.Random(SEED)
    now = datetime(2026, 11, 26, 20, 30, 0)

    # ---- 1. categories + products ---- #
    categories = [{"id": i + 1, "name": name} for i, name in enumerate(CATEGORIES)]
    cat_id = {c["name"]: c["id"] for c in categories}
    products = [
        {
            "id": i + 1,
            "category_id": cat_id[p.category],
            "name": p.name,
            "description": p.description,
            "price": p.price,
        }
        for i, p in enumerate(PRODUCTS)
    ]
    product_weight = {p["id"]: spec.weight for p, spec in zip(products, PRODUCTS)}
    product_price = {p["id"]: D(p["price"]) for p in products}

    # Tables (kept, per Serdar's choice: dineIn orders reference a table)
    tables = [
        {"id": i + 1, "name": name, "area": area, "capacity": cap}
        for i, (name, area, cap) in enumerate(TABLES)
    ]

    # ---- 4/5. order methods + payment methods (small lookup tables) ---- #
    order_methods = [{"id": i + 1, "name": name} for i, name in enumerate(ORDER_METHODS)]
    om_id = {m["name"]: m["id"] for m in order_methods}
    payment_methods = [{"id": i + 1, "name": name} for i, name in enumerate(PAYMENT_METHODS)]
    pm_id = {m["name"]: m["id"] for m in payment_methods}

    # ---- 3. users: registered (reused across orders) + guest (one per guest order) ---- #
    users: list[dict] = []
    registered_ids: list[int] = []
    for i in range(N_REGISTERED_USERS):
        first, last = rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES)
        uid = len(users) + 1
        users.append(
            {
                "id": uid,
                "type": "registered",
                "name": f"{first} {last}",
                "email": f"{first.lower()}.{last.lower()}{uid}@example.com",
                "created_at": (now - timedelta(days=rng.randint(30, 700))).isoformat(),
            }
        )
        registered_ids.append(uid)

    def new_guest_user(order_time: datetime) -> int:
        uid = len(users) + 1
        users.append(
            {
                "id": uid,
                "type": "guest",
                "name": f"Guest {uid}",
                "email": None,
                "created_at": order_time.isoformat(),
            }
        )
        return uid

    # ---- 2/6. orders + order_items ---- #
    orders: list[dict] = []
    order_items: list[dict] = []
    order_id_seq = 1
    item_id_seq = 1
    start_day = now.date() - timedelta(days=DAYS - 1)
    open_tables: set[int] = set()

    for day_index in range(DAYS):
        day = start_day + timedelta(days=day_index)
        factor = WEEKDAY_FACTOR[day.weekday()] * (1 + 0.08 * day_index / DAYS)
        n_orders = round(BASE_ORDERS_PER_DAY * factor * rng.uniform(0.9, 1.1))
        hours = rng.choices(list(HOUR_WEIGHTS), weights=list(HOUR_WEIGHTS.values()), k=n_orders)

        for hour in sorted(hours):
            opened_at = datetime(
                day.year, day.month, day.day, hour, rng.randint(0, 59), rng.randint(0, 59)
            )
            if opened_at > now:
                continue

            method = weighted_pick(rng, ORDER_METHOD_WEIGHTS)
            minutes_open = {"dineIn": (35, 90), "pickup": (5, 15), "delivery": (25, 50)}[method]
            closed_at = opened_at + timedelta(minutes=rng.randint(*minutes_open))
            still_open = closed_at > now

            table_id = None
            if method == "dineIn":
                candidates = (
                    [t for t in tables if t["id"] not in open_tables] if still_open else tables
                )
                if not candidates:
                    continue
                table_id = rng.choice(candidates)["id"]

            # 70% of orders come from a registered user, 30% guest checkout
            if rng.random() < 0.7:
                user_id = rng.choice(registered_ids)
            else:
                user_id = new_guest_user(opened_at)

            n_lines = rng.choices([1, 2, 3, 4, 5], weights=[20, 35, 25, 13, 7])[0]
            chosen_products = rng.choices(
                list(product_weight), weights=list(product_weight.values()), k=n_lines
            )
            line_counts: dict[int, int] = {}
            for pid in chosen_products:
                line_counts[pid] = line_counts.get(pid, 0) + rng.choice([1, 1, 1, 2, 2, 3])

            status = "open" if still_open else "paid"
            if not still_open and rng.random() < 0.015:
                status = "cancelled"

            subtotal = D("0")
            this_order_items = []
            for pid, qty in line_counts.items():
                unit_price = product_price[pid]
                line_total = unit_price * qty
                this_order_items.append(
                    {
                        "id": item_id_seq,
                        "order_id": order_id_seq,
                        "product_id": pid,
                        "quantity": qty,
                        "unit_price": q2(unit_price),
                        "line_total": q2(line_total),
                    }
                )
                item_id_seq += 1
                if status != "cancelled":
                    subtotal += line_total

            discount = D("0")
            discount_reason = None
            if status == "paid" and rng.random() < 0.06:
                if method == "delivery":
                    discount_reason, rate = ONLINE_CAMPAIGN
                else:
                    discount_reason, rate = rng.choice(DISCOUNT_REASONS)
                discount = subtotal * rate

            payment_method_id = (
                pm_id[weighted_pick(rng, PAYMENT_WEIGHTS[method])] if status == "paid" else None
            )

            orders.append(
                {
                    "id": order_id_seq,
                    "user_id": user_id,
                    "order_method_id": om_id[method],
                    "payment_method_id": payment_method_id,
                    "table_id": table_id,
                    "status": status,
                    "cancel_reason": rng.choice(CANCEL_REASONS) if status == "cancelled" else None,
                    "opened_at": opened_at.isoformat(),
                    "closed_at": None if still_open else closed_at.isoformat(),
                    "subtotal": q2(subtotal),
                    "discount": q2(discount),
                    "discount_reason": discount_reason,
                    "total": q2(subtotal - discount),
                }
            )
            order_items.extend(this_order_items)
            if still_open and table_id:
                open_tables.add(table_id)
            order_id_seq += 1

    data = {
        "categories.json": categories,
        "products.json": products,
        "tables.json": tables,
        "users.json": users,
        "order_methods.json": order_methods,
        "payment_methods.json": payment_methods,
        "orders.json": orders,
        "order_items.json": order_items,
    }
    for filename, rows in data.items():
        (OUT_DIR / filename).write_text(
            json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    print("Generated:")
    for filename, rows in data.items():
        print(f"  {filename:<22} {len(rows):>6} rows")


if __name__ == "__main__":
    main()
