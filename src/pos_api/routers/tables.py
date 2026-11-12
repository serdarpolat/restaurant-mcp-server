from fastapi import APIRouter
from sqlmodel import select

from pos_api.db.models import DiningTable, Order, OrderStatus, TableStatus
from pos_api.deps import ActorDep, SessionDep
from pos_api.errors import NotFound
from pos_api.schemas import TableRead, TableStatusUpdate
from pos_api.services import orders as order_service

router = APIRouter(prefix="/tables", tags=["tables"])


def _open_orders_by_table(session) -> dict[int, int]:
    rows = session.exec(
        select(Order.table_id, Order.id).where(
            Order.status == OrderStatus.open, Order.table_id.is_not(None)
        )
    ).all()
    return dict(rows)


def _read(table: DiningTable, open_order_id: int | None) -> TableRead:
    return TableRead.model_validate(table).model_copy(update={"open_order_id": open_order_id})


@router.get("", response_model=list[TableRead])
def list_tables(session: SessionDep, status: TableStatus | None = None, area: str | None = None):
    stmt = select(DiningTable).order_by(DiningTable.id)
    if status:
        stmt = stmt.where(DiningTable.status == status)
    if area:
        stmt = stmt.where(DiningTable.area == area)
    open_orders = _open_orders_by_table(session)
    return [_read(t, open_orders.get(t.id)) for t in session.exec(stmt).all()]


@router.get("/{table_id}", response_model=TableRead)
def get_table(table_id: int, session: SessionDep):
    table = session.get(DiningTable, table_id)
    if not table:
        raise NotFound(f"Table #{table_id} not found.")
    return _read(table, _open_orders_by_table(session).get(table_id))


@router.patch("/{table_id}", response_model=TableRead)
def update_table_status(
    table_id: int, body: TableStatusUpdate, session: SessionDep, actor: ActorDep
):
    table = order_service.set_table_status(session, table_id, body.status, actor)
    return _read(table, None)
