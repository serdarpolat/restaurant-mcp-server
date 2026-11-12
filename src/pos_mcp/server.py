"""MCP server exposing the restaurant POS to AI assistants.

Run with:  restaurant-pos-mcp   (stdio transport)

Without POS_API_URL the POS API is embedded in this process (zero setup).
With POS_API_URL it talks to a running POS API over HTTP.
"""

import argparse
import logging
import os
from datetime import datetime
from typing import Annotated, Any, Literal
from zoneinfo import ZoneInfo

from mcp.server.elicitation import ElicitationResult
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.resolve import Elicit, Resolve
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from pos_mcp import api
from pos_mcp.confirmation import Approval, Gate, blocked, gate

RESTAURANT_TZ = ZoneInfo(os.getenv("RESTAURANT_TZ", "Europe/Istanbul"))

INSTRUCTIONS = """\
You are connected to the POS of a Turkish kebab restaurant.

- Currency is Turkish Lira (TRY). All dates and times are restaurant local time.
- Call get_current_time before resolving relative dates such as "yesterday" or "last week".
- Never guess ids. Look up menu items with search_menu, tables with list_tables, and
  options (modifiers) with get_menu_item.
- Some menu items have REQUIRED options (e.g. spice level). If the user did not state one,
  ask them; do not pick for them.
- Tools that cancel, void, take payment or change stock need the user's approval. If a tool
  answers "confirmation_required", show the preview to the user and wait for their answer.
- Report numbers exactly as returned by the tools; do not estimate.
"""

mcp = MCPServer("restaurant-pos", instructions=INSTRUCTIONS)

READ = ToolAnnotations(read_only_hint=True, open_world_hint=False)
WRITE = ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=False)
DESTRUCTIVE = ToolAnnotations(read_only_hint=False, destructive_hint=True, open_world_hint=False)

Date = Annotated[str | None, Field(description="Local date, YYYY-MM-DD. Default: today.")]
ConfirmToken = Annotated[
    str | None,
    Field(description="Token from a previous 'confirmation_required' answer. Omit on first call."),
]


class OrderLine(BaseModel):
    menu_item_id: int = Field(description="Menu item id from search_menu.")
    quantity: int = Field(default=1, ge=1, le=50)
    modifier_ids: list[int] = Field(
        default_factory=list, description="Option ids from get_menu_item (e.g. spice level)."
    )
    note: str = Field(default="", description="Free-text kitchen note, e.g. 'soğansız'.")


def _lines(items: list[OrderLine]) -> list[dict[str, Any]]:
    return [i.model_dump() for i in items]


def _money(value: float) -> str:
    return f"{value:,.2f} TRY"


def _where(order: dict[str, Any]) -> str:
    return order["table"] or order["channel"]


# --------------------------------------------------------------------------- #
# Read tools
# --------------------------------------------------------------------------- #


@mcp.tool(annotations=READ)
async def get_current_time() -> dict[str, str]:
    """Current local date, time and weekday at the restaurant. Use it to resolve relative dates."""
    now = datetime.now(RESTAURANT_TZ)
    return {
        "date": now.date().isoformat(),
        "time": now.strftime("%H:%M"),
        "weekday": now.strftime("%A"),
    }


@mcp.tool(annotations=READ)
async def search_menu(
    query: Annotated[
        str | None, Field(description="Name or keyword, Turkish letters optional ('cay' = 'çay').")
    ] = None,
    category: Annotated[str | None, Field(description="Category name, e.g. 'Kebaplar'.")] = None,
) -> list[dict[str, Any]]:
    """Find menu items (id, name, price, category). Call with no arguments for the whole menu.

    Items with has_options=true have options; call get_menu_item before ordering them.
    """
    return await api.get("/menu/items", search=query, category=category)


@mcp.tool(annotations=READ)
async def get_menu_item(menu_item_id: int) -> dict[str, Any]:
    """Details of one menu item, including option groups (min/max choices) and option ids."""
    return await api.get(f"/menu/items/{menu_item_id}")


