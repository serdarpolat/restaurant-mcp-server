"""What the user's own words say about an order: quantities, and whether they gave an option.

Write tools receive user_message, the user's latest message word for word. The server reads
it to catch two silent errors of small models before anything is saved:

- quantities: "Salon 3'e 2 acılı Adana" sent as 1 x Adana Kebap (the model's answer then
  says "2 Adana" while the order has one: a wrong bill nobody notices);
- options chosen for the user: "Salon 4'e 1 Adana" sent with 'Acılı' although the user never
  said how spicy.

The eval uses the same reader on the model's final answer, to check that what the model
tells the user matches what was saved.

Deliberately conservative: a quantity counts only when a number stands right before an
item's name ("2 çay", "three lahmacun", "1 x Ayran") or right after it with a unit
("Ayran: 2 adet"). Anything unclear (no number, an item not in the order, a name with a
case suffix such as "Adana'yı", which refers to something already ordered) is skipped, so a
correct order is never refused because of how the user phrased it.
"""

import re
from collections.abc import Iterable
from typing import Any

from pos_api.text import normalize, word_matches, words

NUMBERS_EN = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "a": None, "an": None,
}  # fmt: skip
NUMBERS_TR = {
    "bir": 1, "iki": 2, "uc": 3, "dort": 4, "bes": 5, "alti": 6, "yedi": 7, "sekiz": 8,
    "dokuz": 9, "on": 10,
}  # fmt: skip
# "on" is 10 in Turkish but a preposition in English ("on Salon 4").
_AMBIGUOUS = {"on": "tr"}
UNITS = {"adet", "tane", "porsiyon", "x", "servings", "serving", "pieces", "piece", "pcs"}
_FRACTION = {"bucuk", "half", "yarim"}
MAX_QUANTITY = 50
_WINDOW = 4  # words between a number and the item's name ("2 büyük boy acısız ayran")

_TOKEN = re.compile(
    r"\d+[.,]\d+|\d+[.)](?=\s|$)|[#]?[a-z0-9]+(?:['’][a-z]+)?|:|[,;\n•–—]|\s-\s|\.(?=\s|$)"
)
# Clause breaks: a number never reaches past one to an item ("1 adet, 560 TRY - Ayran"). A
# number written after its item may cross a colon only ("Ayran: 2 adet").
_BREAK = "|"
_TABLE = "qtablq"
_COLON = ":"


def _tokens(text: str, table_names: Iterable[str] = ()) -> list[str]:
    """Normalized words; table names ('Salon 2'e') become one placeholder token so their
    numbers are never read as quantities."""
    text = normalize(text)
    for name in table_names:
        parts = [re.escape(p) for p in words(name)]
        if parts:
            text = re.sub(r"\b" + r"\s*".join(parts) + r"\b(?:['’][a-z]+)?", " qtablq ", text)
    out = []
    for token in _TOKEN.findall(text):
        if token == ":":
            out.append(_COLON)
        elif not re.match(r"[#a-z0-9]", token):
            out.append(_BREAK)
        else:
            out.append(token)
    return out


def _number(token: str, lang: str | None) -> int | None:
    """Quantity a token stands for, or None. List markers ('1.'), decimals, '#12' are not."""
    if token.startswith("#") or "'" in token or "’" in token:
        return None
    if re.fullmatch(r"\d+", token):
        value = int(token)
    elif m := re.fullmatch(r"(\d+)x|x(\d+)", token):
        value = int(m.group(1) or m.group(2))
    elif token in NUMBERS_TR:
        if token in _AMBIGUOUS and lang != _AMBIGUOUS[token]:
            return None
        value = NUMBERS_TR[token]
    elif token in NUMBERS_EN and NUMBERS_EN[token] is not None:
        value = NUMBERS_EN[token]
    else:
        return None
    return value if 1 <= value <= MAX_QUANTITY else None


def _names(token: str, item_name: str) -> bool:
    """Does the token name this item? Its first word decides ('adana' -> 'Adana Kebap',
    'teas' -> 'Çay', 'turnip' -> 'Şalgam'); a token with a case suffix ('adana'yı') does
    not, because it points at something already ordered."""
    if "'" in token or "’" in token or token == _TABLE or len(token) < 2:
        return False
    first = words(item_name)[:1]
    if not first:
        return False
    forms = {token}
    if len(token) > 3 and token.endswith("s"):  # "teas", "kebabs" (search keeps 4+ letters)
        forms |= {token[:-1], token[:-2] if token.endswith("es") else token[:-1]}
    return any(word_matches(f, first, first[0]) for f in forms)


