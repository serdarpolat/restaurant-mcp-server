"""Analytical reports. Grouping happens in local time (not UTC)."""

from collections import defaultdict
from collections.abc import Callable
from datetime import date
from decimal import Decimal
from enum import Enum

from sqlmodel import Session, func, select

from pos_api.db.models import (
    Category,
    MenuItem,
    Order,
    OrderItem,
    OrderItemStatus,
    OrderStatus,
    Payment,
    Staff,
)
from pos_api.schemas import (
    DailySummary,
    SalesReport,
    SalesRow,
    StaffPerformanceRow,
    TopItemRow,
    VoidRow,
)
from pos_api.timeutil import day_range, to_local

ZERO = Decimal(0)
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


class SalesGroupBy(str, Enum):
    day = "day"
    hour = "hour"
    weekday = "weekday"
    channel = "channel"


class TopItemsSort(str, Enum):
    quantity = "quantity"
    revenue = "revenue"


def _avg(total: Decimal, count: int) -> Decimal:
    return (total / count).quantize(Decimal("0.01")) if count else ZERO


def _paid_orders(session: Session, date_from: date, date_to: date) -> list[Order]:
    start, end = day_range(date_from, date_to)
    return session.exec(
        select(Order).where(
            Order.status == OrderStatus.paid, Order.opened_at >= start, Order.opened_at < end
        )
    ).all()


def sales(session: Session, date_from: date, date_to: date, group_by: SalesGroupBy) -> SalesReport:
    key_fn: Callable[[Order], str] = {
        SalesGroupBy.day: lambda o: to_local(o.opened_at).date().isoformat(),
        SalesGroupBy.hour: lambda o: f"{to_local(o.opened_at).hour:02d}:00",
        SalesGroupBy.weekday: lambda o: WEEKDAYS[to_local(o.opened_at).weekday()],
        SalesGroupBy.channel: lambda o: o.channel.value,
    }[group_by]

    buckets: dict[str, list[Decimal]] = defaultdict(list)
    for o in _paid_orders(session, date_from, date_to):
        buckets[key_fn(o)].append(o.total)

    order = WEEKDAYS if group_by == SalesGroupBy.weekday else sorted(buckets)
    rows = [
        SalesRow(key=k, orders=len(v), revenue=sum(v, ZERO), avg_ticket=_avg(sum(v, ZERO), len(v)))
        for k in order
        if (v := buckets.get(k))
    ]
    total = sum((r.revenue for r in rows), ZERO)
    count = sum(r.orders for r in rows)
    return SalesReport(
        date_from=date_from,
        date_to=date_to,
        group_by=group_by.value,
        total_orders=count,
        total_revenue=total,
        avg_ticket=_avg(total, count),
        rows=rows,
    )


def top_items(
    session: Session,
    date_from: date,
    date_to: date,
    sort: TopItemsSort,
    limit: int,
    category: str | None = None,
) -> list[TopItemRow]:
    start, end = day_range(date_from, date_to)
    qty = func.sum(OrderItem.quantity)
    revenue = func.sum(OrderItem.quantity * OrderItem.unit_price)
    stmt = (
        select(MenuItem.id, MenuItem.name, Category.name, qty, revenue)
        .join(OrderItem, OrderItem.menu_item_id == MenuItem.id)
        .join(Order, Order.id == OrderItem.order_id)
        .join(Category, Category.id == MenuItem.category_id)
        .where(
            Order.status == OrderStatus.paid,
            OrderItem.status == OrderItemStatus.active,
            Order.opened_at >= start,
            Order.opened_at < end,
        )
        .group_by(MenuItem.id, MenuItem.name, Category.name)
        .order_by((qty if sort == TopItemsSort.quantity else revenue).desc())
        .limit(limit)
    )
    if category:
        stmt = stmt.where(Category.name == category)
    return [
        TopItemRow(
            menu_item_id=i,
            name=n,
            category=c,
            quantity=int(q),
            revenue=Decimal(str(r)).quantize(Decimal("0.01")),
        )
        for i, n, c, q, r in session.exec(stmt).all()
    ]


def staff_performance(
    session: Session, date_from: date, date_to: date
) -> list[StaffPerformanceRow]:
    totals: dict[int, list[Decimal]] = defaultdict(list)
    for o in _paid_orders(session, date_from, date_to):
        if o.staff_id:
            totals[o.staff_id].append(o.total)
    staff = {s.id: s for s in session.exec(select(Staff)).all()}
    rows = [
        StaffPerformanceRow(
            staff_id=sid,
            name=staff[sid].name,
            role=staff[sid].role,
            orders=len(v),
            revenue=sum(v, ZERO),
            avg_ticket=_avg(sum(v, ZERO), len(v)),
        )
        for sid, v in totals.items()
    ]
    return sorted(rows, key=lambda r: r.revenue, reverse=True)


def voids(session: Session, date_from: date, date_to: date) -> list[VoidRow]:
    start, end = day_range(date_from, date_to)
    rows = session.exec(
        select(MenuItem.name, OrderItem.void_reason, OrderItem.quantity, OrderItem.unit_price)
        .join(OrderItem, OrderItem.menu_item_id == MenuItem.id)
        .join(Order, Order.id == OrderItem.order_id)
        .where(
            OrderItem.status == OrderItemStatus.void,
            Order.opened_at >= start,
            Order.opened_at < end,
        )
    ).all()
    agg: dict[tuple[str, str], list] = defaultdict(lambda: [0, ZERO])
    for name, reason, q, price in rows:
        agg[(name, reason or "")][0] += q
        agg[(name, reason or "")][1] += price * q
    out = [VoidRow(name=n, reason=r, quantity=q, value=v) for (n, r), (q, v) in agg.items()]
    return sorted(out, key=lambda r: r.value, reverse=True)


def daily_summary(session: Session, day: date) -> DailySummary:
    start, end = day_range(day, day)
    orders = session.exec(
        select(Order).where(Order.opened_at >= start, Order.opened_at < end)
    ).all()
    paid = [o for o in orders if o.status == OrderStatus.paid]

    by_channel: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for o in paid:
        by_channel[o.channel.value] += o.total

    by_method: dict[str, Decimal] = defaultdict(lambda: ZERO)
    paid_ids = [o.id for o in paid]
    if paid_ids:
        for p in session.exec(select(Payment).where(Payment.order_id.in_(paid_ids))).all():
            by_method[p.method.value] += p.amount

    voided = [
        i
        for o in orders
        if o.status != OrderStatus.cancelled
        for i in o.items
        if i.status == OrderItemStatus.void
    ]
    gross = sum((o.subtotal for o in paid), ZERO)
    discounts = sum((o.discount for o in paid), ZERO)
    net = gross - discounts
    return DailySummary(
        date=day,
        orders_paid=len(paid),
        orders_open=sum(o.status == OrderStatus.open for o in orders),
        orders_cancelled=sum(o.status == OrderStatus.cancelled for o in orders),
        gross_sales=gross,
        discounts=discounts,
        net_sales=net,
        avg_ticket=_avg(net, len(paid)),
        by_channel=dict(by_channel),
        by_payment_method=dict(by_method),
        voided_items=sum(i.quantity for i in voided),
        voided_value=sum((i.unit_price * i.quantity for i in voided), ZERO),
    )
