from decimal import Decimal

from sqlmodel import select

from pos_api.db.models import Ingredient
from tests.helpers import find_item, free_table, modifier_id

ACTOR = {"X-Actor": "mcp:test"}


def _adana_order(client, table_id: int, quantity: int = 2) -> dict:
    adana = find_item(client, "Adana Kebap")
    spicy = modifier_id(client, adana["id"], "Acılı")
    return {
        "channel": "dine_in",
        "table_id": table_id,
        "items": [{"menu_item_id": adana["id"], "quantity": quantity, "modifier_ids": [spicy]}],
    }


def test_required_modifier_error_lists_options(client):
    table = free_table(client)
    adana = find_item(client, "Adana Kebap")
    r = client.post(
        "/orders",
        json={"table_id": table["id"], "items": [{"menu_item_id": adana["id"]}]},
    )
    assert r.status_code == 422
    assert "Acı Seviyesi" in r.json()["detail"]
    assert "Acısız" in r.json()["detail"]  # options are listed so an agent can ask the user


def test_create_order_prices_occupies_table_consumes_stock_and_audits(client, session):
    kiyma_before = session.exec(select(Ingredient).where(Ingredient.name == "Dana Kıyma")).one()
    before = kiyma_before.stock_qty
    table = free_table(client)

    r = client.post("/orders", json=_adana_order(client, table["id"]), headers=ACTOR)
    assert r.status_code == 201, r.text
    order = r.json()
    assert order["status"] == "open"
    assert order["total"] == 2 * find_item(client, "Adana Kebap")["price"]
    assert order["items"][0]["modifiers"] == "Acılı"

    assert client.get(f"/tables/{table['id']}").json()["open_order_id"] == order["id"]

    session.expire_all()
    after = session.exec(select(Ingredient).where(Ingredient.name == "Dana Kıyma")).one()
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
    payload = _adana_order(client, 1) | {"channel": "takeaway"}
    assert client.post("/orders", json=payload).status_code == 422


def test_portion_modifier_adds_price(client):
    adana = find_item(client, "Adana Kebap")
    payload = {
        "channel": "takeaway",
        "items": [
            {
                "menu_item_id": adana["id"],
                "modifier_ids": [
                    modifier_id(client, adana["id"], "Acısız"),
                    modifier_id(client, adana["id"], "1.5 Porsiyon"),
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
    assert order["total"] == find_item(client, "Adana Kebap")["price"] + 2 * ayran["price"]

    ayran_line = next(i for i in order["items"] if i["name"] == "Ayran")
    order = client.post(
        f"/orders/{order['id']}/items/{ayran_line['id']}/void", json={"reason": "Müşteri vazgeçti"}
    ).json()
    assert order["total"] == find_item(client, "Adana Kebap")["price"]

    r = client.post(f"/orders/{order['id']}/pay", json={"method": "card", "discount_rate": 0.1})
    assert r.status_code == 422  # discount without a reason

    paid = client.post(
        f"/orders/{order['id']}/pay",
        json={"method": "card", "discount_rate": 0.1, "discount_reason": "Sadakat indirimi"},
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
        f"/orders/{order['id']}/cancel", json={"reason": "Müşteri gitti"}
    ).json()
    assert cancelled["status"] == "cancelled"
    assert cancelled["total"] == 0
    assert all(i["status"] == "void" for i in cancelled["items"])
    assert client.get(f"/tables/{table['id']}").json()["status"] == "free"


def test_insufficient_stock_is_refused(client, session):
    patlican = session.exec(select(Ingredient).where(Ingredient.name == "Patlıcan")).one()
    patlican.stock_qty = Decimal("0.1")
    session.commit()
    item = find_item(client, "Ali Nazik")
    r = client.post(
        "/orders", json={"channel": "takeaway", "items": [{"menu_item_id": item["id"]}]}
    )
    assert r.status_code == 409
    assert "Patlıcan" in r.json()["detail"]


def test_table_with_open_order_cannot_be_freed(client):
    table = free_table(client)
    client.post("/orders", json=_adana_order(client, table["id"]))
    r = client.patch(f"/tables/{table['id']}", json={"status": "free"})
    assert r.status_code == 409
