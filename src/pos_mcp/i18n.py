"""The user's language for what write tools say back.

The menu, option and table names are English data, but guests and AI agents (this project's
whole premise) often write in Turkish, and a model that copies a result such as "OPENED order
#12 on Hall 4: 1 x Adana Kebab (Spicy)" into its answer tends to drift into English even when
the user wrote in Turkish. So every write tool takes `reply_language`, and the server writes
its summaries, previews and approval questions in that language: the text the model is most
likely to copy is already in the user's language. This works in every MCP client, because
tool results always reach the model (server instructions may not).

Which language? Small models judge it badly: asked for "the language of the user's
message", a 24B model wrote 'en' for half of the Turkish requests (the data is English) and
'tr' for some English ones. Copying text is easier than classifying it, so write tools also
take user_message, the user's words verbatim, and the server detects the language itself
(language.detect_message, Turkish/English). reply_language is the fallback for other
languages and for messages too short to tell ("ok").

Turkish and English texts are written out; any other language gets English text plus an
explicit "answer the user in <language>" line.
"""

from contextvars import ContextVar
from typing import Annotated, Any

from pydantic import Field

from pos_api.text import normalize
from pos_mcp.language import detect_message

UserMessage = Annotated[
    str,
    Field(
        description="The user's latest message, copied word for word (not translated, not "
        "summarized). The server answers in that message's language; answer the user in it "
        "too. Not stored.",
        min_length=1,
        max_length=2000,
    ),
]
ReplyLanguage = Annotated[
    str | None,
    Field(
        description="Optional: the user's language as a code ('en', 'tr', 'de'...), used when "
        "it cannot be told from user_message.",
        max_length=20,
    ),
]
UserMessageOptional = Annotated[
    str | None,
    Field(
        description="Optional: the user's latest message, copied word for word. Read tools "
        "return data to describe yourself, not a sentence to copy, so pass this to get a "
        "reminder of which language to answer in.",
        max_length=2000,
    ),
]

_ALIASES = {
    "en": "en",
    "eng": "en",
    "english": "en",
    "ingilizce": "en",
    "tr": "tr",
    "tur": "tr",
    "turkish": "tr",
    "turkce": "tr",
    "de": "de",
    "german": "de",
    "deutsch": "de",
    "fr": "fr",
    "french": "fr",
    "ru": "ru",
    "russian": "ru",
    "ar": "ar",
    "arabic": "ar",
    "es": "es",
    "spanish": "es",
}
LANGUAGE_NAMES = {
    "en": "English",
    "tr": "Turkish",
    "de": "German",
    "fr": "French",
    "ru": "Russian",
    "ar": "Arabic",
    "es": "Spanish",
}

_current: ContextVar[str] = ContextVar("reply_language", default="en")


def code(language: str | None) -> str:
    """'English' / 'EN' / 'en-US' -> 'en'. Unknown codes are kept ('nl')."""
    key = normalize(language or "").replace("_", "-").split("-")[0].strip()
    return _ALIASES.get(key, key or "en")


def use(user_message: str | None, language: str | None = None) -> str:
    """Set the reply language for the rest of this tool call; returns its code.

    The language of the user's own words wins; the model's reply_language is the fallback.
    """
    lang = detect_message(user_message) or (code(language) if language else "en")
    _current.set(lang)
    return lang


def current() -> str:
    return _current.get()


def name(lang: str | None = None) -> str:
    lang = lang or current()
    return LANGUAGE_NAMES.get(lang, lang)


def reply_note() -> dict[str, str]:
    """Put last in every write result: the language to answer in, after the Turkish data."""
    return {"answer_the_user_in": name()}


# --------------------------------------------------------------------------- #
# Option names: English data, glossed for Turkish-speaking users ("Spicy (acılı)")
# --------------------------------------------------------------------------- #

OPTION_GLOSS = {
    "spicy": "acılı",
    "mild": "az acılı",
    "not spicy": "acısız",
    "large": "büyük boy",
    "1.5 portion": "1.5 porsiyon",
    "extra cheese": "ekstra kaşar",
    "extra egg": "ekstra yumurta",
}


GROUP_GLOSS = {
    "spice level": "Acı seviyesi",
    "portion": "Porsiyon",
    "size": "Boy",
    "pide extras": "Pide ekstraları",
}


def _turkish_lower(text: str) -> str:
    return text.replace("I", "ı").replace("İ", "i").lower()


def ask_option(item: str, group: dict[str, Any], quantity: int = 1) -> str:
    """'Spice level for the Adana Kebab: Spicy, Mild or Not Spicy?' /
    'Adana Kebab için acı seviyesi ne olsun: Spicy (acılı), Mild (az acılı) ya da
    Not Spicy (acısız)?'"""
    turkish = current() == "tr"
    names = [m["name"] for m in group["modifiers"]]
    shown = (
        [
            f"{n} ({OPTION_GLOSS[normalize(n)]})" if normalize(n) in OPTION_GLOSS else n
            for n in names
        ]
        if turkish
        else names
    )
    choices = shown[0] if len(shown) == 1 else f"{', '.join(shown[:-1])} {t('or')} {shown[-1]}"
    label = (
        _turkish_lower(GROUP_GLOSS.get(normalize(group["name"]), group["name"]))
        if turkish
        else group["name"]
    )
    if quantity > 1:
        item = f"{quantity} {item}"
    text = t("ask_option", item=item, group=label, choices=choices)
    if quantity > 1 and len(names) > 1:
        text += t("ask_split", first=names[0], second=names[-1])
    return text


def options(text: str) -> str:
    """'Spicy, Large' -> 'Spicy = acılı, Large = büyük boy' when replying in Turkish."""
    if current() != "tr" or not text:
        return text
    out = []
    for part in (p.strip() for p in text.split(",")):
        gloss = OPTION_GLOSS.get(normalize(part))
        out.append(f"{part} = {gloss}" if gloss else part)
    return ", ".join(out)


