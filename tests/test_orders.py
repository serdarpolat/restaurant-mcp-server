from decimal import Decimal

from sqlmodel import select

from pos_api.db.models import Ingredient
from tests.helpers import find_item, free_table, modifier_id

ACTOR = {"X-Actor": "mcp:test"}


def _adana_order(client, table_id: int, quantity: int = 2) -> dict:
    adana = find_item(client, "Adana Kebab")
    spicy = modifier_id(client, adana["id"], "Spicy")
    return {
        "channel": "dineIn",
        "table_id": table_id,
        "items": [{"menu_item_id": adana["id"], "quantity": quantity, "modifier_ids": [spicy]}],
    }


def test_required_modifier_error_lists_options(client):
    table = free_table(client)
    adana = find_item(client, "Adana Kebab")
    r = client.post(
        "/orders",
        json={"table_id": table["id"], "items": [{"menu_item_id": adana["id"]}]},
    )
    assert r.status_code == 422
    assert "Spice Level" in r.json()["detail"]
    assert "Not Spicy" in r.json()["detail"]  # options are listed so an agent can ask the user


def test_two_options_on_one_line_suggests_separate_lines(client):
    adana = client.get("/menu/items", params={"search": "adana"}).json()[0]
    detail = client.get(f"/menu/items/{adana['id']}").json()
    spice = {m["name"]: m["id"] for m in detail["modifier_groups"][0]["modifiers"]}
    line = {"menu_item_id": adana["id"], "quantity": 2}
    r = client.post(
        "/orders",
        json={
            "channel": "pickup",
            "items": [{**line, "modifier_ids": [spice["Spicy"], spice["Not Spicy"]]}],
        },
    )
    assert r.status_code == 422
    assert "separate lines" in r.json()["detail"]
    r = client.post(
        "/orders",
        json={
            "channel": "pickup",
            "items": [
                {"menu_item_id": adana["id"], "modifier_ids": [spice["Spicy"]]},
                {"menu_item_id": adana["id"], "modifier_ids": [spice["Not Spicy"]]},
            ],
        },
    )
    assert r.status_code == 201, r.text
    assert sorted(i["modifiers"] for i in r.json()["items"]) == ["Not Spicy", "Spicy"]


def test_create_order_prices_occupies_table_consumes_stock_and_audits(client, session):
    kiyma_before = session.exec(select(Ingredient).where(Ingredient.name == "Ground Beef")).one()
    before = kiyma_before.stock_qty
    table = free_table(client)

    r = client.post("/orders", json=_adana_order(client, table["id"]), headers=ACTOR)
    assert r.status_code == 201, r.text
    order = r.json()
    assert order["status"] == "open"
    assert order["total"] == 2 * find_item(client, "Adana Kebab")["price"]
    assert order["items"][0]["modifiers"] == "Spicy"

    assert client.get(f"/tables/{table['id']}").json()["open_order_id"] == order["id"]

    session.expire_all()
    after = session.exec(select(Ingredient).where(Ingredient.name == "Ground Beef")).one()
    assert before - after.stock_qty == Decimal("0.4")

    log = client.get("/audit-log", params={"actor": "mcp:test"}).json()
    assert log[0]["action"] == "create_order"


def test_cannot_open_second_order_on_occupied_table(client):
    table = free_table(client)
    first = client.post("/orders", json=_adana_order(client, table["id"])).json()
    r = client.post("/orders", json=_adana_order(client, table["id"]))
    assert r.status_code == 409
    assert f"#{first['id']}" in r.json()["detail"]


def test_takeaway_cannot_have_table(client):
    payload = _adana_order(client, 1) | {"channel": "pickup"}
    assert client.post("/orders", json=payload).status_code == 422


def test_portion_modifier_adds_price(client):
    adana = find_item(client, "Adana Kebab")
    payload = {
        "channel": "pickup",
        "items": [
            {
                "menu_item_id": adana["id"],
                "modifier_ids": [
                    modifier_id(client, adana["id"], "Not Spicy"),
                    modifier_id(client, adana["id"], "1.5 Portion"),
                ],
            }
        ],
    }
    order = client.post("/orders", json=payload).json()
    assert order["total"] == adana["price"] + 250


def test_add_void_pay_flow(client):
    table = free_table(client)
    order = client.post("/orders", json=_adana_order(client, table["id"], 1)).json()
    ayran = find_item(client, "Ayran")

    order = client.post(
        f"/orders/{order['id']}/items",
        json={"items": [{"menu_item_id": ayran["id"], "quantity": 2}]},
    ).json()
    assert order["total"] == find_item(client, "Adana Kebab")["price"] + 2 * ayran["price"]

    ayran_line = next(i for i in order["items"] if i["name"] == "Ayran")
    order = client.post(
        f"/orders/{order['id']}/items/{ayran_line['id']}/void",
        json={"reason": "Customer changed their mind"},
    ).json()
    assert order["total"] == find_item(client, "Adana Kebab")["price"]

    r = client.post(
        f"/orders/{order['id']}/pay", json={"method": "credit_card", "discount_rate": 0.1}
    )
    assert r.status_code == 422  # discount without a reason

    paid = client.post(
        f"/orders/{order['id']}/pay",
        json={"method": "credit_card", "discount_rate": 0.1, "discount_reason": "Loyalty discount"},
    ).json()
    assert paid["status"] == "paid"
    assert paid["discount"] == round(paid["subtotal"] * 0.1, 2)
    assert sum(p["amount"] for p in paid["payments"]) == paid["total"]
    assert client.get(f"/tables/{table['id']}").json()["status"] == "free"

    r = client.post(f"/orders/{order['id']}/items", json={"items": [{"menu_item_id": ayran["id"]}]})
    assert r.status_code == 409  # paid orders are closed


