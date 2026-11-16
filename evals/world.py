"""The fixed restaurant every eval case runs against, and lookups for expected arguments."""

from datetime import timedelta
from pathlib import Path
from typing import Any, ClassVar

from sqlalchemy.engine import Engine
from sqlmodel import Session, create_engine, delete, select

from pos_api.db.models import (
    DiningTable,
    Ingredient,
    MenuItem,
    Order,
    OrderChannel,
    OrderItem,
    OrderStatus,
    Payment,
    TableStatus,
)
from pos_api.db.seed import seed
from pos_api.schemas import OrderCreate, OrderItemCreate
from pos_api.services import orders
from pos_api.timeutil import today

ACTOR = "eval:setup"


def sqlite_engine(path: Path) -> Engine:
    return create_engine(f"sqlite:///{path.as_posix()}", connect_args={"check_same_thread": False})


def _menu_item(session: Session, name: str) -> MenuItem:
    item = session.exec(select(MenuItem).where(MenuItem.name == name)).first()
    if item is None:
        raise KeyError(f"Unknown menu item in eval file: {name!r}")
    return item


def _modifier_id(session: Session, item_name: str, option: str) -> int:
    for group in _menu_item(session, item_name).modifier_groups:
        for m in group.modifiers:
            if m.name == option:
                return m.id
    raise KeyError(f"{item_name!r} has no option {option!r}")


def _table(session: Session, name: str) -> DiningTable:
    table = session.exec(select(DiningTable).where(DiningTable.name == name)).first()
    if table is None:
        raise KeyError(f"Unknown table in eval file: {name!r}")
    return table


def _open_order(session: Session, table_name: str) -> Order:
    order = orders.open_order_for_table(session, _table(session, table_name).id)
    if order is None:
        raise KeyError(f"Table {table_name!r} has no open order in the eval world")
    return order


def build_world(path: Path, world: dict[str, Any], days: int = 30) -> None:
    """Seed `days` of history, then reset the floor to the world described in cases.yaml."""
    engine = sqlite_engine(path)
    seed(reset=True, days=days, db_engine=engine, verbose=False)
    with Session(engine) as session:
        # Drop whatever happens to be open at seed time so every run starts the same.
        open_ids = session.exec(select(Order.id).where(Order.status == OrderStatus.open)).all()
        if open_ids:
            session.exec(delete(OrderItem).where(OrderItem.order_id.in_(open_ids)))
            session.exec(delete(Payment).where(Payment.order_id.in_(open_ids)))
            session.exec(delete(Order).where(Order.id.in_(open_ids)))
        for table in session.exec(select(DiningTable)).all():
            table.status = TableStatus.free
        for name in world.get("reserved_tables", []):
            _table(session, name).status = TableStatus.reserved
        session.commit()

        for table_name, lines in world.get("open_orders", {}).items():
            items = [
                OrderItemCreate(
                    menu_item_id=_menu_item(session, line["item"]).id,
                    quantity=line.get("quantity", 1),
                    modifier_ids=[
                        _modifier_id(session, line["item"], o) for o in line.get("options", [])
                    ],
                )
                for line in lines
            ]
            data = OrderCreate(
                channel=OrderChannel.dine_in, table_id=_table(session, table_name).id, items=items
            )
            orders.create_order(session, data, ACTOR)
    engine.dispose()


class Resolver:
    """Turns references in cases.yaml ({menu: Ayran}, {date: -1}, ...) into concrete values."""

    REFS: ClassVar[set[str]] = {
        "menu",
        "table",
        "modifier",
        "ingredient",
        "open_order",
        "order_line",
        "date",
    }

    def __init__(self, session: Session):
        self.session = session

    def menu(self) -> tuple[list[dict[str, Any]], dict[int, dict[str, Any]]]:
        """The menu as the POS API shows it (items, and item details with options)."""
        items = self.session.exec(select(MenuItem).where(MenuItem.is_active)).all()
        menu = [{"id": i.id, "name": i.name} for i in items]
        details = {
            i.id: {
                "id": i.id,
                "name": i.name,
                "modifier_groups": [
                    {
                        "name": g.name,
                        "modifiers": [{"id": m.id, "name": m.name} for m in g.modifiers],
                    }
                    for g in i.modifier_groups
                ],
            }
            for i in items
        }
        return menu, details

    def tables(self) -> list[dict[str, Any]]:
        return [{"id": t.id, "name": t.name} for t in self.session.exec(select(DiningTable)).all()]

    def resolve(self, ref: str, value: Any) -> Any:
        s = self.session
        if ref == "menu":
            return _menu_item(s, value).id
        if ref == "table":
            return _table(s, value).id
        if ref == "modifier":
            return _modifier_id(s, *value)
        if ref == "ingredient":
            ing = s.exec(select(Ingredient).where(Ingredient.name == value)).first()
            if ing is None:
                raise KeyError(f"Unknown ingredient in eval file: {value!r}")
            return ing.id
        if ref == "open_order":
            return _open_order(s, value).id
        if ref == "order_line":
            table_name, item_name = value
            order = _open_order(s, table_name)
            item_id = _menu_item(s, item_name).id
            return next(i.id for i in order.items if i.menu_item_id == item_id)
        if ref == "date":
            return (today() + timedelta(days=int(value))).isoformat()
        raise KeyError(ref)
