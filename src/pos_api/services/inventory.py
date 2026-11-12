from datetime import timedelta
from decimal import Decimal

from sqlmodel import Session, func, select

from pos_api.db.models import Ingredient, StockMovement, StockReason
from pos_api.errors import NotFound
from pos_api.schemas import IngredientRead, PurchaseCreate
from pos_api.services import audit
from pos_api.timeutil import now

USAGE_WINDOW_DAYS = 7


def _usage_by_ingredient(session: Session) -> dict[int, Decimal]:
    since = now() - timedelta(days=USAGE_WINDOW_DAYS)
    rows = session.exec(
        select(StockMovement.ingredient_id, func.sum(StockMovement.change))
        .where(StockMovement.reason == StockReason.sale, StockMovement.created_at >= since)
        .group_by(StockMovement.ingredient_id)
    ).all()
    return {i: -Decimal(str(total)) / USAGE_WINDOW_DAYS for i, total in rows}


def to_read(ing: Ingredient, avg_usage: Decimal) -> IngredientRead:
    avg = avg_usage.quantize(Decimal("0.001"))
    return IngredientRead(
        id=ing.id,
        name=ing.name,
        unit=ing.unit,
        stock_qty=ing.stock_qty,
        reorder_level=ing.reorder_level,
        unit_cost=ing.unit_cost,
        below_reorder=ing.stock_qty < ing.reorder_level,
        avg_daily_usage=avg,
        days_of_cover=round(float(ing.stock_qty / avg), 1) if avg > 0 else None,
    )


def list_ingredients(session: Session) -> list[IngredientRead]:
    usage = _usage_by_ingredient(session)
    ingredients = session.exec(select(Ingredient).order_by(Ingredient.name)).all()
    return [to_read(i, usage.get(i.id, Decimal(0))) for i in ingredients]


def add_purchase(session: Session, data: PurchaseCreate, actor: str) -> IngredientRead:
    ing = session.get(Ingredient, data.ingredient_id)
    if not ing:
        raise NotFound(f"Ingredient #{data.ingredient_id} not found.")
    ing.stock_qty += data.quantity
    session.add(
        StockMovement(
            ingredient_id=ing.id,
            change=data.quantity,
            reason=StockReason.purchase,
            note=data.note,
            created_at=now(),
        )
    )
    audit.record(session, actor, "add_purchase", data.model_dump())
    session.commit()
    session.refresh(ing)
    return to_read(ing, _usage_by_ingredient(session).get(ing.id, Decimal(0)))
