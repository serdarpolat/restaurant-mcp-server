from typing import Annotated

from fastapi import APIRouter, Query
from sqlmodel import select

from pos_api.db.models import Category, MenuItem
from pos_api.deps import SessionDep
from pos_api.errors import NotFound
from pos_api.schemas import CategoryRead, MenuItemDetail, MenuItemRead
from pos_api.text import matches

router = APIRouter(prefix="/menu", tags=["menu"])


def _item_read(item: MenuItem) -> MenuItemRead:
    return MenuItemRead(
        id=item.id,
        name=item.name,
        description=item.description,
        price=item.price,
        category=item.category.name,
        is_active=item.is_active,
        has_options=bool(item.modifier_groups),
    )


@router.get("/categories", response_model=list[CategoryRead])
def list_categories(session: SessionDep):
    cats = session.exec(select(Category).order_by(Category.sort_order)).all()
    return [CategoryRead(id=c.id, name=c.name, item_count=len(c.items)) for c in cats]


@router.get("/items", response_model=list[MenuItemRead])
def list_items(
    session: SessionDep,
    search: Annotated[str | None, Query(description="Turkish-aware, accent-insensitive")] = None,
    category: Annotated[str | None, Query(description="Category name")] = None,
    active_only: bool = True,
):
    items = session.exec(select(MenuItem).order_by(MenuItem.category_id, MenuItem.id)).all()
    out = []
    for item in items:
        if active_only and not item.is_active:
            continue
        if category and not matches(category, item.category.name):
            continue
        if search and not matches(search, item.name, item.description, item.category.name):
            continue
        out.append(_item_read(item))
    return out


@router.get("/items/{item_id}", response_model=MenuItemDetail)
def get_item(item_id: int, session: SessionDep):
    item = session.get(MenuItem, item_id)
    if not item:
        raise NotFound(f"Menu item #{item_id} not found.")
    return MenuItemDetail(**_item_read(item).model_dump(), modifier_groups=item.modifier_groups)