@mcp.tool(annotations=READ)
async def list_tables(
    status: Literal["free", "occupied", "reserved"] | None = None,
) -> list[dict[str, Any]]:
    """Tables with area, capacity, status and the open order id (if occupied)."""
    return await api.get("/tables", status=status)


@mcp.tool(annotations=READ)
async def list_orders(
    status: Literal["open", "paid", "cancelled"] | None = None,
    channel: Literal["dine_in", "takeaway", "delivery"] | None = None,
    table_id: int | None = None,
    date_from: Date = None,
    date_to: Date = None,
    limit: Annotated[int, Field(ge=1, le=200)] = 20,
) -> list[dict[str, Any]]:
    """Order headers (no line items), newest first. Defaults to today's orders."""
    return await api.get(
        "/orders",
        status=status,
        channel=channel,
        table_id=table_id,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
    )


@mcp.tool(annotations=READ)
async def get_order(order_id: int) -> dict[str, Any]:
    """One order with its line items (ids, options, notes, void status) and payments."""
    return await api.get(f"/orders/{order_id}")


@mcp.tool(annotations=READ)
async def get_daily_summary(day: Date = None) -> dict[str, Any]:
    """End-of-day (Z) report for one day: sales, discounts, channels, payment methods, voids."""
    return await api.get("/reports/daily-summary", day=day)


@mcp.tool(annotations=READ)
async def get_sales_report(
    date_from: Date = None,
    date_to: Date = None,
    group_by: Literal["day", "hour", "weekday", "channel"] = "day",
) -> dict[str, Any]:
    """Paid sales for a date range, grouped by day, hour of day, weekday or channel.

    Use it for trends and comparisons (e.g. this week vs last week = two calls).
    """
    return await api.get("/reports/sales", date_from=date_from, date_to=date_to, group_by=group_by)


@mcp.tool(annotations=READ)
async def get_top_items(
    date_from: Date = None,
    date_to: Date = None,
    sort: Literal["quantity", "revenue"] = "quantity",
    category: Annotated[str | None, Field(description="Exact category name.")] = None,
    limit: Annotated[int, Field(ge=1, le=50)] = 10,
) -> list[dict[str, Any]]:
    """Best-selling menu items in a date range, by quantity or revenue."""
    return await api.get(
        "/reports/top-items",
        date_from=date_from,
        date_to=date_to,
        sort=sort,
        category=category,
        limit=limit,
    )


@mcp.tool(annotations=READ)
async def get_staff_performance(
    date_from: Date = None, date_to: Date = None
) -> list[dict[str, Any]]:
    """Orders, revenue and average ticket per staff member, highest revenue first."""
    return await api.get("/reports/staff", date_from=date_from, date_to=date_to)


@mcp.tool(annotations=READ)
async def get_void_report(date_from: Date = None, date_to: Date = None) -> list[dict[str, Any]]:
    """Voided/cancelled items by item and reason, with lost value. Useful for loss analysis."""
    return await api.get("/reports/voids", date_from=date_from, date_to=date_to)


@mcp.tool(annotations=READ)
async def get_inventory(
    low_stock_only: Annotated[bool, Field(description="Only items below reorder level.")] = False,
    search: Annotated[str | None, Field(description="Ingredient name filter.")] = None,
) -> list[dict[str, Any]]:
    """Ingredient stock: quantity, reorder level, 7-day average usage and days of cover."""
    return await api.get("/inventory/ingredients", below_reorder=low_stock_only, search=search)


@mcp.tool(annotations=READ)
async def get_stock_movements(
    ingredient_id: int,
    days: Annotated[int, Field(ge=1, le=90)] = 14,
    reason: Literal["sale", "purchase", "waste", "adjustment"] | None = None,
) -> list[dict[str, Any]]:
    """Stock ledger of one ingredient (sales, purchases, waste). Explains WHY stock changed."""
    return await api.get(
        f"/inventory/ingredients/{ingredient_id}/movements", days=days, reason=reason
    )


# --------------------------------------------------------------------------- #
# Write tools (additive, low risk)
# --------------------------------------------------------------------------- #


