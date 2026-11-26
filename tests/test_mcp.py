"""End-to-end tests: MCP client -> MCP server -> POS API -> SQLite, all in-process."""

from datetime import date, timedelta

import httpx
import pytest
from mcp import Client as _Client
from mcp.types import ElicitResult
from sqlmodel import Session

from pos_api.db.database import get_session
from pos_api.main import app
from pos_mcp import api
from pos_mcp.server import mcp

WRITE_TOOLS = {
    "create_order",
    "add_items_to_order",
    "set_table_status",
    "void_order_item",
    "cancel_order",
    "pay_order",
    "record_stock_purchase",
}


class Client(_Client):
    """The MCP client, as a model that copies the user's message into write tools (an
    English one unless a test passes its own)."""

    async def call_tool(self, name, arguments=None, *args, **kwargs):
        if name in WRITE_TOOLS and arguments is not None:
            arguments = {"user_message": "Please do it.", **arguments}
        return await super().call_tool(name, arguments, *args, **kwargs)


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
    spice = next(g for g in detail["modifier_groups"] if g["name"] == "Spice Level")
    table = data(await client.call_tool("list_tables", {"status": "free"}))[0]
    line = {
        "name": "Adana Kebab",
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
        assert [i["name"] for i in items] == ["Iskender Kebab"]
        low = data(await client.call_tool("get_inventory", {"low_stock_only": True}))
        assert low and all(i["below_reorder"] for i in low)
        summary = data(await client.call_tool("get_daily_summary", {}))
        assert "net_sales" in summary


async def test_search_menu_falls_back_to_closest_items_with_a_note(pos_api):
    async with Client(mcp) as client:
        exact = data(await client.call_tool("search_menu", {"query": "adana kebab"}))
        assert exact[0]["name"] == "Adana Kebab"
        close = data(await client.call_tool("search_menu", {"query": "adana dürüm"}))
        assert close["items"][0]["name"] == "Adana Kebab"
        assert "ask the user" in close["note"]
        none = data(await client.call_tool("search_menu", {"query": "sushi"}))
        assert none["items"] == [] and "one key word" in none["note"]


async def test_api_errors_reach_the_model_with_recovery_hints(pos_api):
    async with Client(mcp) as client:
        adana = data(await client.call_tool("search_menu", {"query": "adana"}))[0]
        result = await client.call_tool(
            "create_order",
            {"channel": "pickup", "items": [{"name": "Adana", "menu_item_id": adana["id"]}]},
        )
    assert result.is_error
    message = result.content[0].text
    # a missing required choice is a question for the user, written by the server
    assert "NOT SAVED" in message and "ASK_USER: Spice Level for the Adana Kebab" in message
    assert "Not Spicy" in message


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
        approved = {"confirmation_token": fresh["confirmation_token"], "user_reply": "Evet"}
        done = data(await client.call_tool("cancel_order", args | approved))
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
            await client.call_tool("pay_order", {"order_id": order["id"], "method": "credit_card"})
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
    assert "Adana Kebab" in menu.contents[0].text
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


async def test_read_tools_hint_the_language_only_when_given_user_message(pos_api):
    """Report-style read tools return data, not a sentence to copy, so unlike write tools the
    language hint is opt-in: no reminder without user_message, and none either when its
    language cannot be told (too short or mixed)."""
    async with Client(mcp) as client:
        tr = data(
            await client.call_tool(
                "get_sales_report", {"user_message": "Bu haftanın saatlik satışları ne?"}
            )
        )
        en = data(await client.call_tool("get_top_items", {"user_message": "What sold the most?"}))
        bare = data(await client.call_tool("get_void_report", {}))
        unclear = data(await client.call_tool("get_daily_summary", {"user_message": "ok"}))
    assert tr["answer_the_user_in"] == "Turkish"
    assert en["answer_the_user_in"] == "English"
    assert "answer_the_user_in" not in bare
    assert "answer_the_user_in" not in unclear


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
        bad = await client.call_tool("get_daily_summary", {"day": "geçen salı"})
        yesterday = data(await client.call_tool("get_top_items", {"date_from": "dün"}))
        week = data(
            await client.call_tool("get_void_report", {"date_from": "-7", "date_to": "today"})
        )
        reversed_orders = await client.call_tool(
            "list_orders", {"date_from": today, "date_to": "-7"}
        )
        reversed_top = await client.call_tool(
            "get_top_items", {"date_from": today, "date_to": "yesterday"}
        )
    assert old.is_error and f"Did you mean {today}" in old.content[0].text
    assert future.is_error and today in future.content[0].text
    assert bad.is_error and "YYYY-MM-DD" in bad.content[0].text
    # relative days need no date arithmetic from the model
    day_before = (date.fromisoformat(today) - timedelta(days=1)).isoformat()
    assert yesterday["period"] == {"date_from": day_before, "date_to": day_before}
    week_ago = (date.fromisoformat(today) - timedelta(days=7)).isoformat()
    assert week["period"] == {"date_from": week_ago, "date_to": today}
    # a reversed range is refused, not silently swapped (it used to just swap the two)
    assert reversed_orders.is_error
    assert "date_from" in reversed_orders.content[0].text
    assert "date_to" in reversed_orders.content[0].text
    assert reversed_top.is_error and "date_to" in reversed_top.content[0].text


async def test_ids_are_checked_against_the_name_the_user_said(pos_api):
    async with Client(mcp) as client:
        tables = data(await client.call_tool("list_tables", {}))
        teras = next(t for t in tables if t["name"] == "Terrace 1")
        other = next(t for t in tables if t["name"] != "Terrace 1")
        wrong = await client.call_tool(
            "set_table_status",
            {"table_id": other["table_id"], "table_name": "Terrace 1", "status": "reserved"},
        )
        right = await client.call_tool(
            "set_table_status",
            {"table_id": teras["table_id"], "table_name": "terrace 1", "status": "reserved"},
        )
        kiyma = data(await client.call_tool("get_inventory", {"search": "ground beef"}))[0]
        guessed = await client.call_tool(
            "get_stock_movements",
            {"ingredient_id": kiyma["ingredient_id"] + 1, "ingredient_name": "Ground Beef"},
        )
        purchase = await client.call_tool(
            "record_stock_purchase",
            {
                "ingredient_id": kiyma["ingredient_id"] + 1,
                "ingredient_name": "Ground Beef",
                "quantity": 10,
            },
        )
    assert wrong.is_error
    assert f"'Terrace 1' is table_id {teras['table_id']}" in wrong.content[0].text
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
        again = args | {"confirmation_token": unknown["confirmation_token"], "user_reply": "yes"}
        assert data(await client.call_tool("cancel_order", again))["status"] == "cancelled"
        reused = await client.call_tool("cancel_order", again)
        # a used token on a now-cancelled order: refused before any new preview
        assert reused.is_error and "is cancelled" in reused.content[0].text


# ----------------------------------------------------------------- v5: live-chat findings


async def call(client, tool, args):
    result = await client.call_tool(tool, args)
    return result, (result.content[0].text if result.is_error else data(result))


async def test_order_lines_by_name_and_option_names(pos_api):
    async with Client(mcp) as client:
        order = data(
            await client.call_tool(
                "create_order",
                {
                    "table_name": "Hall 4",
                    "items": [
                        {"name": "adana kebab", "options": ["spicy"]},
                        {"name": "Adana Kebab", "options": ["not spicy", "Acısız"]},
                        {"name": "lahmajun", "quantity": 3, "options": ["Acısız"]},
                        {"name": "Ayran", "options": ["large"]},
                    ],
                },
            )
        )
    assert order["table"] == "Hall 4"
    assert order["summary"].startswith(f"OPENED order #{order['id']} on Hall 4: ")
    got = sorted((i["name"], i["quantity"], i["modifiers"]) for i in order["items"])
    assert got == [
        ("Adana Kebab", 1, "Not Spicy"),
        ("Adana Kebab", 1, "Spicy"),
        ("Ayran", 1, "Large"),
        ("Lahmacun", 3, "Not Spicy"),
    ]


async def test_a_remembered_id_that_does_not_match_the_name_is_refused(pos_api):
    async with Client(mcp) as client:
        adana = data(await client.call_tool("search_menu", {"query": "adana"}))[0]
        line = {"name": "Lahmacun", "menu_item_id": adana["id"], "options": ["Acısız"]}
        result, text = await call(
            client, "create_order", {"table_name": "Garden 2", "items": [line]}
        )
        assert result.is_error and text.count("NOT SAVED") == 1
        assert "is 'Adana Kebab', not 'Lahmacun'" in text and "'Lahmacun' (menu_item_id" in text
        result, text = await call(
            client, "create_order", {"channel": "pickup", "items": [{"name": "kebap"}]}
        )
        assert result.is_error and "Ask the user which one" in text
        result, text = await call(
            client,
            "create_order",
            {"channel": "pickup", "items": [{"name": "Cola", "size": "L"}]},
        )
        assert result.is_error  # unknown fields are refused, not silently dropped
        result, text = await call(
            client,
            "create_order",
            {"channel": "pickup", "items": [{"name": "Ayran", "options": ["iced"]}]},
        )
        assert result.is_error and "Large" in text


async def test_orders_go_to_the_named_table_whatever_order_id_was_remembered(pos_api):
    """Seen in LM Studio: "Garden 3'e ... ekle" went to the previous table's order id."""
    async with Client(mcp) as client:
        order = await open_adana_order(client)  # on the first free table
        table = order["table"]
        # an order id from earlier in a chat does not matter for a table: the name decides
        ok = data(
            await client.call_tool(
                "add_items_to_order",
                {
                    "order_id": order["id"] + 1000,
                    "table_name": table,
                    "items": [{"name": "Tea", "quantity": 2}],
                },
            )
        )
        assert ok["id"] == order["id"]
        assert ok["summary"].startswith(f"ADDED to {table}'s open order #{order['id']}")
        assert "2 x Tea" in ok["summary"] and "Adana" not in ok["summary"]
        # "add" to a table without an order opens one there
        teras = data(
            await client.call_tool(
                "add_items_to_order", {"table_name": "Terrace 2", "items": [{"name": "Water"}]}
            )
        )
        assert teras["table"] == "Terrace 2" and teras["summary"].startswith("OPENED order #")
        # "open" on a table that already has an order adds to it (no second order, no error)
        again = data(
            await client.call_tool(
                "create_order", {"table_name": "Terrace 2", "items": [{"name": "Cola"}]}
            )
        )
        assert again["id"] == teras["id"] and again["summary"].startswith("ADDED to Terrace 2")
        # get_order by table name: no order id needed for "what is Terrace 2's bill"
        bill = data(await client.call_tool("get_order", {"table_name": "terrace 2"}))
        assert bill["id"] == teras["id"] and len(bill["items"]) == 2
        result, text = await call(
            client,
            "create_order",
            {"channel": "pickup", "table_name": "Terrace 2", "items": [{"name": "Water"}]},
        )
        assert result.is_error and "no table" in text


async def test_a_table_the_user_did_not_say_is_refused(pos_api):
    """Found testing live: table_name/table_id is trusted with no check against what the
    user actually said, unlike every other argument (quantities, options, channel). A model
    that mixes up two tables - or still has a stale table_id from earlier in the chat - used
    to open or add to the WRONG table's bill without a word of complaint."""
    async with Client(mcp) as client:
        wrong, text = await call(
            client,
            "create_order",
            {
                "table_name": "Hall 4",  # the model's argument...
                "items": [{"name": "Ayran", "quantity": 1}],
                "user_message": "Terrace 2'ye 1 ayran aç.",  # ...does not match the user's words
            },
        )
        assert wrong.is_error
        assert "user said 'Terrace 2', not 'Hall 4'" in text
        assert "table_name='Terrace 2'" in text
        # the same table_id taken from an earlier turn, now stale
        hall4 = next(
            t for t in data(await client.call_tool("list_tables", {})) if t["name"] == "Hall 4"
        )
        stale_id, text = await call(
            client,
            "create_order",
            {
                "table_id": hall4["table_id"],
                "items": [{"name": "Ayran", "quantity": 1}],
                "user_message": "Terrace 2'ye 1 ayran aç.",
            },
        )
        assert stale_id.is_error and "user said 'Terrace 2', not 'Hall 4'" in text
        # add_items_to_order is checked the same way
        wrong_add, text = await call(
            client,
            "add_items_to_order",
            {
                "table_name": "Hall 4",
                "items": [{"name": "Ayran", "quantity": 1}],
                "user_message": "Terrace 2'ye 1 ayran ekle.",
            },
        )
        assert wrong_add.is_error and "user said 'Terrace 2', not 'Hall 4'" in text
        # the matching table still works
        ok = data(
            await client.call_tool(
                "create_order",
                {
                    "table_name": "Terrace 2",
                    "items": [{"name": "Ayran", "quantity": 1}],
                    "user_message": "Terrace 2'ye 1 ayran aç.",
                },
            )
        )
        assert ok["table"] == "Terrace 2"
        # a message naming no table at all (an answer, a generic "add it") is never held
        # against the caller's table_name - same conservative rule as quantities()
        ok2 = data(
            await client.call_tool(
                "add_items_to_order",
                {
                    "table_name": "Terrace 2",
                    "items": [{"name": "Tea", "quantity": 1}],
                    "user_message": "evet, ekleyin",
                },
            )
        )
        assert ok2["table"] == "Terrace 2"


async def test_cancel_void_pay_are_checked_against_the_table_the_user_said(pos_api):
    """Found testing live: create_order/add_items_to_order check table_name against the
    user's words (test_a_table_the_user_did_not_say_is_refused above), but cancel_order,
    void_order_item and pay_order take order_id, not table_name, so that guard never ran
    for them. A stale or hallucinated order_id from earlier in the chat could act on the
    wrong table's order: "cancel the order on Garden 2" ran against an order_id that was
    actually Hall 3's, with no table ever opened on Garden 2 at all."""
    async with Client(mcp) as client:
        order = data(
            await client.call_tool(
                "create_order",
                {
                    "table_name": "Hall 4",
                    "items": [{"name": "Ayran", "quantity": 1}],
                    "user_message": "Hall 4'e 1 ayran aç.",
                },
            )
        )
        line_id = order["items"][0]["id"]
        args = {"order_id": order["id"], "reason": "x"}

        wrong_void, text = await call(
            client,
            "void_order_item",
            {
                **args,
                "order_item_id": line_id,
                "user_message": "Remove the ayran from the order on Terrace 2.",
            },
        )
        assert wrong_void.is_error
        assert "user said 'Terrace 2'" in text and f"order #{order['id']}" in text

        wrong_cancel, text = await call(
            client, "cancel_order", {**args, "user_message": "Cancel the order on Terrace 2."}
        )
        assert wrong_cancel.is_error and "user said 'Terrace 2'" in text

        wrong_pay, text = await call(
            client,
            "pay_order",
            {
                "order_id": order["id"],
                "method": "cash",
                "user_message": "Take cash for the Terrace 2 bill.",
            },
        )
        assert wrong_pay.is_error and "user said 'Terrace 2'" in text

        # the matching table still works, and still asks for approval as usual
        ok = data(
            await client.call_tool(
                "cancel_order", {**args, "user_message": "Cancel the order on Hall 4."}
            )
        )
        assert ok["status"] == "confirmation_required"
        # a message naming no table at all is never held against the real order_id
        ok2 = data(await client.call_tool("cancel_order", {**args, "user_message": "Cancel it."}))
        assert ok2["status"] == "confirmation_required"


async def test_table_names_match_whole_words(pos_api):
    async with Client(mcp) as client:
        tables = data(await client.call_tool("list_tables", {}))
        hall1 = next(t for t in tables if t["name"] == "Hall 1")
        result, text = await call(
            client,
            "set_table_status",
            {"table_id": hall1["table_id"], "table_name": "Hall 10", "status": "reserved"},
        )
        assert result.is_error and "no table is named 'Hall 10'" in text
        for said in ("hall1", "Hall 1 masası"):
            data(
                await client.call_tool(
                    "set_table_status",
                    {"table_id": hall1["table_id"], "table_name": said, "status": "free"},
                )
            )


async def test_impossible_actions_fail_before_the_approval_step(pos_api):
    async with Client(mcp) as client:
        order = await open_adana_order(client)
        today = data(await client.call_tool("get_current_time", {}))["date"]
        week_ago = (date.fromisoformat(today) - timedelta(days=6)).isoformat()
        paid_args = {"status": "paid", "limit": 1, "date_from": week_ago, "date_to": today}
        paid = data(await client.call_tool("list_orders", paid_args))[0]  # any time of day
        result, text = await call(client, "cancel_order", {"order_id": paid["id"], "reason": "x"})
        assert result.is_error and "is paid" in text
        result, text = await call(
            client,
            "void_order_item",
            {"order_id": order["id"], "order_item_id": 999999, "reason": "x"},
        )
        assert result.is_error and "Active lines:" in text and "Adana Kebab (Spicy)" in text
        line = order["items"][0]["id"]
        preview = data(
            await client.call_tool(
                "void_order_item", {"order_id": order["id"], "order_item_id": line, "reason": "x"}
            )
        )["preview"]
        assert "Adana Kebab (Spicy)" in preview
        result, text = await call(
            client, "pay_order", {"order_id": order["id"], "method": "cash", "discount_percent": 10}
        )
        assert result.is_error and "discount_reason" in text
        inv = data(await client.call_tool("get_inventory", {"search": "ground beef"}))[0]
        args = {
            "ingredient_id": inv["ingredient_id"],
            "ingredient_name": inv["name"],
            "quantity": 1_000_000,
        }
        result, text = await call(client, "record_stock_purchase", args)
        assert result.is_error and "1,000,000" in text and "e+" not in text


async def test_english_category_in_reports(pos_api):
    async with Client(mcp) as client:
        today = data(await client.call_tool("get_current_time", {}))["date"]
        yesterday = (date.fromisoformat(today) - timedelta(days=1)).isoformat()
        args = {"category": "drinks", "date_from": yesterday}
        top = data(await client.call_tool("get_top_items", args))
        assert top["items"] and {i["category"] for i in top["items"]} == {"Beverages"}


async def test_a_token_does_not_run_the_action_when_the_user_said_no(pos_api):
    """Seen in LM Studio: "Hayır, tüm siparişi iptal etme!" and the model used the token."""
    async with Client(mcp) as client:
        order = await open_adana_order(client)
        args = {"order_id": order["id"], "reason": "Yanlış masa"}

        async def status():
            return data(await client.call_tool("get_order", {"order_id": order["id"]}))["status"]

        for reply in ("Hayır, tüm siparişi iptal etme!", "onaylamıyorum", "wait", None, "hmm"):
            token = data(await client.call_tool("cancel_order", args))["confirmation_token"]
            sent = args | {"confirmation_token": token}
            if reply is not None:
                sent["user_reply"] = reply
            answer = data(await client.call_tool("cancel_order", sent))
            assert answer["status"] == "not_approved", reply
            assert await status() == "open"
        assert (
            "user_reply is missing"
            in data(
                await client.call_tool(
                    "cancel_order",
                    args
                    | {
                        "confirmation_token": data(await client.call_tool("cancel_order", args))[
                            "confirmation_token"
                        ]
                    },
                )
            )["message"]
        )

        token = data(await client.call_tool("cancel_order", args))["confirmation_token"]
        done = args | {"confirmation_token": token, "user_reply": "CONFIRM"}
        assert data(await client.call_tool("cancel_order", done))["status"] == "cancelled"


@pytest.mark.parametrize(
    "reply",
    [
        "onaylamıyorum",  # bare "etme"/"yapma" aren't the only negative forms: Turkish
        "onaylamayın",  # negates a verb with an infix ("-ma-/-me-"), not a separate word
        "onaylamadım",  # like English "not" - these all contain _YES's own "onay", and
        "hiç onaylamıyorum bunu",  # none of them is "Hayır, ... iptal etme!", the one
        "kabul etmiyorum",  # phrasing the original LM Studio bug report happened to use.
        "kabul etmeyin",
        "kabul etmem",
        "yapmayın",
        "istemiyorum",
    ],
)
def test_turkish_negated_verbs_are_not_mistaken_for_approval(reply):
    """A gap found by reading confirmation.py, not from a bug report: each of these reads
    as a refusal to a person, but used to come back approved() == True."""
    from pos_mcp.confirmation import approves

    assert not approves(reply), reply


@pytest.mark.parametrize(
    "reply",
    [
        "evet ama iptal etme",  # a "yes" followed by a refusal of the actual action: a
        "evet ama onaylamıyorum, vazgeçtim",  # person reading this would not take it as
        "tamam ama yapma",  # approval, and a model could otherwise read the bare "evet"/
        "onaylıyorum ama hayır",  # "tamam"/"onaylıyorum" and run the action anyway.
        "yes but actually don't void it, I changed my mind again",
        "yes but no, cancel that",
        "sure, but don't do it",
    ],
)
def test_a_yes_followed_by_a_refusal_is_not_approved(reply):
    """'Evet ama iptal etme' / "yes but don't do it": a live adversarial test tried to send
    this to a real confirmation preview to check it, but could not (fabricating a user's
    approval reply is correctly refused by the calling agent's own permission layer).
    Covered here directly against approves() instead; the module docstring already claims
    "a refusal anywhere wins over a yes" (confirmation.py:138) but this exact compound
    pattern had no test of its own."""
    from pos_mcp.confirmation import approves

    assert not approves(reply), reply


# --------------------------------------------------------------------------- #
# reply_language: what write tools say back is in the user's language
# --------------------------------------------------------------------------- #


async def test_write_results_are_in_the_users_language(pos_api):
    line = {"name": "Adana Kebab", "quantity": 1, "options": ["spicy"]}
    async with Client(mcp) as client:
        tr = data(
            await client.call_tool(
                "create_order",
                {"table_name": "Hall 1", "items": [line], "user_message": "Hall 1'e acılı Adana"},
            )
        )
        en = data(
            await client.call_tool(
                "create_order",
                {"table_name": "Hall 1", "items": [line], "user_message": "Add a spicy Adana"},
            )
        )
        de = data(
            await client.call_tool(
                "create_order",
                # German is not detected: the model's reply_language decides
                {
                    "channel": "pickup",
                    "items": [line],
                    "user_message": "Einmal Adana zum Mitnehmen",
                    "reply_language": "de",
                },
            )
        )
    assert tr["summary"].startswith("AÇILDI: Hall 1 için")
    assert "1 x Adana Kebab (Spicy = acılı)" in tr["summary"] and "Sipariş toplamı" in tr["summary"]
    assert en["summary"].startswith("ADDED to Hall 1's open order")
    assert "1 x Adana Kebab (Spicy)" in en["summary"] and "Order total" in en["summary"]
    # other languages: English text, and an explicit language to answer in
    assert de["summary"].startswith("OPENED pickup order")
    assert (tr["answer_the_user_in"], en["answer_the_user_in"]) == ("Turkish", "English")
    assert de["answer_the_user_in"] == "German"
    assert list(en)[-1] == "answer_the_user_in"  # read last, after the Turkish data


async def test_user_message_is_required_on_write_tools(pos_api):
    async with _Client(mcp) as client:  # the plain client: no user_message added
        tools = {t.name: t for t in (await client.list_tools()).tools}
        for name in WRITE_TOOLS:
            assert "user_message" in tools[name].input_schema["required"], name
            assert "reply_language" not in tools[name].input_schema["required"], name
        result = await client.call_tool(
            "create_order", {"table_name": "Hall 1", "items": [{"name": "Ayran"}]}
        )
    assert result.is_error and "user_message" in result.content[0].text


async def test_the_users_words_beat_the_models_language_guess(pos_api):
    """Seen in v6.3: the model wrote reply_language='tr' for English requests."""
    async with Client(mcp) as client:
        result = data(
            await client.call_tool(
                "create_order",
                {
                    "table_name": "Hall 2",
                    "items": [{"name": "Tea", "quantity": 2}],
                    "user_message": "Add two teas to Hall 2.",
                    "reply_language": "tr",
                },
            )
        )
        short = data(
            await client.call_tool(
                "create_order",
                {
                    "table_name": "Hall 2",
                    "items": [{"name": "Tea"}],
                    "user_message": "ok",  # too short to tell: reply_language decides
                    "reply_language": "tr",
                },
            )
        )
    assert result["summary"].startswith("OPENED") and result["answer_the_user_in"] == "English"
    assert short["summary"].startswith("EKLENDİ") and short["answer_the_user_in"] == "Turkish"


async def test_approval_preview_and_question_in_the_users_language(pos_api):
    async with Client(mcp) as client:
        order = await open_adana_order(client)
        args = {"order_id": order["id"], "reason": "Müşteri gitti", "return_to_stock": True}
        tr = data(
            await client.call_tool("cancel_order", args | {"user_message": "Siparişi iptal et"})
        )
        en = data(
            await client.call_tool("cancel_order", args | {"user_message": "Cancel the order"})
        )
        assert tr["preview"].startswith(f"#{order['id']} numaralı sipariş")
        assert "Malzemeler stoğa geri eklenecek" in tr["preview"]
        assert tr["ask_user"] == "Onaylıyor musunuz? (evet / hayır)"
        assert en["preview"].startswith(f"Cancel order #{order['id']}")
        assert en["ask_user"] == "Do you approve? (yes / no)"
        assert "in English" in en["message"] and en["answer_the_user_in"] == "English"

        # the language is not part of what is approved: a token from the Turkish preview
        # works when the user answers in English
        approved = {"confirmation_token": tr["confirmation_token"], "user_reply": "yes"}
        done = data(
            await client.call_tool("cancel_order", args | approved | {"user_message": "yes"})
        )
    assert done["status"] == "cancelled"
    assert done["summary"].startswith(f"CANCELLED order #{order['id']}")


async def test_elicitation_asks_in_the_users_language(pos_api):
    asked = []

    async def user(context, params):
        asked.append(params.message)
        return ElicitResult(action="accept", content={"approve": True})

    async with Client(mcp, elicitation_callback=user) as client:
        order = await open_adana_order(client)
        paid = data(
            await client.call_tool(
                "pay_order",
                {
                    "order_id": order["id"],
                    "method": "credit_card",
                    "user_message": "Kartla kapat",
                },
            )
        )
    assert "kredi kartı ile" in asked[0] and asked[0].endswith("Onaylıyor musunuz? (evet / hayır)")
    assert paid["summary"].startswith("ÖDENDİ") and paid["answer_the_user_in"] == "Turkish"


async def test_refusals_name_the_language_to_answer_in(pos_api):
    async with Client(mcp) as client:
        result, text = await call(
            client,
            "create_order",
            {"items": [{"name": "Ayran"}], "user_message": "2 ayran ekle"},  # no table
        )
    assert result.is_error and text.endswith("(Answer the user in Turkish.)")


async def test_approval_rule_is_in_the_tool_descriptions(pos_api):
    """Clients that drop the server instructions still tell the model how approval works."""
    async with Client(mcp) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
    for name in ("void_order_item", "cancel_order", "pay_order", "record_stock_purchase"):
        assert "do not ask the user to confirm first" in tools[name].description, name
    assert "ASK_USER" in tools["create_order"].description
    assert "do not choose for them" in tools["create_order"].description


def test_language_codes_and_neutral_instructions():
    from pos_mcp import i18n
    from pos_mcp.confirmation import approves
    from pos_mcp.server import INSTRUCTIONS

    assert i18n.use("Hall 4'e 1 Adana Kebab.") == "tr" and i18n.use("ok", "de") == "de"
    assert [i18n.code(x) for x in ("en", "EN", "English", "en-US", "Türkçe", "tr", "nl")] == [
        "en",
        "en",
        "en",
        "en",
        "tr",
        "tr",
        "nl",
    ]
    assert approves("ja") and approves("oui") and not approves("nein")
    # the language rule names both directions, not only "Turkish -> Turkish"
    assert "English -> English" in INSTRUCTIONS and "Türkçe -> Türkçe" in INSTRUCTIONS
    assert "Turkish message -> Turkish answer" not in INSTRUCTIONS


# --------------------------------------------------------------------------- #
# v6.5: the server holds order lines against the user's own words
# --------------------------------------------------------------------------- #


async def _open_orders(client, table: str) -> int | None:
    tables = data(await client.call_tool("list_tables", {}))
    return next(t["open_order_id"] for t in tables if t["name"] == table)


async def test_a_quantity_the_user_did_not_say_is_not_saved(pos_api):
    async with Client(mcp) as client:
        result, text = await call(
            client,
            "create_order",
            {
                "table_name": "Hall 3",
                "items": [
                    {"name": "Adana Kebab", "quantity": 1, "options": ["Acılı"]},
                    {"name": "Ayran", "quantity": 2},
                ],
                "user_message": "Hall 3'e 2 acılı Adana ve 2 ayran aç.",
            },
        )
        assert result.is_error and "NOT SAVED. Quantity: the user said 2 x Adana Kebab" in text
        assert "but the lines add up to 1." in text and "said 2 x Ayran" not in text
        # the corrected items, ready to copy
        assert (
            'exactly these items (the rest unchanged): [{"name": "Adana Kebab", "quantity": 2, '
            '"options": ["Spicy"]}, {"name": "Ayran", "quantity": 2}]' in text
        )
        assert await _open_orders(client, "Hall 3") is None  # nothing was opened
        fixed = data(
            await client.call_tool(
                "create_order",
                {
                    "table_name": "Hall 3",
                    "items": [
                        {"name": "Adana Kebab", "quantity": 2, "options": ["Acılı"]},
                        {"name": "Ayran", "quantity": 2},
                    ],
                    "user_message": "Hall 3'e 2 acılı Adana ve 2 ayran aç.",
                },
            )
        )
    assert "2 x Adana Kebab (Spicy = acılı), 2 x Ayran" in fixed["summary"]


async def test_lines_with_different_options_add_up_to_what_the_user_said(pos_api):
    message = "Start an order on Hall 4: two Adana kebabs, one spicy and one not spicy."
    split = [
        {"name": "Adana Kebab", "quantity": 1, "options": ["spicy"]},
        {"name": "Adana Kebab", "quantity": 1, "options": ["not spicy"]},
    ]
    async with Client(mcp) as client:
        ok = data(
            await client.call_tool(
                "create_order", {"table_name": "Hall 4", "items": split, "user_message": message}
            )
        )
        three, text = await call(
            client,
            "create_order",
            {
                "table_name": "Hall 4",
                "items": [*split, {"name": "Adana Kebab", "quantity": 1, "options": ["mild"]}],
                "user_message": message,
            },
        )
    assert ok["summary"].startswith("OPENED order")
    assert three.is_error and "said 2 x Adana Kebab, but the lines add up to 3" in text
    assert "Put the number the user said in each line's quantity field" in text  # 3 lines for 2


async def test_a_missing_table_is_asked_by_the_server_in_the_users_language(pos_api):
    async with Client(mcp) as client:
        tr, tr_text = await call(
            client,
            "create_order",
            {"items": [{"name": "Cola", "quantity": 2}], "user_message": "2 kola ekle."},
        )
        en, en_text = await call(
            client,
            "add_items_to_order",
            {
                "table_name": "?",
                "items": [{"name": "Cola", "quantity": 2}],
                "user_message": "Add two colas.",
            },
        )
    assert tr.is_error and "ASK_USER: Hangi masa için?" in tr_text
    assert tr_text.endswith("(Answer the user in Turkish.)")
    assert en.is_error and "ASK_USER: Which table is this for?" in en_text


async def test_takeaway_channel_is_inferred_when_the_model_forgets_it(pos_api):
    """ "Paket servis: 3 acısız lahmacun" left at channel='dineIn' with no table used to make
    the server ask "which table?" instead of placing the pickup order (found in testing)."""
    async with Client(mcp) as client:
        order = data(
            await client.call_tool(
                "create_order",
                {
                    # channel left at its default; the model forgot pickup has no table
                    "items": [{"name": "Lahmacun", "quantity": 3, "options": ["acısız"]}],
                    "user_message": "Paket servis: 3 acısız lahmacun.",
                },
            )
        )
        delivery = data(
            await client.call_tool(
                "create_order",
                {
                    "items": [{"name": "Tea", "quantity": 1}],
                    "user_message": "Kurye ile 1 çay gönder.",
                },
            )
        )
    assert order["channel"] == "pickup" and order["table"] is None
    assert delivery["channel"] == "delivery" and delivery["table"] is None


async def test_takeaway_words_do_not_override_an_explicit_table(pos_api):
    async with Client(mcp) as client:
        order = data(
            await client.call_tool(
                "create_order",
                {
                    "table_name": "Hall 4",
                    "items": [{"name": "Tea", "quantity": 1}],
                    "user_message": "Hall 4'e paket kutusunda servis edilsin, 1 çay aç.",
                },
            )
        )
    assert order["table"] == "Hall 4"


async def test_a_spice_level_the_user_did_not_give_is_asked_not_chosen(pos_api):
    async with Client(mcp) as client:
        # the model chose 'Acılı' although the user did not say how spicy
        guessed, tr_text = await call(
            client,
            "create_order",
            {
                "table_name": "Hall 4",
                "items": [{"name": "Adana Kebab", "options": ["Acılı"]}],
                "user_message": "Hall 4'e 1 Adana Kebap.",
            },
        )
        assert await _open_orders(client, "Hall 4") is None
        missing, en_text = await call(
            client,
            "create_order",
            {
                "table_name": "Hall 4",
                "items": [{"name": "Adana Kebab", "quantity": 2}],
                "user_message": "Open two Adana kebabs on Hall 4.",
            },
        )
        # the user's answer to the question names no item: it is not second-guessed
        answered = data(
            await client.call_tool(
                "create_order",
                {
                    "table_name": "Hall 4",
                    "items": [{"name": "Adana Kebab", "options": ["Acılı"]}],
                    "user_message": "acılı olsun",
                },
            )
        )
    assert guessed.is_error
    assert (
        "ASK_USER: Adana Kebab için acı seviyesi ne olsun: Spicy (acılı), Mild (az acılı) ya da "
        "Not Spicy (acısız)?" in tr_text
    )
    assert missing.is_error
    assert (
        "ASK_USER: Spice Level for the 2 Adana Kebab: Spicy, Mild or Not Spicy? (If they differ, "
        "say e.g. 'one Spicy, one Not Spicy'.)" in en_text
    )
    assert answered["summary"].startswith("AÇILDI")


async def test_table_and_spice_are_asked_together(pos_api):
    async with Client(mcp) as client:
        result, text = await call(
            client,
            "create_order",
            {"items": [{"name": "Beyti"}], "user_message": "bir Beyti aç"},
        )
    assert result.is_error
    question = text.split("ASK_USER: ")[1]
    assert question.startswith("Hangi masa için?") and "Beyti Kebab için acı seviyesi" in question


async def test_options_in_other_languages_are_not_second_guessed(pos_api):
    """The server reads Turkish and English; in other languages the model's choice stands."""
    async with Client(mcp) as client:
        order = data(
            await client.call_tool(
                "create_order",
                {
                    "channel": "pickup",
                    "items": [{"name": "Adana Kebab", "options": ["spicy"]}],
                    "user_message": "Einmal Adana scharf zum Mitnehmen",
                    "reply_language": "de",
                },
            )
        )
    assert order["summary"].startswith("OPENED pickup order")


async def test_two_spicy_and_one_mild_for_two_mixed_adana_gets_two_lines_of_one(pos_api):
    async with Client(mcp) as client:
        result, text = await call(
            client,
            "create_order",
            {
                "table_name": "Hall 6",
                "items": [
                    {"name": "Adana Kebab", "quantity": 2, "options": ["Acılı"]},
                    {"name": "Adana Kebab", "quantity": 1, "options": ["Acısız"]},
                ],
                "user_message": "Hall 6'ya 2 Adana aç, biri acılı biri acısız.",
            },
        )
    assert result.is_error
    assert (
        '[{"name": "Adana Kebab", "quantity": 1, "options": ["Spicy"]}, '
        '{"name": "Adana Kebab", "quantity": 1, "options": ["Not Spicy"]}]' in text
    )


async def test_a_note_the_user_did_not_ask_for_is_not_saved(pos_api):
    message = "Hall 3'e 2 acılı Adana ve 2 ayran aç."
    async with Client(mcp) as client:
        invented, text = await call(
            client,
            "create_order",
            {
                "table_name": "Hall 3",
                "items": [
                    {"name": "Adana", "options": ["Acılı"], "note": "soğansız"},
                    {"name": "Ayran", "quantity": 2},
                ],
                "user_message": message,
            },
        )
        assert await _open_orders(client, "Hall 3") is None
        # a note that only repeats the line (the count went there) is dropped, and the
        # missing quantity is reported with the corrected lines
        repeated, text2 = await call(
            client,
            "create_order",
            {
                "table_name": "Hall 3",
                "items": [
                    {"name": "Adana", "options": ["acılı"], "note": "acılı Adana (2 adet)"},
                    {"name": "Ayran", "quantity": 2},
                ],
                "user_message": message,
            },
        )
        said = data(
            await client.call_tool(
                "create_order",
                {
                    "table_name": "Hall 3",
                    "items": [{"name": "Adana", "options": ["Acılı"], "note": "soğansız"}],
                    "user_message": "Hall 3'e 1 acılı Adana, soğan olmasın",
                },
            )
        )
    assert invented.is_error
    assert "Note: the user did not ask for 'soğansız' on Adana Kebab" in text
    assert "Quantity: the user said 2 x Adana Kebab" in text  # both problems, one refusal
    assert '{"name": "Adana Kebab", "quantity": 2, "options": ["Spicy"]}' in text
    assert repeated.is_error and "the user did not ask for" not in text2
    assert '{"name": "Adana Kebab", "quantity": 2, "options": ["Spicy"]}' in text2
    assert said["items"][0]["note"] == "soğansız"


async def test_a_note_that_only_repeats_the_line_is_dropped(pos_api):
    async with Client(mcp) as client:
        order = data(
            await client.call_tool(
                "create_order",
                {
                    "table_name": "Hall 3",
                    "items": [
                        {
                            "name": "Adana",
                            "quantity": 2,
                            "options": ["Acılı"],
                            "note": "2 acılı Adana",
                        }
                    ],
                    "user_message": "Hall 3'e 2 acılı Adana",
                },
            )
        )
    assert order["items"][0]["note"] == "" and order["items"][0]["quantity"] == 2
