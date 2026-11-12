"""API request/response schemas."""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer

from pos_api.db.models import (
    OrderChannel,
    OrderItemStatus,
    OrderStatus,
    PaymentMethod,
    StaffRole,
    StockReason,
    TableStatus,
)

# Decimals are exact internally but serialized as JSON numbers.
Money = Annotated[Decimal, PlainSerializer(lambda v: float(v), return_type=float, when_used="json")]
Qty = Money


class Schema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- Staff ----------


class StaffRead(Schema):
    id: int
    name: str
    role: StaffRole
    is_active: bool


# ---------- Menu ----------


class CategoryRead(Schema):
    id: int
    name: str
    item_count: int = 0


class ModifierRead(Schema):
    id: int
    name: str
    price_delta: Money


class ModifierGroupRead(Schema):
    id: int
    name: str
    min_select: int
    max_select: int
    modifiers: list[ModifierRead]


class MenuItemRead(Schema):
    id: int
    name: str
    description: str
    price: Money
    category: str
    is_active: bool
    has_options: bool = False


class MenuItemDetail(MenuItemRead):
    modifier_groups: list[ModifierGroupRead]


# ---------- Tables ----------


class TableRead(Schema):
    id: int
    name: str
    area: str
    capacity: int
    status: TableStatus
    open_order_id: int | None = None


class TableStatusUpdate(BaseModel):
    status: TableStatus


# ---------- Orders ----------


class OrderItemRead(Schema):
    id: int
    menu_item_id: int
    name: str
    quantity: int
    unit_price: Money
    line_total: Money
    modifiers: str
    note: str
    status: OrderItemStatus
    void_reason: str | None


class PaymentRead(Schema):
    method: PaymentMethod
    amount: Money
    paid_at: datetime


class OrderSummary(Schema):
    id: int
    channel: OrderChannel
    status: OrderStatus
    table: str | None
    staff: str | None
    opened_at: datetime
    closed_at: datetime | None
    subtotal: Money
    discount: Money
    total: Money


class OrderRead(OrderSummary):
    discount_reason: str | None
    items: list[OrderItemRead]
    payments: list[PaymentRead]


class OrderItemCreate(BaseModel):
    menu_item_id: int
    quantity: int = Field(default=1, ge=1, le=50)
    modifier_ids: list[int] = Field(default_factory=list)
    note: str = Field(default="", max_length=200)


class OrderCreate(BaseModel):
    channel: OrderChannel = OrderChannel.dine_in
    table_id: int | None = None
    staff_id: int | None = None
    items: list[OrderItemCreate] = Field(min_length=1, max_length=50)


class OrderItemsAdd(BaseModel):
    items: list[OrderItemCreate] = Field(min_length=1, max_length=50)


class ReasonRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=200)


class PayRequest(BaseModel):
    method: PaymentMethod
    discount_rate: Decimal = Field(default=Decimal(0), ge=0, le=Decimal("0.5"))
    discount_reason: str | None = Field(default=None, max_length=100)


# ---------- Inventory ----------


class IngredientRead(Schema):
    id: int
    name: str
    unit: str
    stock_qty: Qty
    reorder_level: Qty
    unit_cost: Money
    below_reorder: bool
    avg_daily_usage: Qty  # last 7 days
    days_of_cover: float | None  # stock / avg daily usage


class StockMovementRead(Schema):
    id: int
    change: Qty
    reason: StockReason
    note: str
    created_at: datetime


class PurchaseCreate(BaseModel):
    ingredient_id: int
    quantity: Decimal = Field(gt=0, le=10000)
    note: str = Field(default="Manuel alım", max_length=200)


# ---------- Reports ----------


class SalesRow(BaseModel):
    key: str
    orders: int
    revenue: Money
    avg_ticket: Money


class SalesReport(BaseModel):
    date_from: date
    date_to: date
    group_by: str
    total_orders: int
    total_revenue: Money
    avg_ticket: Money
    rows: list[SalesRow]


class TopItemRow(BaseModel):
    menu_item_id: int
    name: str
    category: str
    quantity: int
    revenue: Money


class StaffPerformanceRow(BaseModel):
    staff_id: int
    name: str
    role: StaffRole
    orders: int
    revenue: Money
    avg_ticket: Money


class VoidRow(BaseModel):
    name: str
    reason: str
    quantity: int
    value: Money


class DailySummary(BaseModel):
    date: date
    orders_paid: int
    orders_open: int
    orders_cancelled: int
    gross_sales: Money
    discounts: Money
    net_sales: Money
    avg_ticket: Money
    by_channel: dict[str, Money]
    by_payment_method: dict[str, Money]
    voided_items: int
    voided_value: Money


# ---------- Audit ----------


class AuditLogRead(Schema):
    id: int
    actor: str
    action: str
    payload: str
    created_at: datetime
