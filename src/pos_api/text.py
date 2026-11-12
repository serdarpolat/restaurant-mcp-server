"""Turkish-aware text normalization for forgiving search ("iskender" finds "İskender")."""

_UPPER = str.maketrans({"İ": "i", "I": "ı"})
_ASCII = str.maketrans({"ı": "i", "ş": "s", "ğ": "g", "ü": "u", "ö": "o", "ç": "c", "â": "a"})


def normalize(text: str) -> str:
    return text.translate(_UPPER).lower().translate(_ASCII).strip()


def matches(query: str, *fields: str) -> bool:
    haystack = " ".join(normalize(f) for f in fields)
    return all(token in haystack for token in normalize(query).split())
