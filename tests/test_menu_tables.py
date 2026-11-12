def test_search_is_turkish_and_accent_insensitive(client):
    names = [i["name"] for i in client.get("/menu/items", params={"search": "iskender"}).json()]
    assert names == ["İskender"]
    names = [i["name"] for i in client.get("/menu/items", params={"search": "cay"}).json()]
    assert "Çay" in names


def test_category_filter(client):
    items = client.get("/menu/items", params={"category": "Tatlılar"}).json()
    assert {i["category"] for i in items} == {"Tatlılar"}
    assert len(items) == 3


def test_item_detail_has_modifier_groups(client):
    adana = next(i for i in client.get("/menu/items", params={"search": "adana"}).json())
    detail = client.get(f"/menu/items/{adana['id']}").json()
    groups = {g["name"]: g for g in detail["modifier_groups"]}
    assert groups["Acı Seviyesi"]["min_select"] == 1
    assert detail["has_options"] is True


def test_unknown_item_returns_404(client):
    r = client.get("/menu/items/9999")
    assert r.status_code == 404
    assert "not found" in r.json()["detail"]


def test_occupied_tables_point_to_open_orders(client):
    for t in client.get("/tables", params={"status": "occupied"}).json():
        assert t["open_order_id"] is not None
        order = client.get(f"/orders/{t['open_order_id']}").json()
        assert order["status"] == "open"
        assert order["table"] == t["name"]
