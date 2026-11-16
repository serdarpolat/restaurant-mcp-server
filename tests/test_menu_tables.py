import pytest


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


def test_unknown_category_lists_the_valid_ones(client):
    r = client.get("/menu/items", params={"category": "sushi"})
    assert r.status_code == 422
    assert "Çorbalar" in r.json()["detail"]  # an agent can retry with the right name
    assert client.get("/menu/items", params={"category": "corbalar"}).status_code == 200
    soups = client.get("/menu/items", params={"category": "soups"}).json()
    assert {i["category"] for i in soups} == {"Çorbalar"}


def names(client, search, match="all"):
    params = {"search": search, "match": match}
    return [i["name"] for i in client.get("/menu/items", params=params).json()]


@pytest.mark.parametrize(
    ("search", "first"),
    [
        ("adana kebab", "Adana Kebap"),  # English spelling
        ("two Adana kebabs", "Adana Kebap"),  # plural and a number word
        ("2 adana", "Adana Kebap"),
        ("lahmajun", "Lahmacun"),  # one typo
        ("lentil soup", "Mercimek Çorbası"),  # English words
        ("chicken wings", "Tavuk Kanat"),
        ("tea", "Çay"),
        ("water", "Su"),
        ("turkish coffee", "Türk Kahvesi"),
        ("spicy adana", "Adana Kebap"),
    ],
)
def test_search_understands_english_and_typos(client, search, first):
    assert names(client, search)[0] == first


def test_short_words_match_whole_words_only(client):
    assert names(client, "su") == ["Su"]  # not Sütlaç
    assert "Çoban Salata" not in names(client, "soup")  # 'corba' is not 'coban'


def test_any_match_lists_close_items_best_first(client):
    assert names(client, "adana durum") == []  # no dürüm on the menu
    close = names(client, "adana durum", match="any")
    assert close[0] == "Adana Kebap"
    assert names(client, "sushi", match="any") == []
