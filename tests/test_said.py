"""Reading the user's own words: quantities and whether they chose an option (pos_mcp.said)."""

import pytest

from pos_mcp.lines import OPTION_ALIASES
from pos_mcp.said import mentions, quantities, quantity_mentions, speaks_of_group

ITEMS = {
    1: "Adana Kebab",
    2: "Ayran",
    3: "Lahmacun",
    4: "Turnip Juice",
    5: "Tea",
    6: "Chicken Shish",
    7: "Chicken Wings",
    8: "Beyti Kebab",
}
TABLES = ["Hall 2", "Hall 3", "Hall 4", "Hall 6", "Garden 2", "Terrace 1"]
SPICE = {
    "name": "Spice Level",
    "modifiers": [{"name": "Spicy"}, {"name": "Mild"}, {"name": "Not Spicy"}],
}


def said(text, lang="tr"):
    return {ITEMS[k]: v for k, v in quantities(text, ITEMS, TABLES, lang).items()}


@pytest.mark.parametrize(
    ("text", "lang", "expected"),
    [
        # every order prompt of the eval (table names are proper nouns: kept in English even
        # in an otherwise Turkish sentence, the way a real bilingual speaker would say them)
        ("Hall 3'e 2 acılı Adana ve 2 ayran aç.", "tr", {"Adana Kebab": 2, "Ayran": 2}),
        ("Paket servis: 3 acısız lahmacun ve 1 şalgam.", "tr", {"Lahmacun": 3, "Turnip Juice": 1}),
        ("Garden 2'ye 2 çay ekle.", "tr", {"Tea": 2}),
        ("Hall 6'ya 2 Adana aç, biri acılı biri acısız.", "tr", {"Adana Kebab": 2}),
        ("Hall 6'ya bir Beyti aç.", "tr", {"Beyti Kebab": 1}),
        (
            "Start an order on Hall 4: two Adana kebabs, one spicy and one not spicy.",
            "en",
            {"Adana Kebab": 2},
        ),
        (
            "Takeaway: three lahmacun, not spicy, and one turnip juice.",
            "en",
            {"Lahmacun": 3, "Turnip Juice": 1},
        ),
        ("Add two teas to Garden 2.", "en", {"Tea": 2}),
        # the next word decides between items that share a first word
        ("Hall 2 için 1 tavuk şiş, 2 tavuk kanat", "tr", {"Chicken Shish": 1, "Chicken Wings": 2}),
        # numbers after the name count only with a unit
        ("Adana Kebab (Acılı): 1 adet, 560.00 TRY - Ayran: 2 adet", "tr",
         {"Adana Kebab": 1, "Ayran": 2}),
        ("Ayran x2, Adana Kebab x 3", "tr", {"Ayran": 2, "Adana Kebab": 3}),
    ],
)  # fmt: skip
def test_quantities_the_user_said(text, lang, expected):
    assert said(text, lang) == expected


@pytest.mark.parametrize(
    "text",
    [
        "Hall 3'teki Adana'yı iptal et",  # a suffix points at something already ordered
        "1.5 porsiyon Adana, bir buçuk porsiyon Beyti",  # portions, not quantities
        "1. Adana Kebab (Acılı)",  # a list marker
        "Order #12 on Hall 2: Adana Kebab",  # an order id and a table number
        "Put the tea on Terrace 1",  # 'on' is 10 only in Turkish
        "acılı olsun",  # an answer to a question: no item
    ],
)
def test_no_quantity_when_it_is_not_clear(text):
    assert said(text, "en" if "Put" in text else "tr").get("Adana Kebab") is None
    assert said(text).get("Tea") is None


def test_an_answer_may_name_an_item_twice():
    text = "2 çay eklendi: 2 x Çay."
    assert quantity_mentions(text, ITEMS, TABLES, "tr") == [(5, 2), (5, 2)]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Hall 4'e 1 Adana Kebab.", False),
        ("Open one Adana kebab on Hall 4.", False),
        ("Hall 6'ya bir Beyti aç.", False),
        ("Hall 4'e 1 Adana, acı olmasın", True),
        ("2 Adana, biri acılı biri acısız", True),
        ("one spicy, one not spicy", True),
        ("make it mild", True),
        ("Adana, hot please", True),
    ],
)
def test_speaks_of_the_spice_level(text, expected):
    assert speaks_of_group(text, SPICE, OPTION_ALIASES, TABLES) is expected


