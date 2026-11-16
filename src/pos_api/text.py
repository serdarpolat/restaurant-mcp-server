"""Forgiving, Turkish-aware search ("iskender" finds "İskender", "adana kebab" finds "Adana Kebap").

The menu is in Turkish, but guests and AI agents often search in English. Each query word
matches a name word if it is a prefix of it (or the reverse, for plurals: "kebabs"), if it is
a close spelling ("kebab" ~ "kebap"), or if its English translation matches (GLOSSARY).
"""

_UPPER = str.maketrans({"İ": "i", "I": "ı"})
_ASCII = str.maketrans({"ı": "i", "ş": "s", "ğ": "g", "ü": "u", "ö": "o", "ç": "c", "â": "a"})
_PUNCT = str.maketrans({c: " " for c in ",.;:!?()[]\"'&/-+"})

# English -> Turkish stems (normalized). Covers the dish words of this menu; a word not listed
# here still matches by spelling, and the agent can translate anything else.
GLOSSARY: dict[str, tuple[str, ...]] = {
    "kebab": ("kebap", "kebab"),
    "kebob": ("kebap", "kebab"),
    "soup": ("corba",),
    "lentil": ("mercimek",),
    "yogurt": ("yogurt", "yayla", "haydari"),
    "yoghurt": ("yogurt", "yayla", "haydari"),
    "starter": ("baslangic",),
    "appetizer": ("baslangic",),
    "meze": ("baslangic", "haydari", "ezme"),
    "chicken": ("tavuk",),
    "wing": ("kanat",),
    "lamb": ("kuzu",),
    "beef": ("dana",),
    "skewer": ("sis",),
    "shish": ("sis",),
    "chop": ("pirzola",),
    "cutlet": ("pirzola",),
    "meatball": ("kofte",),
    "kofta": ("kofte",),
    "kofte": ("kofte",),
    "grill": ("izgara",),
    "grilled": ("izgara",),
    "mixed": ("karisik",),
    "mix": ("karisik",),
    "eggplant": ("patlican", "ali nazik"),
    "aubergine": ("patlican", "ali nazik"),
    "cheese": ("kasar",),
    "egg": ("yumurta",),
    "pizza": ("lahmacun", "pide"),
    "flatbread": ("lahmacun", "pide"),
    "salad": ("salata",),
    "shepherd": ("coban",),
    "dessert": ("tatli",),
    "sweet": ("tatli",),
    "pistachio": ("fistik",),
    "baklava": ("baklava",),
    "pudding": ("sutlac",),
    "drink": ("icecek",),
    "beverage": ("icecek",),
    "tea": ("cay",),
    "coffee": ("kahve",),
    "water": ("su",),
    "coke": ("kola",),
    "cola": ("kola",),
    "lemonade": ("limonata",),
    "soda": ("soda",),
    "turnip": ("salgam",),
    "buttermilk": ("ayran",),
    "spicy": ("acili",),
    # ingredients (stock questions in English)
    "mince": ("kiyma",),
    "minced": ("kiyma",),
    "ground": ("kiyma",),
    "thigh": ("but",),
    "dough": ("hamur",),
    "rice": ("pirinc",),
    "tomato": ("domates",),
    "tomatoe": ("domates",),
    "onion": ("sogan",),
    "pepper": ("biber",),
    "chili": ("biber",),
    "parsley": ("maydanoz",),
    "lemon": ("limon",),
    "butter": ("tereyag",),
    "bulgur": ("bulgur",),
}

# Words that carry no dish name: English/Turkish fillers and order words.
STOPWORDS = {
    "a", "an", "the", "of", "and", "with", "some", "please", "order", "portion", "portions",
    "plate", "plates", "one", "two", "three", "four", "five", "x", "bir", "iki", "uc", "dort",
    "bes", "tane", "adet", "porsiyon", "ve", "ile", "lutfen",
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
