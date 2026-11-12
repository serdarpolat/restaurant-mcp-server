"""Order business rules: validation, pricing, stock consumption, table state, audit."""

from decimal import Decimal

from sqlmodel import Session, select

from pos_api.db.models import (
    DiningTable,
    Ingredient,
    MenuItem,
    Modifier,
    Order,
    OrderChannel,
    OrderItem,
    OrderItemStatus,
    OrderStatus,
    Payment,
    Staff,
    StockMovement,
    StockReason,
    TableStatus,
)
from pos_api.errors import Conflict, Invalid, NotFound
from pos_api.schemas import OrderCreate, OrderItemCreate, PayRequest
from pos_api.services import audit
from pos_api.timeutil import now

PORTION_MULTIPLIERS = {"1.5 Porsiyon": Decimal("1.5")}


# ---------- Lookups ----------


def get_order(session: Session, order_id: int) -> Order:
    order = session.get(Order, order_id)
    if not order:
        raise NotFound(f"Order #{order_id} not found.")
    return order


def get_open_order(session: Session, order_id: int) -> Order:
    order = get_order(session, order_id)
    if order.status != OrderStatus.open:
        raise Conflict(f"Order #{order_id} is {order.status.value}; only open orders can change.")
    return order


def open_order_for_table(session: Session, table_id: int) -> Order | None:
    return session.exec(
        select(Order).where(Order.table_id == table_id, Order.status == OrderStatus.open)
    ).first()


# ---------- Pricing & validation ----------


def _build_line(session: Session, data: OrderItemCreate) -> tuple[OrderItem, list[Modifier]]:
    item = session.get(MenuItem, data.menu_item_id)
    if not item:
        raise NotFound(f"Menu item #{data.menu_item_id} not found.")
    if not item.is_active:
        raise Conflict(f"'{item.name}' is not available right now.")

    chosen = [session.get(Modifier, mid) for mid in data.modifier_ids]
    if any(m is None for m in chosen):
        raise Invalid(f"Unknown modifier id in {data.modifier_ids}.")

    allowed_groups = {g.id: g for g in item.modifier_groups}
    for m in chosen:
        if m.group_id not in allowed_groups:
            raise Invalid(f"Modifier '{m.name}' cannot be used with '{item.name}'.")

    for group in item.modifier_groups:
        picked = [m for m in chosen if m.group_id == group.id]
        if not group.min_select <= len(picked) <= group.max_select:
            options = ", ".join(f"{m.name} (id={m.id})" for m in group.modifiers)
            raise Invalid(
                f"'{item.name}' needs {group.min_select}-{group.max_select} choice(s) for "
                f"'{group.name}'. Options: {options}."
            )

    unit_price = item.price + sum((m.price_delta for m in chosen), Decimal(0))
    line = OrderItem(
        menu_item_id=item.id,
        quantity=data.quantity,
        unit_price=unit_price,
        modifiers=", ".join(m.name for m in chosen),
        note=data.note,
    )
    return line, chosen


def _consume_stock(
    session: Session, order_id: int, lines: list[tuple[OrderItem, list[Modifier]]]
) -> None:
    """Deduct ingredients for the given lines. Refuses if anything would go negative."""
    needed: dict[int, Decimal] = {}
    for line, mods in lines:
        item = session.get(MenuItem, line.menu_item_id)
        mult = Decimal(1)
        for m in mods:
            mult *= PORTION_MULTIPLIERS.get(m.name, Decimal(1))
        for r in item.recipe:
            needed[r.ingredient_id] = needed.get(r.ingredient_id, Decimal(0)) + (
                r.quantity * line.quantity * mult
            )

    ingredients = {i: session.get(Ingredient, i) for i in needed}
    short = [
        f"{ing.name} (need {needed[i]:.3f} {ing.unit}, have {ing.stock_qty:.3f})"
        for i, ing in ingredients.items()
        if ing.stock_qty < needed[i]
    ]
    if short:
        raise Conflict("Not enough stock: " + "; ".join(short))

    ts = now()
    for i, ing in ingredients.items():
        ing.stock_qty -= needed[i]
        session.add(
            StockMovement(
                ingredient_id=i,
                change=-needed[i],
                reason=StockReason.sale,
                note=f"Sipariş #{order_id}",
                created_at=ts,
            )
        )


def recompute_totals(order: Order) -> None:
    subtotal = sum(
        (i.unit_price * i.quantity for i in order.items if i.status == OrderItemStatus.active),
        Decimal(0),
    )
    order.subtotal = subtotal
    order.total = subtotal - order.discount


# ---------- Commands ----------