def test_mentions_an_item():
    assert mentions("Hall 4'e 1 Adana Kebab.", "Adana Kebab", TABLES)
    assert mentions("two Adana kebabs", "Adana Kebab", TABLES)
    assert not mentions("acılı", "Adana Kebab", TABLES)
    assert not mentions("Adana'yı iptal et", "Adana Kebab", TABLES)


ADANA = {
    "name": "Adana Kebab",
    "modifier_groups": [SPICE, {"name": "Portion", "modifiers": [{"name": "1.5 Portion"}]}],
}
SALGAM = {"name": "Turnip Juice", "modifier_groups": []}


@pytest.mark.parametrize(
    ("note", "message", "detail", "expected"),
    [
        # words the user never said: seen in the eval logs
        ("soğansız", "Hall 3'e 2 acılı Adana ve 2 ayran aç.", ADANA, "invented"),
        ("soğansız (if stated by the user)", "Hall 3'e 2 acılı Adana", ADANA, "invented"),
        ("sıcak sunulmasın", "Hall 3'e 2 acılı Adana", ADANA, "invented"),
        # notes that only restate the order: dropped
        ("acılı Adana (2 adet)", "Hall 3'e 2 acılı Adana", ADANA, "empty"),
        ("acılı, hall 3 için, 2 adet", "Hall 3'e 2 acılı Adana", ADANA, "empty"),
        ("Acılı Adana, 2 adet ayran", "Hall 3'e 2 acılı Adana ve 2 ayran", ADANA, "empty"),
        # the user's own request to the kitchen, in their words or another language
        ("soğansız", "Hall 3'e 2 acılı Adana, soğansız olsun", ADANA, "ok"),
        ("soğansız", "2 acılı Adana, soğan olmasın", ADANA, "ok"),
        ("soğansız", "Add a spicy Adana, no onions", ADANA, "ok"),
        ("az pişmiş", "1 acılı Adana az pişmiş olsun", ADANA, "ok"),
        ("acılı", "1 acılı şalgam", SALGAM, "ok"),  # not an option of Turnip Juice: a real note
        # an answer to a question does not name the item: not held against an earlier note
        ("soğansız", "acılı olsun", ADANA, "ok"),
    ],
)
def test_note_status(note, message, detail, expected):
    from pos_mcp.said import note_status

    also = ["Ayran"] if "ayran" in note.lower() else []
    assert note_status(note, message, detail, OPTION_ALIASES, TABLES, also)[0] == expected


def test_juice_names_the_drink():
    from pos_mcp.lines import find_item

    menu = [
        {"id": 1, "name": "Turnip Juice"},
        {"id": 2, "name": "Water"},
        {"id": 3, "name": "Lemonade"},
    ]
    assert [i["name"] for i in find_item(menu, "Turnip Juice")] == ["Turnip Juice"]
    assert [i["name"] for i in find_item(menu, "şalgam suyu")] == ["Turnip Juice"]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Paket servis: 3 acısız lahmacun ve 1 şalgam.", "pickup"),
        ("Paket, 2 Adana Kebap.", "pickup"),
        ("Pickup order: two teas.", "pickup"),
        ("Gel al, 1 Beyti.", "pickup"),
        ("Kurye ile 2 Adana gönder.", "delivery"),
        ("Delivery, one lahmacun please.", "delivery"),
        ("Hall 4'e 2 Adana aç.", None),  # dine-in: names a table, not a channel
        ("2 kola ekle.", None),  # neither a table nor a channel: the server must still ask
    ],
)
def test_channel_from_message(text, expected):
    from pos_mcp.said import channel_from_message

    assert channel_from_message(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Terrace 2'ye 1 ayran aç.", "Terrace 2"),  # a case ending glued on with an apostrophe
        ("Hall 4 için hesap getir", "Hall 4"),
        ("Hall 10 dolu mu?", "Hall 10"),  # not read as naming "Hall 1"
        ("Garden 2 masasına 1 çay", "Garden 2"),
        ("Hall 1 ve Hall 4 için hesap getir", None),  # two tables named: ambiguous
        ("evet, ekleyin", None),  # no table named: never held against the caller's table
        ("masaya ekle", None),
    ],
)
def test_table_from_message(text, expected):
    from pos_mcp.said import table_from_message

    tables = [*TABLES, "Hall 1", "Hall 10", "Terrace 2"]
    assert table_from_message(text, tables) == expected