def _item_at(tokens: list[str], i: int, items: dict[int, str]) -> int | None:
    """The single item named by tokens[i] (the next word decides between 'Tavuk Şiş' and
    'Tavuk Kanat'); None if none or still ambiguous."""
    hits = [iid for iid, name in items.items() if _names(tokens[i], name)]
    if len(hits) > 1 and i + 1 < len(tokens):
        nxt = tokens[i + 1]
        narrowed = [
            iid
            for iid in hits
            if len(words(items[iid])) > 1 and word_matches(nxt, words(items[iid])[1:], items[iid])
        ]
        hits = narrowed or hits
    return hits[0] if len(hits) == 1 else None


def quantities(
    text: str,
    items: dict[int, str],
    table_names: Iterable[str] = (),
    lang: str | None = None,
) -> dict[int, int]:
    """Quantities the text states for these items {menu_item_id: name} -> {id: total}.

    "2 acılı Adana ve 2 ayran" -> {Adana: 2, Ayran: 2}; "one spicy Adana and one mild Adana"
    -> {Adana: 2}; "Adana Kebap (Acılı): 1 adet" -> {Adana: 1}. Items without a clear number
    are left out.
    """
    found: dict[int, int] = {}
    for item, value in quantity_mentions(text, items, table_names, lang):
        found[item] = found.get(item, 0) + value
    return found


def quantity_mentions(
    text: str,
    items: dict[int, str],
    table_names: Iterable[str] = (),
    lang: str | None = None,
) -> list[tuple[int, int]]:
    """Every (item, number) the text states, in order: an answer may name an item twice
    ("2 çay eklendi: 2 x Çay") where a request names it once per group of units."""
    tokens = _tokens(text, table_names)
    found: list[tuple[int, int]] = []
    used: set[int] = set()
    for i, token in enumerate(tokens):
        value = _number(token, lang)
        if value is None:
            continue
        nxt = tokens[i + 1] if i + 1 < len(tokens) else ""
        if nxt in _FRACTION:
            continue
        for j in range(i + 1, min(i + 1 + _WINDOW, len(tokens))):
            if tokens[j] in (_BREAK, _COLON, _TABLE) or _number(tokens[j], lang) is not None:
                break
            item = _item_at(tokens, j, items)
            if item is not None:
                found.append((item, value))
                used.add(i)
                break
            if any(_names(tokens[j], n) for n in items.values()):
                break  # an item, but not a clear one: skip this number
    # "Ayran: 2 adet", "Ayran x2": the number comes after the name, with a unit.
    for i in range(len(tokens)):
        item = _item_at(tokens, i, items)
        if item is None:
            continue
        for j in range(i + 1, min(i + 1 + _WINDOW, len(tokens))):
            if j in used or tokens[j] in (_BREAK, _TABLE):
                break
            if tokens[j] == _COLON:
                continue
            value = _number(tokens[j], lang)
            if value is None:
                if j > i + 1 and _item_at(tokens, j, items) is not None:
                    break
                continue
            unit = tokens[j + 1] if j + 1 < len(tokens) else ""
            if unit in UNITS or tokens[j - 1] == "x" or re.fullmatch(r"x\d+", tokens[j]):
                found.append((item, value))
                used.add(j)
            break
    return found


def mentions(text: str, item_name: str, table_names: Iterable[str] = ()) -> bool:
    """Does the message name this item as something to order ('2 Adana', 'one Adana kebab')?"""
    return any(_names(t, item_name) for t in _tokens(text, table_names))


# Words that say an order has no table, by themselves: the model may still default to
# dine-in and either leave the table out or ask which table (server.py's _NO_TABLE
# covers the same words when the model names a "table" that is really the channel).
_TAKEAWAY_WORDS = {"paket", "takeaway", "togo"}
_DELIVERY_WORDS = {"kurye", "delivery", "deliver"}
_PICKUP_PHRASE = ("gel", "al")  # "gel al" = "come and get it"


def channel_from_message(text: str) -> str | None:
    """'takeaway', 'delivery' or None: did the user say this order has no table?

    A safety net for create_order: a model that reads "Paket servis: 3 lahmacun" may
    still leave channel at its 'dine_in' default and ask which table instead of placing
    a takeaway order. Only used when the model gave no table either way.
    """
    tokens = _tokens(text)
    words_here = set(tokens)
    if words_here & _DELIVERY_WORDS:
        return "delivery"
    if words_here & _TAKEAWAY_WORDS:
        return "takeaway"
    for i in range(len(tokens) - 1):
        if (tokens[i], tokens[i + 1]) == _PICKUP_PHRASE:
            return "takeaway"
    return None


# Words that are about an option group without naming one choice: "acı olmasın", "spice".
GROUP_WORDS = {
    "aci seviyesi": {"aci", "acili", "acisiz", "biber", "spicy", "spice", "hot", "mild",
                     "chili", "chilli", "pepper", "medium"},
}  # fmt: skip
_GENERIC = {"a", "no", "not", "non", "without", "little", "very", "slightly", "boy", "and"}


