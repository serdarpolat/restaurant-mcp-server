"""Turn the order lines a model sends into the ids the POS needs, or explain what is wrong.

A line names its item ("Lahmacun") and may carry its id and its options by name ("Acısız",
"not spicy"). Names are checked against ids, so an id remembered from earlier in a chat
(Adana's 7 for a lahmacun) is caught instead of ordered. Pure functions over plain dicts
(menu items as the POS API returns them), shared by the MCP server and the eval scorer.
"""

from datetime import date, timedelta
from typing import Any

from pos_api.text import matches, normalize, words


class LineError(ValueError):
    """A line that cannot be resolved; the message tells the model how to fix it."""


# Turkish (and loose English) ways to say an option -> the option's normalized English name,
# since the menu data is now English but guests and agents may still say it in Turkish.
OPTION_ALIASES: dict[str, str] = {
    "acili": "spicy",
    "hot": "spicy",
    "very spicy": "spicy",
    "az acili": "mild",
    "medium": "mild",
    "medium spicy": "mild",
    "a little spicy": "mild",
    "slightly spicy": "mild",
    "acisiz": "not spicy",
    "no spice": "not spicy",
    "non spicy": "not spicy",
    "without spice": "not spicy",
    "no chili": "not spicy",
    "not hot": "not spicy",
    "buyuk boy": "large",
    "big": "large",
    "buyuk": "large",
    "large portion": "1 5 portion",
    "big portion": "1 5 portion",
    "one and a half": "1 5 portion",
    "one and a half portion": "1 5 portion",
    "1 5": "1 5 portion",
    "bir bucuk": "1 5 portion",
    "ekstra kasar": "extra cheese",
    "ekstra yumurta": "extra egg",
}


def _key(text: str) -> str:
    return " ".join(words(text))


def same_item_name(said: str, actual: str) -> bool:
    """'lahmacun' / 'Lahmacun', 'adana kebab' / 'Adana Kebab', 'adana' / 'Adana Kebab'."""
    return _key(said) == _key(actual) or matches(said, actual)


def find_item(menu: list[dict[str, Any]], name: str) -> list[dict[str, Any]]:
    """Menu items the name can mean: an exact name wins, otherwise every name match."""
    exact = [i for i in menu if _key(i["name"]) == _key(name)]
    if exact:
        return exact
    return [i for i in menu if matches(name, i["name"])]


def _names(items: list[dict[str, Any]]) -> str:
    return ", ".join(f"'{i['name']}' (menu_item_id {i['id']})" for i in items)


def resolve_item(menu: list[dict[str, Any]], name: str, menu_item_id: int | None) -> dict:
    by_name = find_item(menu, name)
    if menu_item_id is not None:
        item = next((i for i in menu if i["id"] == menu_item_id), None)
        if item and same_item_name(name, item["name"]):
            return item
        actual = (
            f"menu_item_id {menu_item_id} is '{item['name']}'"
            if item
            else f"There is no menu item {menu_item_id}"
        )
        if by_name:
            raise LineError(f"{actual}, not '{name}'. Matching items: {_names(by_name)}.")
        raise LineError(f"{actual}, and no menu item is called '{name}'. Use search_menu.")
    if len(by_name) == 1:
        return by_name[0]
    if by_name:
        raise LineError(f"'{name}' could be {_names(by_name)}. Ask the user which one.")
    raise LineError(f"No menu item is called '{name}'. Use search_menu.")


def _all_options(detail: dict[str, Any]) -> list[dict[str, Any]]:
    return [m for g in detail.get("modifier_groups", []) for m in g["modifiers"]]


def _option_list(detail: dict[str, Any]) -> str:
    groups = detail.get("modifier_groups", [])
    if not groups:
        return f"'{detail['name']}' has no options."
    parts = [
        f"{g['name']}: " + ", ".join(f"{m['name']} (id={m['id']})" for m in g["modifiers"])
        for g in groups
    ]
    return f"Options of '{detail['name']}': " + "; ".join(parts) + "."


def resolve_option(detail: dict[str, Any], said: str) -> int:
    options = _all_options(detail)
    key = _key(said)
    target = OPTION_ALIASES.get(key, key)
    for m in options:
        if _key(m["name"]) in (key, target):
            return m["id"]
    loose = [m for m in options if matches(said, m["name"])]
    if len(loose) == 1:
        return loose[0]["id"]
    raise LineError(f"'{said}' is not an option of '{detail['name']}'. {_option_list(detail)}")


def resolve_line(
    line: dict[str, Any], menu: list[dict[str, Any]], details: dict[int, dict[str, Any]]
) -> dict[str, Any]:
    """One line as the POS API wants it. `details` maps menu_item_id -> get_menu_item result."""
    item = resolve_item(menu, line["name"], line.get("menu_item_id"))
    detail = details[item["id"]]
    ids = list(line.get("modifier_ids") or [])
    ids += [resolve_option(detail, o) for o in line.get("options") or []]
    return {
        "menu_item_id": item["id"],
        "quantity": line.get("quantity", 1),
        "modifier_ids": list(dict.fromkeys(ids)),  # "Acısız" twice is one choice
        "note": line.get("note", ""),
    }


def same_table(said: str, actual: str) -> bool:
    """'Terrace 1' == 'terrace 1' == 'terrace1' == 'Terrace 1 masası', but 'Hall 10' != 'Hall 1'."""
    s, a = normalize(said), normalize(actual)
    if s.replace(" ", "") == a.replace(" ", ""):
        return True
    s, a = f" {' '.join(s.split())} ", f" {' '.join(a.split())} "
    return a in s


_TODAY = {"today", "bugun", "now", "simdi", "0"}
_YESTERDAY = {"yesterday", "dun", "-1"}


def resolve_day(value: str | None, today: date) -> str | None:
    """'today' / 'bugün' / 'yesterday' / 'dün' / '-7' -> YYYY-MM-DD; anything else unchanged.

    Small models get the year of "yesterday" wrong (2024-11-16 in 2026); a word they cannot.
    """
    if value is None:
        return None
    key = normalize(str(value)).replace(" ", "")
    if key in _TODAY:
        return today.isoformat()
    if key in _YESTERDAY:
        return (today - timedelta(days=1)).isoformat()
    if key.startswith("-") and key[1:].isdigit():
        return (today - timedelta(days=int(key[1:]))).isoformat()
    return str(value)


def merge_lines(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Identical lines become one: '1 x Adana (Spicy)' twice = '2 x Adana (Spicy)'."""
    merged: dict[tuple, dict[str, Any]] = {}
    for line in lines:
        key = (line["menu_item_id"], tuple(sorted(line["modifier_ids"])), line.get("note", ""))
        if key in merged:
            merged[key]["quantity"] += line["quantity"]
        else:
            merged[key] = dict(line)
    return list(merged.values())
