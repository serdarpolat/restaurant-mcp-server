from typing import Annotated, Literal

from fastapi import APIRouter, Query
from sqlmodel import select

from pos_api.db.models import Category, MenuItem
from pos_api.deps import SessionDep
from pos_api.errors import Invalid, NotFound
from pos_api.schemas import CategoryRead, MenuItemDetail, MenuItemRead
from pos_api.text import match_count, matches, query_words

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


def check_category(session, category: str) -> list[str]:
    """The category names meant ("soups" -> ["Çorbalar"]); unknown ones get the valid list
    back, so an agent can retry."""
    names = session.exec(select(Category.name).order_by(Category.sort_order)).all()
    found = [n for n in names if matches(category, n)]
    if not found:
        raise Invalid(f"Unknown category '{category}'. Categories: {', '.join(names)}.")
    return found


@router.get("/categories", response_model=list[CategoryRead])
def list_categories(session: SessionDep):
    cats = session.exec(select(Category).order_by(Category.sort_order)).all()
    return [CategoryRead(id=c.id, name=c.name, item_count=len(c.items)) for c in cats]


@router.get("/items", response_model=list[MenuItemRead])
def list_items(
    session: SessionDep,
    search: Annotated[
        str | None,
        Query(description="Turkish or English words, accent- and typo-tolerant ('adana kebab')"),
    ] = None,
    category: Annotated[str | None, Query(description="Category name")] = None,
    match: Annotated[
        Literal["all", "any"], Query(description="Items matching all search words, or any")
    ] = "all",
    active_only: bool = True,
):
    if category:
        check_category(session, category)
    items = session.exec(select(MenuItem).order_by(MenuItem.category_id, MenuItem.id)).all()
    needed = len(query_words(search)) if search else 0
    found = []
    for item in items:
        if active_only and not item.is_active:
            continue
        if category and not matches(category, item.category.name):
            continue
        rank = (0, 0)
        if search:
            hits = match_count(search, item.name, item.description, item.category.name)
            if hits == 0 or (match == "all" and hits < needed):
                continue
            # Best first: more words matched, then words matched in the item's own name.
            rank = (-hits, -match_count(search, item.name))
        found.append((rank, item))
    found.sort(key=lambda pair: pair[0])  # stable: menu order within a rank
    return [_item_read(item) for _, item in found]


@router.get("/items/{item_id}", response_model=MenuItemDetail)
def get_item(item_id: int, session: SessionDep):
    item = session.get(MenuItem, item_id)
    if not item:
        raise NotFound(f"Menu item #{item_id} not found.")
    return MenuItemDetail(**_item_read(item).model_dump(), modifier_groups=item.modifier_groups)
