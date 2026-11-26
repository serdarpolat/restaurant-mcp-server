"""Forgiving, bilingual search ("iskender" finds "Iskender Kebab", "corba" finds "Soup" items).

The menu is in English, but guests and AI agents (this project's whole premise) often ask in
Turkish. Each query word matches a name word if it is a prefix of it (or the reverse, for
plurals: "kebabs"), if it is a close spelling ("kebab" ~ "kebap"), or if its Turkish form
matches the English menu word via GLOSSARY.
"""

_UPPER = str.maketrans({"İ": "i", "I": "ı"})
_ASCII = str.maketrans({"ı": "i", "ş": "s", "ğ": "g", "ü": "u", "ö": "o", "ç": "c", "â": "a"})
_PUNCT = str.maketrans({c: " " for c in ",.;:!?()[]\"'&/-+"})

# Turkish stems -> English words actually on this menu (normalized). Covers the dish/ingredient
# words a Turkish-speaking guest would type; a word not listed here still matches by spelling,
# and the agent can translate anything else. A few English alt-spellings are included too.
GLOSSARY: dict[str, tuple[str, ...]] = {
    "corba": ("soup",),
    "mercimek": ("lentil",),
    "baslangic": ("starter", "appetizer"),
    "tavuk": ("chicken",),
    "kanat": ("wing",),
    "kuzu": ("lamb",),
    "dana": ("ground", "beef"),
    "sis": ("shish", "skewer"),
    "pirzola": ("chop", "cutlet"),
    "kofte": ("meatball",),
    "kofta": ("meatball",),
    "izgara": ("grill", "grilled"),
    "karisik": ("mixed", "mix"),
    "patlican": ("eggplant",),
    "kasar": ("cheese",),
    "yumurta": ("egg",),
    "lahmacun": ("flatbread", "pizza"),
    "pide": ("flatbread", "pizza"),
    "salata": ("salad",),
    "coban": ("shepherd",),
    "tatli": ("dessert", "sweet"),
    "fistik": ("pistachio",),
    "sutlac": ("pudding",),
    "icecek": ("drink", "beverage"),
    "cay": ("tea",),
    "kahve": ("coffee",),
    "su": ("water",),
    "kola": ("cola", "coke"),
    "limonata": ("lemonade",),
    "salgam": ("turnip",),
    "ayran": ("buttermilk",),
    "acili": ("spicy",),
    # ingredients (stock questions in Turkish)
    "kiyma": ("mince", "minced", "ground"),
    "but": ("thigh",),
    "hamur": ("dough",),
    "pirinc": ("rice",),
    "domates": ("tomato",),
    "sogan": ("onion",),
    "biber": ("pepper", "chili"),
    "maydanoz": ("parsley",),
    "limon": ("lemon",),
    "tereyag": ("butter",),
    # common English alt-spellings worth normalizing explicitly
    "kebob": ("kebab",),
    "yoghurt": ("yogurt",),
    "aubergine": ("eggplant",),
    "cutlet": ("chop",),
    "drink": ("beverage",),
}

# Words that carry no dish name: English/Turkish fillers and order words.
STOPWORDS = {
    "a", "an", "the", "of", "and", "with", "some", "please", "order", "portion", "portions",
    "plate", "plates", "one", "two", "three", "four", "five", "x", "bir", "iki", "uc", "dort",
    "bes", "tane", "adet", "porsiyon", "ve", "ile", "lutfen",
    # "turnip juice" / "şalgam suyu" name Şalgam ("suyu" is not Su)
    "juice", "suyu",
}  # fmt: skip


def normalize(text: str) -> str:
    return text.translate(_UPPER).lower().translate(_ASCII).strip()


def words(text: str) -> list[str]:
    return normalize(text).translate(_PUNCT).split()


def query_words(query: str) -> list[str]:
    """Words that name something; numbers and fillers ("2 adana", "two of the") dropped."""
    return [w for w in words(query) if w not in STOPWORDS and not w.isdigit()]


def _singular(word: str) -> str:
    for suffix in ("es", "s"):
        if len(word) > 4 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def _alternatives(word: str) -> set[str]:
    base = _singular(word)
    return {word, base, *GLOSSARY.get(word, ()), *GLOSSARY.get(base, ())}


def _close(a: str, b: str) -> bool:
    """One typo apart: a changed, missing, extra or swapped letter ('kebab'~'kebap',
    'lahmajun'~'lahmacun'). Short words must match exactly."""
    if min(len(a), len(b)) < 4 or abs(len(a) - len(b)) > 1 or a == b:
        return a == b
    i = 0
    while a[i] == b[i]:
        i += 1
    if len(a) == len(b):
        swapped = a[i + 2 :] == b[i + 2 :] and a[i : i + 2] == b[i : i + 2][::-1]
        return a[i + 1 :] == b[i + 1 :] or swapped
    longer, shorter = (a, b) if len(a) > len(b) else (b, a)
    return longer[i + 1 :] == shorter[i:]


def word_matches(word: str, text_words: list[str], text: str) -> bool:
    for alt in _alternatives(word):
        if " " in alt:
            if alt in text:
                return True
            continue
        for tw in text_words:
            if len(alt) <= 3:  # "su", "cay", "sis": whole words only ("su" is not "sütlaç")
                if tw == alt:
                    return True
            elif tw.startswith(alt) or (len(tw) >= 3 and alt.startswith(tw)) or _close(alt, tw):
                return True
    return False


def match_count(query: str, *fields: str) -> int:
    """How many of the query's words match the fields."""
    text = " ".join(normalize(f) for f in fields)
    text_words = text.translate(_PUNCT).split()
    return sum(word_matches(w, text_words, text) for w in query_words(query))


def matches(query: str, *fields: str) -> bool:
    """True if every word of the query matches (an empty query matches everything)."""
    return match_count(query, *fields) == len(query_words(query))