# --------------------------------------------------------------------------- #
# Sentences
# --------------------------------------------------------------------------- #

_TEXT: dict[str, dict[str, str]] = {
    "opened_table": {
        "en": "OPENED order #{order_id} on {table}: {lines}",
        "tr": "AÇILDI: {table} için #{order_id} numaralı sipariş: {lines}",
    },
    "added_table": {
        "en": "ADDED to {table}'s open order #{order_id}: {lines}",
        "tr": "EKLENDİ: {table} masasının açık siparişine (#{order_id}): {lines}",
    },
    "opened_channel": {
        "en": "OPENED {channel} order #{order_id}: {lines}",
        "tr": "AÇILDI: #{order_id} numaralı {channel} siparişi: {lines}",
    },
    "added_order": {
        "en": "ADDED to order #{order_id} ({where}): {lines}",
        "tr": "EKLENDİ: #{order_id} numaralı siparişe ({where}): {lines}",
    },
    "order_total": {"en": "Order total {total}.", "tr": "Sipariş toplamı {total}."},
    "table_status": {
        "en": "{table} is now {status}.",
        "tr": "{table} artık {status}.",
    },
    "status_free": {"en": "free", "tr": "boş"},
    "status_reserved": {
        "en": "reserved (no time or guest name is stored)",
        "tr": "rezerve (saat ve misafir adı tutulmuyor)",
    },
    # previews
    "void_preview": {
        "en": "Void {line} on order #{order_id} ({where}). Reason: {reason}.",
        "tr": "#{order_id} numaralı siparişten ({where}) {line} iptal edilecek. Sebep: {reason}.",
    },
    "cancel_preview": {
        "en": "Cancel order #{order_id} ({where}, {count} lines, {total}). Reason: {reason}.",
        "tr": "#{order_id} numaralı sipariş ({where}, {count} satır, {total}) iptal edilecek. "
        "Sebep: {reason}.",
    },
    "pay_preview": {
        "en": "Close order #{order_id} ({where}): charge {due} by {method}",
        "tr": "#{order_id} numaralı sipariş ({where}) kapatılacak: {method} ile {due} alınacak",
    },
    "pay_discount": {
        "en": " after {percent}% discount ({reason})",
        "tr": " (%{percent} indirim sonrası; sebep: {reason})",
    },
    "purchase_preview": {
        "en": "Add {quantity} {unit} of {ingredient} to stock. Note: {note}",
        "tr": "Stoğa {quantity} {unit} {ingredient} eklenecek. Not: {note}",
    },
    "stock_back": {
        "en": " Ingredients go back to stock.",
        "tr": " Malzemeler stoğa geri eklenecek.",
    },
    "stock_kept": {"en": " Stock is not returned.", "tr": " Stok geri eklenmeyecek."},
    "ask_approval": {
        "en": "Do you approve? (yes / no)",
        "tr": "Onaylıyor musunuz? (evet / hayır)",
    },
    # results of approved actions
    "voided": {
        "en": "VOIDED {line} on order #{order_id} ({where}). {total_text}",
        "tr": "İPTAL EDİLDİ: #{order_id} numaralı siparişten ({where}) {line}. {total_text}",
    },
    "cancelled": {
        "en": "CANCELLED order #{order_id} ({where}). Reason: {reason}.",
        "tr": "İPTAL EDİLDİ: #{order_id} numaralı sipariş ({where}). Sebep: {reason}.",
    },
    "paid": {
        "en": "PAID and closed order #{order_id} ({where}): {total} by {method}.",
        "tr": "ÖDENDİ ve kapatıldı: #{order_id} numaralı sipariş ({where}), {method} ile {total}.",
    },
    "purchased": {
        "en": "RECORDED: {quantity} {unit} of {ingredient} added to stock; now {stock} {unit}.",
        "tr": "KAYDEDİLDİ: stoğa {quantity} {unit} {ingredient} eklendi; şimdi {stock} {unit}.",
    },
    # questions the server writes for the user (missing table or required choice)
    "ask_table": {
        "en": "Which table is this for? (Or is it pickup or delivery?)",
        "tr": "Hangi masa için? (Paket servis ya da kurye ise onu söyleyin.)",
    },
    "ask_option": {
        "en": "{group} for the {item}: {choices}?",
        "tr": "{item} için {group} ne olsun: {choices}?",
    },
    "ask_split": {
        "en": " (If they differ, say e.g. 'one {first}, one {second}'.)",
        "tr": " (Farklı olacaksa söyleyin, örn. '1 {first}, 1 {second}'.)",
    },
    "or": {"en": "or", "tr": "ya da"},
    "method_cash": {"en": "cash", "tr": "nakit"},
    "method_credit_card": {"en": "credit card", "tr": "kredi kartı"},
    "method_meal_voucher": {"en": "meal voucher", "tr": "yemek çeki"},
    "method_apple_pay": {"en": "Apple Pay", "tr": "Apple Pay"},
    "method_google_pay": {"en": "Google Pay", "tr": "Google Pay"},
    "channel_pickup": {"en": "pickup", "tr": "paket servis"},
    "channel_delivery": {"en": "delivery", "tr": "kurye"},
    "channel_dineIn": {"en": "dine-in", "tr": "masa"},
}


def t(key: str, **values: Any) -> str:
    """The sentence in the current language (English for languages without a text)."""
    texts = _TEXT[key]
    return texts.get(current(), texts["en"]).format(**values)


def word(key: str, value: str) -> str:
    """t() for single words such as payment methods; unknown values pass through."""
    full = f"{key}_{value}"
    return t(full) if full in _TEXT else value
