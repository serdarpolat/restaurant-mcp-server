"""Reading the user's own words: quantities and whether they chose an option (pos_mcp.said)."""

import pytest

from pos_mcp.lines import OPTION_ALIASES
from pos_mcp.said import mentions, quantities, quantity_mentions, speaks_of_group

ITEMS = {
    1: "Adana Kebap",
    2: "Ayran",
    3: "Lahmacun",
    4: "Şalgam",
    5: "Çay",
    6: "Tavuk Şiş",
    7: "Tavuk Kanat",
    8: "Beyti",
}
TABLES = ["Salon 2", "Salon 3", "Salon 4", "Salon 6", "Bahçe 2", "Teras 1"]
SPICE = {
    "name": "Acı Seviyesi",
    "modifiers": [{"name": "Acılı"}, {"name": "Az Acılı"}, {"name": "Acısız"}],
}


def said(text, lang="tr"):
    return {ITEMS[k]: v for k, v in quantities(text, ITEMS, TABLES, lang).items()}


@pytest.mark.parametrize(
    ("text", "lang", "expected"),
    [
        # every order prompt of the eval
        ("Salon 3'e 2 acılı Adana ve 2 ayran aç.", "tr", {"Adana Kebap": 2, "Ayran": 2}),
        ("Paket servis: 3 acısız lahmacun ve 1 şalgam.", "tr", {"Lahmacun": 3, "Şalgam": 1}),
        ("Bahçe 2'ye 2 çay ekle.", "tr", {"Çay": 2}),
        ("Salon 6'ya 2 Adana aç, biri acılı biri acısız.", "tr", {"Adana Kebap": 2}),
        ("Salon 6'ya bir Beyti aç.", "tr", {"Beyti": 1}),
        (
            "Start an order on Salon 4: two Adana kebabs, one spicy and one not spicy.",
            "en",
            {"Adana Kebap": 2},
        ),
        (
            "Takeaway: three lahmacun, not spicy, and one turnip juice.",
            "en",
            {"Lahmacun": 3, "Şalgam": 1},
        ),
        ("Add two teas to Bahçe 2.", "en", {"Çay": 2}),
        # the next word decides between items that share a first word
        ("Salon 2 için 1 tavuk şiş, 2 tavuk kanat", "tr", {"Tavuk Şiş": 1, "Tavuk Kanat": 2}),
        # numbers after the name count only with a unit
        ("Adana Kebap (Acılı): 1 adet, 560.00 TRY - Ayran: 2 adet", "tr",
         {"Adana Kebap": 1, "Ayran": 2}),
        ("Ayran x2, Adana Kebap x 3", "tr", {"Ayran": 2, "Adana Kebap": 3}),
    ],
)  # fmt: skip
def test_quantities_the_user_said(text, lang, expected):
    assert said(text, lang) == expected


@pytest.mark.parametrize(
    "text",
    [
        "Salon 3'teki Adana'yı iptal et",  # a suffix points at something already ordered
        "1.5 porsiyon Adana, bir buçuk porsiyon Beyti",  # portions, not quantities
        "1. Adana Kebap (Acılı)",  # a list marker
        "Order #12 on Salon 2: Adana Kebap",  # an order id and a table number
        "Put the tea on Teras 1",  # 'on' is 10 only in Turkish
        "acılı olsun",  # an answer to a question: no item
    ],
)
def test_no_quantity_when_it_is_not_clear(text):
    assert said(text, "en" if "Put" in text else "tr").get("Adana Kebap") is None
    assert said(text).get("Çay") is None


def test_an_answer_may_name_an_item_twice():
    text = "2 çay eklendi: 2 x Çay."
    assert quantity_mentions(text, ITEMS, TABLES, "tr") == [(5, 2), (5, 2)]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Salon 4'e 1 Adana Kebap.", False),
        ("Open one Adana kebab on Salon 4.", False),
        ("Salon 6'ya bir Beyti aç.", False),
        ("Salon 4'e 1 Adana, acı olmasın", True),
        ("2 Adana, biri acılı biri acısız", True),
        ("one spicy, one not spicy", True),
        ("make it mild", True),
        ("Adana, hot please", True),
    ],
)
def test_speaks_of_the_spice_level(text, expected):
    assert speaks_of_group(text, SPICE, OPTION_ALIASES, TABLES) is expected


def test_mentions_an_item():
    assert mentions("Salon 4'e 1 Adana Kebap.", "Adana Kebap", TABLES)
    assert mentions("two Adana kebabs", "Adana Kebap", TABLES)
    assert not mentions("acılı", "Adana Kebap", TABLES)
    assert not mentions("Adana'yı iptal et", "Adana Kebap", TABLES)