@mcp.tool(annotations=WRITE)
async def create_order(
    items: list[OrderLine],
    channel: Literal["dine_in", "takeaway", "delivery"] = "dine_in",
    table_id: Annotated[int | None, Field(description="Required for dine_in.")] = None,
) -> dict[str, Any]:
    """Open a new order. Dine-in needs a table without an open order.

    If the table already has an open order, use add_items_to_order instead.
    """
    return await api.post(
        "/orders", {"channel": channel, "table_id": table_id, "items": _lines(items)}
    )


@mcp.tool(annotations=WRITE)
async def add_items_to_order(order_id: int, items: list[OrderLine]) -> dict[str, Any]:
    """Add items to an existing OPEN order (find it via list_tables.open_order_id)."""
    return await api.post(f"/orders/{order_id}/items", {"items": _lines(items)})


@mcp.tool(annotations=WRITE)
async def set_table_status(table_id: int, status: Literal["free", "reserved"]) -> dict[str, Any]:
    """Mark a table without an open order as free or reserved."""
    return await api.patch(f"/tables/{table_id}", {"status": status})


# --------------------------------------------------------------------------- #
# Write tools that need the user's approval
#
# Each tool has a resolver that runs first: it builds a human-readable preview
# and asks for approval (see confirmation.py). The tool body only runs if approved.
# --------------------------------------------------------------------------- #


async def approve_void(
    ctx: Context, order_id: int, order_item_id: int, reason: str, confirmation_token: str | None
) -> Elicit[Approval] | Gate:
    order = await api.get(f"/orders/{order_id}")
    line = next((i for i in order["items"] if i["id"] == order_item_id), None)
    described = f"{line['quantity']} x {line['name']}" if line else f"item #{order_item_id}"
    preview = f"Void {described} on order #{order_id} ({_where(order)}). Reason: {reason}"
    args = {"order_id": order_id, "order_item_id": order_item_id, "reason": reason}
    return gate(ctx, "void_order_item", args, preview, confirmation_token)


@mcp.tool(annotations=DESTRUCTIVE)
async def void_order_item(
    order_id: int,
    order_item_id: Annotated[int, Field(description="Line id from get_order (not menu id).")],
    reason: Annotated[str, Field(description="Why it is voided, e.g. 'Müşteri vazgeçti'.")],
    approval: Annotated[ElicitationResult[Approval], Resolve(approve_void)],
    confirmation_token: ConfirmToken = None,
) -> dict[str, Any]:
    """Void (cancel) one line of an open order. Requires user approval."""
    if (response := blocked(approval)) is not None:
        return response
    return await api.post(f"/orders/{order_id}/items/{order_item_id}/void", {"reason": reason})


async def approve_cancel(
    ctx: Context, order_id: int, reason: str, confirmation_token: str | None
) -> Elicit[Approval] | Gate:
    order = await api.get(f"/orders/{order_id}")
    preview = (
        f"Cancel order #{order_id} ({_where(order)}, {len(order['items'])} lines, "
        f"{_money(order['total'])}). Reason: {reason}"
    )
    args = {"order_id": order_id, "reason": reason}
    return gate(ctx, "cancel_order", args, preview, confirmation_token)


@mcp.tool(annotations=DESTRUCTIVE)
async def cancel_order(
    order_id: int,
    reason: str,
    approval: Annotated[ElicitationResult[Approval], Resolve(approve_cancel)],
    confirmation_token: ConfirmToken = None,
) -> dict[str, Any]:
    """Cancel a whole open order and free its table. Requires user approval."""
    if (response := blocked(approval)) is not None:
        return response
    return await api.post(f"/orders/{order_id}/cancel", {"reason": reason})


async def approve_payment(
    ctx: Context,
    order_id: int,
    method: str,
    discount_percent: float,
    discount_reason: str | None,
    confirmation_token: str | None,
) -> Elicit[Approval] | Gate:
    order = await api.get(f"/orders/{order_id}")
    due = order["subtotal"] * (1 - discount_percent / 100)
    preview = f"Close order #{order_id} ({_where(order)}): charge {_money(due)} by {method}"
    if discount_percent:
        preview += f" after {discount_percent:g}% discount ({discount_reason or 'no reason given'})"
    args = {
        "order_id": order_id,
        "method": method,
        "discount_percent": discount_percent,
        "discount_reason": discount_reason,
    }
    return gate(ctx, "pay_order", args, preview, confirmation_token)


