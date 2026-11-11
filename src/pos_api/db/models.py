"""Data model for the mock restaurant POS.

Design notes:
- Money is stored as Decimal (2 decimal places) to avoid float rounding errors.
- Order items keep a snapshot of `unit_price` so price changes never rewrite history.
- Stock is tracked both as a current level (`Ingredient.stock_qty`) and as an
  append-only ledger (`StockMovement`) so "why did X run low?" is answerable.
- `AuditLog` records every write performed through the MCP server (AI actions).
- There is intentionally no customer table: no personal data is stored (privacy by design).
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum

from sqlmodel import Field, Relationship, SQLModel


def money(default: Decimal | None = None, **kwargs) -> Decimal:
    return Field(default=default, max_digits=10, decimal_places=2, **kwargs)


# ---------- Enums ----------


class StaffRole(str, Enum):
    waiter = "waiter"
    cashier = "cashier"
    manager = "manager"


class TableStatus(str, Enum):
    free = "free"
    occupied = "occupied"
    reserved = "reserved"


class OrderChannel(str, Enum):
    dine_in = "dine_in"
    takeaway = "takeaway"
    delivery = "delivery"


class OrderStatus(str, Enum):
    open = "open"
    paid = "paid"
    cancelled = "cancelled"


class OrderItemStatus(str, Enum):
    active = "active"
    void = "void"


class PaymentMethod(str, Enum):
    cash = "cash"
    card = "card"
    online = "online"


class StockReason(str, Enum):
    sale = "sale"
    purchase = "purchase"
    waste = "waste"
    adjustment = "adjustment"


# ---------- Staff ----------


class Staff(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    role: StaffRole
    is_active: bool = True


# ---------- Menu ----------


class Category(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(unique=True)
    sort_order: int = 0

    items: list["MenuItem"] = Relationship(back_populates="category")


class MenuItemModifierGroupLink(SQLModel, table=True):
    menu_item_id: int = Field(foreign_key="menuitem.id", primary_key=True)
    modifier_group_id: int = Field(foreign_key="modifiergroup.id", primary_key=True)


class MenuItem(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    category_id: int = Field(foreign_key="category.id", index=True)
    name: str = Field(index=True)
    description: str = ""
    price: Decimal = money()
    is_active: bool = True

    category: Category = Relationship(back_populates="items")
    modifier_groups: list["ModifierGroup"] = Relationship(
        back_populates="menu_items", link_model=MenuItemModifierGroupLink
    )
    recipe: list["RecipeItem"] = Relationship(back_populates="menu_item")


class ModifierGroup(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    min_select: int = 0
    max_select: int = 1

    modifiers: list["Modifier"] = Relationship(back_populates="group")
    menu_items: list[MenuItem] = Relationship(
        back_populates="modifier_groups", link_model=MenuItemModifierGroupLink
    )


class Modifier(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    group_id: int = Field(foreign_key="modifiergroup.id", index=True)
    name: str
    price_delta: Decimal = money(Decimal(0))

    group: ModifierGroup = Relationship(back_populates="modifiers")


# ---------- Inventory ----------


class Ingredient(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(unique=True)
    unit: str  # kg, lt, piece
    stock_qty: Decimal = Field(default=Decimal(0), max_digits=12, decimal_places=3)
    reorder_level: Decimal = Field(default=Decimal(0), max_digits=12, decimal_places=3)
    unit_cost: Decimal = money(Decimal(0))


class RecipeItem(SQLModel, table=True):
    """How much of an ingredient one portion of a menu item consumes."""

    menu_item_id: int = Field(foreign_key="menuitem.id", primary_key=True)
    ingredient_id: int = Field(foreign_key="ingredient.id", primary_key=True)
    quantity: Decimal = Field(max_digits=10, decimal_places=3)

    menu_item: MenuItem = Relationship(back_populates="recipe")
    ingredient: Ingredient = Relationship()


class StockMovement(SQLModel, table=True):
    """Append-only stock ledger. Positive = stock in, negative = stock out."""

    id: int | None = Field(default=None, primary_key=True)
    ingredient_id: int = Field(foreign_key="ingredient.id", index=True)
    change: Decimal = Field(max_digits=12, decimal_places=3)
    reason: StockReason
    note: str = ""
    created_at: datetime = Field(index=True)


# ---------- Floor ----------


class DiningTable(SQLModel, table=True):
    __tablename__ = "dining_table"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(unique=True)
    area: str
    capacity: int
    status: TableStatus = TableStatus.free


# ---------- Orders ----------


class Order(SQLModel, table=True):
    __tablename__ = "orders"  # "order" is a reserved SQL keyword

    id: int | None = Field(default=None, primary_key=True)
    table_id: int | None = Field(default=None, foreign_key="dining_table.id", index=True)
    staff_id: int | None = Field(default=None, foreign_key="staff.id", index=True)
    channel: OrderChannel
    status: OrderStatus = OrderStatus.open
    opened_at: datetime = Field(index=True)
    closed_at: datetime | None = None
    subtotal: Decimal = money(Decimal(0))
    discount: Decimal = money(Decimal(0))
    discount_reason: str | None = None
    total: Decimal = money(Decimal(0))

    items: list["OrderItem"] = Relationship(back_populates="order")
    payments: list["Payment"] = Relationship(back_populates="order")


class OrderItem(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="orders.id", index=True)
    menu_item_id: int = Field(foreign_key="menuitem.id", index=True)
    quantity: int = 1
    unit_price: Decimal = money()  # snapshot incl. modifiers
    modifiers: str = ""  # human-readable, e.g. "Acısız, 1.5 Porsiyon"
    note: str = ""
    status: OrderItemStatus = OrderItemStatus.active
    void_reason: str | None = None

    order: Order = Relationship(back_populates="items")


class Payment(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="orders.id", index=True)
    method: PaymentMethod
    amount: Decimal = money()
    paid_at: datetime

    order: Order = Relationship(back_populates="payments")


# ---------- Audit ----------


class AuditLog(SQLModel, table=True):
    """Every write performed through the MCP server is recorded here."""

    id: int | None = Field(default=None, primary_key=True)
    actor: str  # e.g. "mcp:claude-desktop"
    action: str  # e.g. "create_order"
    payload: str  # JSON
    created_at: datetime = Field(index=True)
