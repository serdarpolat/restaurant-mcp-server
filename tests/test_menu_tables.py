import pytest


def test_search_is_bilingual_and_accent_insensitive(client):
    names = [i["name"] for i in client.get("/menu/items", params={"search": "iskender"}).json()]
    assert names == ["Iskender Kebab"]
    # Turkish word -> English menu, via GLOSSARY ("cay" = tea)
    names = [i["name"] for i in client.get("/menu/items", params={"search": "cay"}).json()]
    assert "Tea" in names
    # accented Turkish spelling normalizes the same way
    names = [i["name"] for i in client.get("/menu/items", params={"search": "çay"}).json()]
    assert "Tea" in names


def test_category_filter(client):
    items = client.get("/menu/items", params={"category": "Desserts"}).json()
    assert {i["category"] for i in items} == {"Desserts"}
    assert len(items) == 3


def test_item_detail_has_modifier_groups(client):
    adana = next(i for i in client.get("/menu/items", params={"search": "adana"}).json())
    detail = client.get(f"/menu/items/{adana['id']}").json()
    groups = {g["name"]: g for g in detail["modifier_groups"]}
    assert groups["Spice Level"]["min_select"] == 1
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
    assert "Soups" in r.json()["detail"]  # an agent can retry with the right name
    assert client.get("/menu/items", params={"category": "corba"}).status_code == 200
    soups = client.get("/menu/items", params={"category": "soups"}).json()
    assert {i["category"] for i in soups} == {"Soups"}


def names(client, search, match="all"):
    params = {"search": search, "match": match}
    return [i["name"] for i in client.get("/menu/items", params=params).json()]


@pytest.mark.parametrize(
    ("search", "first"),
    [
        ("adana kebab", "Adana Kebab"),  # direct English spelling
        ("two Adana kebabs", "Adana Kebab"),  # plural and a number word
        ("2 adana", "Adana Kebab"),
        ("lahmajun", "Lahmacun"),  # one typo
        ("mercimek corba", "Lentil Soup"),  # Turkish words -> English menu
        ("tavuk kanat", "Chicken Wings"),  # Turkish words -> English menu
        ("cay", "Tea"),  # Turkish word -> English menu
        ("su", "Water"),  # Turkish word -> English menu
        ("kahve", "Turkish Coffee"),  # Turkish word -> English menu
        ("acili adana", "Adana Kebab"),  # Turkish word + English word
    ],
)
def test_search_understands_turkish_english_and_typos(client, search, first):
    assert names(client, search)[0] == first


def test_short_words_match_whole_words_only(client):
    assert names(client, "su") == ["Water"]  # not some unrelated word containing "su"
    assert "Shepherd's Salad" not in names(client, "soup")  # 'corba' is not 'shepherd'


def test_any_match_lists_close_items_best_first(client):
    assert names(client, "adana durum") == []  # no "durum" wrap on the menu
    close = names(client, "adana durum", match="any")
    assert close[0] == "Adana Kebab"
    assert names(client, "sushi", match="any") == []