def create_order(session: Session, data: OrderCreate, actor: str) -> Order:
    table = None
    if data.channel == OrderChannel.dine_in:
        if data.table_id is None:
            raise Invalid("Dine-in orders need a table_id.")
        table = session.get(DiningTable, data.table_id)
        if not table:
            raise NotFound(f"Table #{data.table_id} not found.")
        existing = open_order_for_table(session, table.id)
        if existing:
            raise Conflict(
                f"Table '{table.name}' already has open order #{existing.id}. "
                "Add items to that order instead."
            )
    elif data.table_id is not None:
        raise Invalid(f"{data.channel.value} orders cannot have a table.")

    if data.staff_id is not None and not session.get(Staff, data.staff_id):
        raise NotFound(f"Staff #{data.staff_id} not found.")

    lines = [_build_line(session, i) for i in data.items]

    order = Order(
        channel=data.channel,
        table_id=table.id if table else None,
        staff_id=data.staff_id,
        status=OrderStatus.open,
        opened_at=now(),
    )
    order.items = [line for line, _ in lines]
    session.add(order)
    session.flush()  # assigns order.id

    _consume_stock(session, order.id, lines)
    recompute_totals(order)
    if table:
        table.status = TableStatus.occupied

    audit.record(session, actor, "create_order", {"order_id": order.id, **data.model_dump()})
    session.commit()
    session.refresh(order)
    return order


def add_items(session: Session, order_id: int, items: list[OrderItemCreate], actor: str) -> Order:
    order = get_open_order(session, order_id)
    lines = [_build_line(session, i) for i in items]
    _consume_stock(session, order.id, lines)
    for line, _ in lines:
        order.items.append(line)
    recompute_totals(order)
    audit.record(
        session,
        actor,
        "add_items",
        {"order_id": order.id, "items": [i.model_dump() for i in items]},
    )
    session.commit()
    session.refresh(order)
    return order


def void_item(session: Session, order_id: int, item_id: int, reason: str, actor: str) -> Order:
    order = get_open_order(session, order_id)
    line = next((i for i in order.items if i.id == item_id), None)
    if not line:
        raise NotFound(f"Item #{item_id} is not on order #{order_id}.")
    if line.status == OrderItemStatus.void:
        raise Conflict(f"Item #{item_id} is already void.")
    line.status = OrderItemStatus.void
    line.void_reason = reason
    recompute_totals(order)
    audit.record(
        session, actor, "void_item", {"order_id": order.id, "item_id": item_id, "reason": reason}
    )
    session.commit()
    session.refresh(order)
    return order


def _release_table(session: Session, order: Order) -> None:
    if order.table_id:
        table = session.get(DiningTable, order.table_id)
        table.status = TableStatus.free


def pay_order(session: Session, order_id: int, data: PayRequest, actor: str) -> Order:
    order = get_open_order(session, order_id)
    if not any(i.status == OrderItemStatus.active for i in order.items):
        raise Conflict(f"Order #{order_id} has no active items. Cancel it instead.")
    if data.discount_rate > 0 and not data.discount_reason:
        raise Invalid("A discount needs a discount_reason.")

    order.discount = (order.subtotal * data.discount_rate).quantize(Decimal("0.01"))
    order.discount_reason = data.discount_reason if data.discount_rate > 0 else None
    recompute_totals(order)

    ts = now()
    order.payments.append(Payment(method=data.method, amount=order.total, paid_at=ts))
    order.status = OrderStatus.paid
    order.closed_at = ts
    _release_table(session, order)

    audit.record(session, actor, "pay_order", {"order_id": order.id, **data.model_dump()})
    session.commit()
    session.refresh(order)
    return order


def cancel_order(session: Session, order_id: int, reason: str, actor: str) -> Order:
    order = get_open_order(session, order_id)
    for line in order.items:
        if line.status == OrderItemStatus.active:
            line.status = OrderItemStatus.void
            line.void_reason = reason
    recompute_totals(order)
    order.status = OrderStatus.cancelled
    order.closed_at = now()
    _release_table(session, order)
    audit.record(session, actor, "cancel_order", {"order_id": order.id, "reason": reason})
    session.commit()
    session.refresh(order)
    return order


def set_table_status(
    session: Session, table_id: int, status: TableStatus, actor: str
) -> DiningTable:
    table = session.get(DiningTable, table_id)
    if not table:
        raise NotFound(f"Table #{table_id} not found.")
    open_order = open_order_for_table(session, table_id)
    if open_order and status != TableStatus.occupied:
        raise Conflict(
            f"Table '{table.name}' has open order #{open_order.id}; pay or cancel it first."
        )
    if not open_order and status == TableStatus.occupied:
        raise Conflict("A table becomes occupied by opening an order on it.")
    table.status = status
    audit.record(session, actor, "set_table_status", {"table_id": table_id, "status": status})
    session.commit()
    session.refresh(table)
    return table
