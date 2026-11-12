from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Query, status
from sqlmodel import select

from pos_api.db.models import Ingredient, StockMovement, StockReason
from pos_api.deps import ActorDep, SessionDep
from pos_api.errors import NotFound
from pos_api.schemas import IngredientRead, PurchaseCreate, StockMovementRead
from pos_api.services import inventory as service
from pos_api.text import matches
from pos_api.timeutil import now, to_local

router = APIRouter(prefix="/inventory", tags=["inventory"])


@router.get("/ingredients", response_model=list[IngredientRead])
def list_ingredients(
    session: SessionDep,
    below_reorder: Annotated[bool, Query(description="Only items below reorder level")] = False,
    search: str | None = None,
):
    items = service.list_ingredients(session)
    if below_reorder:
        items = [i for i in items if i.below_reorder]
    if search:
        items = [i for i in items if matches(search, i.name)]
    return items


@router.get("/ingredients/{ingredient_id}/movements", response_model=list[StockMovementRead])
def list_movements(
    ingredient_id: int,
    session: SessionDep,
    days: Annotated[int, Query(ge=1, le=90)] = 14,
    reason: StockReason | None = None,
):
    if not session.get(Ingredient, ingredient_id):
        raise NotFound(f"Ingredient #{ingredient_id} not found.")
    stmt = select(StockMovement).where(
        StockMovement.ingredient_id == ingredient_id,
        StockMovement.created_at >= now() - timedelta(days=days),
    )
    if reason:
        stmt = stmt.where(StockMovement.reason == reason)
    rows = session.exec(stmt.order_by(StockMovement.created_at.desc())).all()
    return [
        StockMovementRead.model_validate(m).model_copy(
            update={"created_at": to_local(m.created_at)}
        )
        for m in rows
    ]


@router.post("/purchases", response_model=IngredientRead, status_code=status.HTTP_201_CREATED)
def add_purchase(body: PurchaseCreate, session: SessionDep, actor: ActorDep):
    return service.add_purchase(session, body, actor)
