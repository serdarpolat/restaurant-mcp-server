from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, status
from sqlmodel import select

from pos_api.db.models import (
    DiningTable,
    MenuItem,
    Order,
    OrderChannel,
    OrderStatus,
    Staff,
)
from pos_api.deps import ActorDep, SessionDep
from pos_api.schemas import (
    OrderCreate,
    OrderItemRead,
    OrderItemsAdd,
    OrderRead,
    OrderSummary,
    PaymentRead,
    PayRequest,
    ReasonRequest,
)
from pos_api.services import orders as service
from pos_api.timeutil import day_range, resolve_dates, to_local

router = APIRouter(prefix="/orders", tags=["orders"])


def _summary(session, o: Order) -> dict:
    table = session.get(DiningTable, o.table_id) if o.table_id else None
    staff = session.get(Staff, o.staff_id) if o.staff_id else None
    return {
        "id": o.id,
        "channel": o.channel,
        "status": o.status,
        "table": table.name if table else None,
        "staff": staff.name if staff else None,
        "opened_at": to_local(o.opened_at),
        "closed_at": to_local(o.closed_at) if o.closed_at else None,
        "subtotal": o.subtotal,
        "discount": o.discount,
        "total": o.total,
    }


def to_read(session, o: Order) -> OrderRead:
    items = [
        OrderItemRead(
            id=i.id,
            menu_item_id=i.menu_item_id,
            name=session.get(MenuItem, i.menu_item_id).name,
            quantity=i.quantity,
            unit_price=i.unit_price,
            line_total=i.unit_price * i.quantity,
            modifiers=i.modifiers,
            note=i.note,
            status=i.status,
            void_reason=i.void_reason,
        )
        for i in o.items
    ]
    payments = [
        PaymentRead(method=p.method, amount=p.amount, paid_at=to_local(p.paid_at))
        for p in o.payments
    ]
    return OrderRead(
        **_summary(session, o), discount_reason=o.discount_reason, items=items, payments=payments
    )


@router.get("", response_model=list[OrderSummary])
def list_orders(
    session: SessionDep,
    status_: Annotated[OrderStatus | None, Query(alias="status")] = None,
    channel: OrderChannel | None = None,
    table_id: int | None = None,
    staff_id: int | None = None,
    date_from: Annotated[date | None, Query(description="Local date. Default: today")] = None,
    date_to: date | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
):
    start, end = day_range(*resolve_dates(date_from, date_to))
    stmt = select(Order).where(Order.opened_at >= start, Order.opened_at < end)
    if status_:
        stmt = stmt.where(Order.status == status_)
    if channel:
        stmt = stmt.where(Order.channel == channel)
    if table_id:
        stmt = stmt.where(Order.table_id == table_id)
    if staff_id:
        stmt = stmt.where(Order.staff_id == staff_id)
    orders = session.exec(stmt.order_by(Order.opened_at.desc()).limit(limit)).all()
    return [OrderSummary(**_summary(session, o)) for o in orders]


@router.get("/{order_id}", response_model=OrderRead)
def get_order(order_id: int, session: SessionDep):
    return to_read(session, service.get_order(session, order_id))


@router.post("", response_model=OrderRead, status_code=status.HTTP_201_CREATED)
def create_order(body: OrderCreate, session: SessionDep, actor: ActorDep):
    return to_read(session, service.create_order(session, body, actor))


@router.post("/{order_id}/items", response_model=OrderRead)
def add_items(order_id: int, body: OrderItemsAdd, session: SessionDep, actor: ActorDep):
    return to_read(session, service.add_items(session, order_id, body.items, actor))


@router.post("/{order_id}/items/{item_id}/void", response_model=OrderRead)
def void_item(
    order_id: int, item_id: int, body: ReasonRequest, session: SessionDep, actor: ActorDep
):
    return to_read(session, service.void_item(session, order_id, item_id, body.reason, actor))


@router.post("/{order_id}/pay", response_model=OrderRead)
def pay_order(order_id: int, body: PayRequest, session: SessionDep, actor: ActorDep):
    return to_read(session, service.pay_order(session, order_id, body, actor))


@router.post("/{order_id}/cancel", response_model=OrderRead)
def cancel_order(order_id: int, body: ReasonRequest, session: SessionDep, actor: ActorDep):
    return to_read(session, service.cancel_order(session, order_id, body.reason, actor))
