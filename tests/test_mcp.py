"""End-to-end tests: MCP client -> MCP server -> POS API -> SQLite, all in-process."""

import httpx
import pytest
from mcp import Client
from mcp.types import ElicitResult
from sqlmodel import Session

from pos_api.db.database import get_session
from pos_api.main import app
from pos_mcp import api
from pos_mcp.server import mcp


@pytest.fixture
async def pos_api(engine):
    """Point the MCP server's HTTP client at the FastAPI app, backed by the test DB."""

    def override():
        with Session(engine) as s:
            yield s

    app.dependency_overrides[get_session] = override
    http = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://pos")
    api.set_client(http)
    yield http
    api.set_client(None)
    await http.aclose()
    app.dependency_overrides.clear()


def data(result):
    assert not result.is_error, result.content
    payload = result.structured_content
    return payload["result"] if set(payload) == {"result"} else payload


async def open_adana_order(client) -> dict:
    adana = data(await client.call_tool("search_menu", {"query": "adana"}))[0]
    detail = data(await client.call_tool("get_menu_item", {"menu_item_id": adana["id"]}))
    spice = next(g for g in detail["modifier_groups"] if g["name"] == "Acı Seviyesi")
    table = data(await client.call_tool("list_tables", {"status": "free"}))[0]
    line = {
        "menu_item_id": adana["id"],
        "quantity": 2,
        "modifier_ids": [spice["modifiers"][0]["id"]],
    }
    return data(await client.call_tool("create_order", {"table_id": table["id"], "items": [line]}))


async def test_tools_are_listed_with_safety_annotations(pos_api):
    async with Client(mcp) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
    assert len(tools) == 20
    assert tools["get_sales_report"].annotations.read_only_hint is True
    assert tools["cancel_order"].annotations.destructive_hint is True
    assert all(t.description for t in tools.values())


async def test_search_and_reports(pos_api):
    async with Client(mcp) as client:
        items = data(await client.call_tool("search_menu", {"query": "iskender"}))
        assert [i["name"] for i in items] == ["İskender"]
        low = data(await client.call_tool("get_inventory", {"low_stock_only": True}))
        assert low and all(i["below_reorder"] for i in low)
        summary = data(await client.call_tool("get_daily_summary", {}))
        assert "net_sales" in summary


async def test_api_errors_reach_the_model_with_recovery_hints(pos_api):
    async with Client(mcp) as client:
        adana = data(await client.call_tool("search_menu", {"query": "adana"}))[0]
        result = await client.call_tool(
            "create_order", {"channel": "takeaway", "items": [{"menu_item_id": adana["id"]}]}
        )
    assert result.is_error
    message = result.content[0].text
    assert "Acı Seviyesi" in message and "Acısız" in message


async def test_cancel_needs_token_and_token_is_bound_to_arguments(pos_api):
    async with Client(mcp) as client:
        order = await open_adana_order(client)
        args = {"order_id": order["id"], "reason": "Müşteri gitti"}

        first = data(await client.call_tool("cancel_order", args))
        assert first["status"] == "confirmation_required"
        assert f"#{order['id']}" in first["preview"]
        assert (
            data(await client.call_tool("get_order", {"order_id": order["id"]}))["status"] == "open"
        )

        # A token issued for one action cannot be reused for different arguments.
        tampered = args | {
            "reason": "Başka sebep",
            "confirmation_token": first["confirmation_token"],
        }
        assert (
            data(await client.call_tool("cancel_order", tampered))["status"]
            == "confirmation_invalid"
        )

        fresh = data(await client.call_tool("cancel_order", args))
        done = data(
            await client.call_tool(
                "cancel_order", args | {"confirmation_token": fresh["confirmation_token"]}
            )
        )
        assert done["status"] == "cancelled"


@pytest.mark.parametrize(("approve", "expected"), [(True, "paid"), (False, "open")])
async def test_elicitation_asks_the_user_directly(pos_api, approve, expected):
    asked = []

    async def user(context, params):
        asked.append(params.message)
        return ElicitResult(action="accept", content={"approve": approve})

    async with Client(mcp, elicitation_callback=user) as client:
        order = await open_adana_order(client)
        result = data(
            await client.call_tool("pay_order", {"order_id": order["id"], "method": "card"})
        )
        after = data(await client.call_tool("get_order", {"order_id": order["id"]}))

    assert len(asked) == 1 and "charge" in asked[0]
    assert after["status"] == expected
    assert result["status"] == ("paid" if approve else "declined")


async def test_writes_are_audited_with_the_mcp_actor(pos_api):
    async with Client(mcp) as client:
        await open_adana_order(client)
    log = (await pos_api.get("/audit-log", params={"actor": api.ACTOR})).json()
    assert log[0]["action"] == "create_order"


async def test_menu_resource_and_prompts(pos_api):
    async with Client(mcp) as client:
        menu = await client.read_resource("restaurant://menu")
        prompts = {p.name for p in (await client.list_prompts()).prompts}
    assert "Adana Kebap" in menu.contents[0].text
    assert prompts == {"daily_briefing", "stock_investigation"}
