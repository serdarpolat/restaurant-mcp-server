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
    return data(
        await client.call_tool("create_order", {"table_id": table["table_id"], "items": [line]})
    )


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


async def test_search_menu_falls_back_to_closest_items_with_a_note(pos_api):
    async with Client(mcp) as client:
        exact = data(await client.call_tool("search_menu", {"query": "adana kebab"}))
        assert exact[0]["name"] == "Adana Kebap"
        close = data(await client.call_tool("search_menu", {"query": "adana dürüm"}))
        assert close["items"][0]["name"] == "Adana Kebap"
        assert "ask the user" in close["note"]
        none = data(await client.call_tool("search_menu", {"query": "sushi"}))
        assert none["items"] == [] and "one key word" in none["note"]


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
        assert "Stock is not returned" in first["preview"]
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

        # Changing return_to_stock also invalidates the token.
        token = data(await client.call_tool("cancel_order", args))["confirmation_token"]
        restock = args | {"return_to_stock": True, "confirmation_token": token}
        assert (
            data(await client.call_tool("cancel_order", restock))["status"]
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


async def test_reports_echo_the_period_they_cover(pos_api):
    async with Client(mcp) as client:
        today = data(await client.call_tool("get_current_time", {}))["date"]
        top = data(await client.call_tool("get_top_items", {"limit": 3}))
        day = data(await client.call_tool("get_void_report", {"date_from": today}))
    # no dates = today only, and the answer says so
    assert top["period"] == {"date_from": today, "date_to": today}
    assert len(top["items"]) <= 3
    assert day["period"] == {"date_from": today, "date_to": today}


async def test_instructions_and_parameter_hints_reach_the_model(pos_api):
    async with Client(mcp) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
    props = tools["get_stock_movements"].input_schema["properties"]
    assert "get_inventory" in props["ingredient_id"]["description"]
    assert (
        "list_tables"
        in tools["set_table_status"].input_schema["properties"]["table_id"]["description"]
    )


async def test_impossible_dates_are_refused_with_a_hint(pos_api):
    async with Client(mcp) as client:
        today = data(await client.call_tool("get_current_time", {}))["date"]
        year = int(today[:4])
        old = await client.call_tool("get_void_report", {"date_from": f"{year - 2}{today[4:]}"})
        future = await client.call_tool("get_top_items", {"date_from": f"{year + 1}-01-01"})
        bad = await client.call_tool("get_daily_summary", {"day": "dün"})
    assert old.is_error and f"Did you mean {today}" in old.content[0].text
    assert future.is_error and today in future.content[0].text
    assert bad.is_error and "YYYY-MM-DD" in bad.content[0].text


async def test_ids_are_checked_against_the_name_the_user_said(pos_api):
    async with Client(mcp) as client:
        tables = data(await client.call_tool("list_tables", {}))
        teras = next(t for t in tables if t["name"] == "Teras 1")
        other = next(t for t in tables if t["name"] != "Teras 1")
        wrong = await client.call_tool(
            "set_table_status",
            {"table_id": other["table_id"], "table_name": "Teras 1", "status": "reserved"},
        )
        right = await client.call_tool(
            "set_table_status",
            {"table_id": teras["table_id"], "table_name": "teras 1", "status": "reserved"},
        )
        kiyma = data(await client.call_tool("get_inventory", {"search": "kıyma"}))[0]
        guessed = await client.call_tool(
            "get_stock_movements",
            {"ingredient_id": kiyma["ingredient_id"] + 1, "ingredient_name": "Dana Kıyma"},
        )
        purchase = await client.call_tool(
            "record_stock_purchase",
            {
                "ingredient_id": kiyma["ingredient_id"] + 1,
                "ingredient_name": "Dana Kıyma",
                "quantity": 10,
            },
        )
    assert wrong.is_error
    assert f"'Teras 1' is table_id {teras['table_id']}" in wrong.content[0].text
    assert data(right)["status"] == "reserved"
    assert "id" not in kiyma
    for result in (guessed, purchase):  # nothing previewed or changed for the wrong item
        assert result.is_error
        assert f"= ingredient_id {kiyma['ingredient_id']}" in result.content[0].text


async def test_tokens_survive_a_server_restart_and_rejections_explain_themselves(pos_api, tmp_path):
    """LM Studio may reach the server through a new process between preview and approval."""
    from pos_mcp import confirmation

    async with Client(mcp) as client:
        order = await open_adana_order(client)
        args = {"order_id": order["id"], "reason": "Müşteri gitti", "return_to_stock": True}
        first = data(await client.call_tool("cancel_order", args))
        token = first["confirmation_token"]
        # the pending token lives on disk, so a new server process can still accept it
        assert token in confirmation._store_path().read_text(encoding="utf-8")

        changed = data(
            await client.call_tool(
                "cancel_order", args | {"reason": "Başka", "confirmation_token": token}
            )
        )
        assert changed["status"] == "confirmation_invalid"
        assert "reason ('Müşteri gitti' -> 'Başka')" in changed["message"]
        assert "Başka" in changed["preview"]  # a fresh preview for what was actually sent

        unknown = data(
            await client.call_tool("cancel_order", args | {"confirmation_token": "nope"})
        )
        assert unknown["status"] == "confirmation_invalid"
        assert "unknown" in unknown["message"]
        assert (
            data(await client.call_tool("get_order", {"order_id": order["id"]}))["status"] == "open"
        )

        # the fresh token from a rejection works, once
        again = args | {"confirmation_token": unknown["confirmation_token"]}
        assert data(await client.call_tool("cancel_order", again))["status"] == "cancelled"
        reused = await client.call_tool("cancel_order", again)
        assert data(reused)["status"] == "confirmation_invalid"