def _group_vocabulary(group: dict[str, Any], aliases: dict[str, str]) -> set[str]:
    names = {normalize(m["name"]) for m in group.get("modifiers", [])}
    vocab = set(GROUP_WORDS.get(normalize(group["name"]), set()))
    vocab |= {w for n in names for w in n.split()}
    vocab |= {w for said, target in aliases.items() if target in names for w in said.split()}
    return {w for w in vocab if w not in _GENERIC and not w.isdigit()}


def speaks_of_group(
    text: str, group: dict[str, Any], aliases: dict[str, str], table_names: Iterable[str] = ()
) -> bool:
    """Did the user say anything about this option group ('acılı', 'not spicy', 'acı olsun')?"""
    vocab = _group_vocabulary(group, aliases)
    for token in _tokens(text, table_names):
        token = re.split(r"['’]", token)[0]
        for v in vocab:
            if token == v or (len(v) >= 3 and token.startswith(v)):
                return True
            if len(token) >= 3 and v.startswith(token):
                return True
    return False


# --------------------------------------------------------------------------- #
# Kitchen notes
# --------------------------------------------------------------------------- #

# Words a note may carry without the user saying them: linking words and politeness.
_NOTE_FILLERS = {
    "ve", "ile", "olsun", "lutfen", "icin", "de", "da", "and", "with", "please", "no", "not",
    "without", "extra", "the", "a", "an", "of", "for", "to", "on",
}  # fmt: skip
# Words of the order itself, not of a kitchen request: a note made of these (and of item,
# option and table names) only restates the order ("paket servis için 3 adet", "Salon 3").
_ORDER_WORDS = {
    "paket", "servis", "takeaway", "delivery", "kurye", "gel", "al", "masa", "masasi", "table",
    "siparis", "order", "ac", "ekle", "open", "add", "start", "tl", "try", "lira", "toplam",
    "total", "fiyat", "price",
}  # fmt: skip


def _stems(text: str, table_names: Iterable[str]) -> set[str]:
    """The message's words, plus the Turkish stems of English ones ('onions' -> 'sogan')."""
    from pos_api.text import GLOSSARY

    out: set[str] = set()
    for token in _tokens(text, table_names):
        token = re.split(r"['’]", token)[0]
        if not re.fullmatch(r"[a-z0-9]+", token):
            continue
        out.add(token)
        for form in (token, token.removesuffix("s")):
            out.update(GLOSSARY.get(form, ()))
    return out


def _said(word: str, stems: set[str]) -> bool:
    """'sogansiz' was said if the user wrote 'soğansız', 'soğan olmasın' or 'no onions'."""
    if word in stems:
        return True
    if len(word) < 4:
        return False
    return any(len(s) >= 4 and s[:4] == word[:4] for s in stems)


def note_words(
    note: str,
    detail: dict[str, Any],
    aliases: dict[str, str],
    also_known: Iterable[str] = (),
) -> list[str]:
    """The words of a note that add something: not the names of the order's items (also
    misspelt: 'Kabab'), the line's options, tables, numbers, units, order or linking words
    ('acılı Adana (2 adet)' adds nothing to an Acılı Adana line)."""
    names_of_items = [detail["name"], *also_known]
    item_words = [w for n in names_of_items for w in words(n)]
    known = set(item_words)
    names = {
        normalize(m["name"]) for g in detail.get("modifier_groups", []) for m in g["modifiers"]
    }
    known |= {w for n in names for w in n.split()}
    known |= {w for said, target in aliases.items() if target in names for w in said.split()}
    known |= UNITS | _NOTE_FILLERS | _ORDER_WORDS | set(NUMBERS_TR) | set(NUMBERS_EN)
    return [
        w
        for w in words(note)
        if w not in known
        and len(w) > 2  # case endings split off by the apostrophe ('Salon 3'e')
        and not re.fullmatch(r"[\d.,x]+", w)
        and not word_matches(w, item_words, " ".join(item_words))
    ]


def note_status(
    note: str,
    user_message: str,
    detail: dict[str, Any],
    aliases: dict[str, str],
    table_names: Iterable[str] = (),
    also_known: Iterable[str] = (),
) -> tuple[str, list[str]]:
    """'ok', 'empty' (nothing beyond the line itself: drop it) or 'invented' (words the user
    never said, such as 'soğansız' for "Salon 3'e 2 acılı Adana"), with those words.

    `also_known`: the other items of the same order (their names restate the order too).
    Checked only when the message names the item: an answer to a question ("acılı olsun")
    may come after the note was given, so it cannot be held against it.
    """
    if not note.strip():
        return "ok", []
    extra = note_words(note, detail, aliases, [*also_known, *table_names])
    if not extra:
        return "empty", []
    if not mentions(user_message, detail["name"], table_names):
        return "ok", []
    stems = _stems(user_message, table_names)
    unsaid = [w for w in extra if not _said(w, stems)]
    return ("invented", unsaid) if unsaid else ("ok", [])