@mcp.tool(annotations=DESTRUCTIVE)
async def pay_order(
    order_id: int,
    method: Literal["cash", "card", "online"],
    approval: Annotated[ElicitationResult[Approval], Resolve(approve_payment)],
    discount_percent: Annotated[float, Field(ge=0, le=50)] = 0,
    discount_reason: Annotated[str | None, Field(description="Required with a discount.")] = None,
    confirmation_token: ConfirmToken = None,
) -> dict[str, Any]:
    """Take payment for an open order and close it (frees the table). Requires user approval."""
    if (response := blocked(approval)) is not None:
        return response
    return await api.post(
        f"/orders/{order_id}/pay",
        {
            "method": method,
            "discount_rate": round(discount_percent / 100, 4),
            "discount_reason": discount_reason,
        },
    )


async def approve_purchase(
    ctx: Context, ingredient_id: int, quantity: float, note: str, confirmation_token: str | None
) -> Elicit[Approval] | Gate:
    matches = [i for i in await api.get("/inventory/ingredients") if i["id"] == ingredient_id]
    name, unit = (matches[0]["name"], matches[0]["unit"]) if matches else (f"#{ingredient_id}", "")
    preview = f"Add {quantity:g} {unit} of {name} to stock. Note: {note}"
    args = {"ingredient_id": ingredient_id, "quantity": quantity, "note": note}
    return gate(ctx, "record_stock_purchase", args, preview, confirmation_token)


@mcp.tool(annotations=WRITE)
async def record_stock_purchase(
    ingredient_id: int,
    quantity: Annotated[float, Field(gt=0, description="In the ingredient's own unit.")],
    approval: Annotated[ElicitationResult[Approval], Resolve(approve_purchase)],
    note: str = "Manuel alım",
    confirmation_token: ConfirmToken = None,
) -> dict[str, Any]:
    """Record received stock for an ingredient (increases stock). Requires user approval."""
    if (response := blocked(approval)) is not None:
        return response
    return await api.post(
        "/inventory/purchases", {"ingredient_id": ingredient_id, "quantity": quantity, "note": note}
    )


# --------------------------------------------------------------------------- #
# Resources & prompts
# --------------------------------------------------------------------------- #


@mcp.resource("restaurant://menu", mime_type="text/markdown")
async def menu_resource() -> str:
    """The full menu as Markdown, grouped by category."""
    items = await api.get("/menu/items")
    lines, category = ["# Menu"], None
    for item in items:
        if item["category"] != category:
            category = item["category"]
            lines.append(f"\n## {category}")
        options = " (has options)" if item["has_options"] else ""
        lines.append(f"- [{item['id']}] {item['name']} - {_money(item['price'])}{options}")
    return "\n".join(lines)


@mcp.prompt()
def daily_briefing() -> str:
    """Morning briefing for the restaurant manager."""
    return (
        "Prepare a short briefing for the restaurant manager. Use the tools to cover: "
        "1) yesterday's sales versus the same weekday last week, 2) yesterday's top 5 items, "
        "3) voids and their reasons, 4) ingredients below reorder level with days of cover and "
        "a suggested purchase list. Be concise, use exact numbers, answer in the user's language."
    )


@mcp.prompt()
def stock_investigation(ingredient: str) -> str:
    """Investigate why an ingredient is running low."""
    return (
        f"Investigate why '{ingredient}' is running low. Check its current stock and days of "
        "cover, then its stock movements (sales, purchases, waste) over the last 14 days, and "
        "which menu items drove the usage. Explain the cause and recommend an action."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Restaurant POS MCP server.")
    parser.add_argument("--http", action="store_true", help="Serve over Streamable HTTP.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()

    logging.getLogger("httpx").setLevel(logging.WARNING)
    if not api.POS_API_URL:
        api.prepare_embedded()
    if args.http:
        mcp.run(transport="streamable-http", host=args.host, port=args.port)
    else:
        mcp.run()


if __name__ == "__main__":
    main()