def test_cancel_order_frees_table(client):
    table = free_table(client)
    order = client.post("/orders", json=_adana_order(client, table["id"])).json()
    cancelled = client.post(
        f"/orders/{order['id']}/cancel", json={"reason": "Customer left"}
    ).json()
    assert cancelled["status"] == "cancelled"
    assert cancelled["total"] == 0
    assert all(i["status"] == "void" for i in cancelled["items"])
    assert client.get(f"/tables/{table['id']}").json()["status"] == "free"


def test_insufficient_stock_is_refused(client, session):
    eggplant = session.exec(select(Ingredient).where(Ingredient.name == "Eggplant")).one()
    eggplant.stock_qty = Decimal("0.1")
    session.commit()
    item = find_item(client, "Ali Nazik")
    r = client.post("/orders", json={"channel": "pickup", "items": [{"menu_item_id": item["id"]}]})
    assert r.status_code == 409
    assert "Eggplant" in r.json()["detail"]


def test_table_with_open_order_cannot_be_freed(client):
    table = free_table(client)
    client.post("/orders", json=_adana_order(client, table["id"]))
    r = client.patch(f"/tables/{table['id']}", json={"status": "free"})
    assert r.status_code == 409


def _stock(session, name: str) -> Decimal:
    session.expire_all()
    return session.exec(select(Ingredient).where(Ingredient.name == name)).one().stock_qty


def test_count_ingredients_are_used_in_whole_pieces(client, session):
    adana = find_item(client, "Adana Kebab")
    flatbread, kiyma = _stock(session, "Flatbread"), _stock(session, "Ground Beef")
    line = {
        "menu_item_id": adana["id"],
        "modifier_ids": [
            modifier_id(client, adana["id"], "Not Spicy"),
            modifier_id(client, adana["id"], "1.5 Portion"),
        ],
    }
    client.post("/orders", json={"channel": "pickup", "items": [line]})
    assert flatbread - _stock(session, "Flatbread") == 2  # 1.5 flatbreads rounds up to 2 pieces
    assert kiyma - _stock(session, "Ground Beef") == Decimal("0.3")  # weights stay exact


def test_cancel_keeps_stock_used_unless_returned(client, session):
    before = _stock(session, "Ground Beef")
    table = free_table(client)
    order = client.post("/orders", json=_adana_order(client, table["id"])).json()
    client.post(f"/orders/{order['id']}/cancel", json={"reason": "Customer left"})
    assert before - _stock(session, "Ground Beef") == Decimal("0.4")  # food was prepared

    table = free_table(client)
    order = client.post("/orders", json=_adana_order(client, table["id"])).json()
    client.post(
        f"/orders/{order['id']}/cancel",
        json={"reason": "Cancelled before it reached the kitchen", "return_to_stock": True},
    )
    assert before - _stock(session, "Ground Beef") == Decimal("0.4")  # second order returned

    kiyma = session.exec(select(Ingredient).where(Ingredient.name == "Ground Beef")).one()
    returns = client.get(
        f"/inventory/ingredients/{kiyma.id}/movements", params={"reason": "returned"}
    ).json()
    assert [(r["change"], r["note"]) for r in returns] == [(0.4, f"Refund: Order #{order['id']}")]


def test_void_can_return_one_line_to_stock(client, session):
    table = free_table(client)
    order = client.post("/orders", json=_adana_order(client, table["id"], 1)).json()
    ayran = find_item(client, "Ayran")
    order = client.post(
        f"/orders/{order['id']}/items",
        json={"items": [{"menu_item_id": ayran["id"], "quantity": 3}]},
    ).json()
    before = _stock(session, "Ayran")
    line = next(i for i in order["items"] if i["name"] == "Ayran")
    client.post(
        f"/orders/{order['id']}/items/{line['id']}/void",
        json={"reason": "Wrong entry", "return_to_stock": True},
    )
    assert _stock(session, "Ayran") - before == 3


def test_seeded_count_ingredients_have_whole_stock(session):
    for ing in session.exec(select(Ingredient).where(Ingredient.unit == "piece")).all():
        assert ing.stock_qty == ing.stock_qty.to_integral_value(), ing.name


def test_missing_required_option_says_ask_the_user(client):
    adana = client.get("/menu/items", params={"search": "adana"}).json()[0]
    r = client.post(
        "/orders",
        json={"channel": "pickup", "items": [{"menu_item_id": adana["id"], "quantity": 3}]},
    )
    assert r.status_code == 422
    assert "do not choose for them" in r.json()["detail"]


def test_reversed_date_range_is_refused_not_swapped(client):
    r = client.get("/orders", params={"date_from": "2026-11-26", "date_to": "2026-11-20"})
    assert r.status_code == 422
    assert "date_from" in r.json()["detail"] and "date_to" in r.json()["detail"]
