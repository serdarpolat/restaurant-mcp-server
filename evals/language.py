"""Which language is an answer written in? Small and dependency-free, for Turkish vs English.

The hard part is that an English answer about this restaurant is full of Turkish names
("1 x Adana Kebap (Acılı) on Bahçe 2"). So the detector ignores letters and names and
counts only function words and common phrasing words, which carry the language of the
sentence around the names. A word that is part of a menu, option or table name is never
in these lists.
"""

import re


def _words(text: str) -> frozenset[str]:
    return frozenset(text.split())


TURKISH = _words(
    """
    ve veya ile ama fakat ancak için gibi kadar sonra önce şimdi artık daha çok en hiç
    bir bu şu o bunlar şunlar her tüm hepsi bazı
    var yok değil evet hayır tamam lütfen
    mı mi mu mü mısınız misiniz musunuz müsünüz mıyım miyim
    ne nedir hangi hangisi kaç nasıl neden
    olarak olan oldu olsun olacak edildi edilecek yapıldı
    masa masası masasına masasındaki masanın masaya masalar masalara
    sipariş siparişi siparişe siparişin siparişler siparişini siparişiniz
    toplam toplamı tutar tutarı adet tane fiyatı fiyat hesap hesabı
    eklendi eklensin ekledim ekleyeyim ekleyelim açıldı açtım açayım açalım
    iptal silindi sildim kapatıldı ödendi alındı kaydedildi güncellendi boşaltıldı
    ister istersiniz istiyor istiyorsunuz istediğiniz seçin seçiniz belirtin belirtir
    seviyesi seviyesini seçeneği seçenekleri seçenekler stokta stoğa stok malzemeler
    bugün dün bugünün dünün satan satış satışlar raporu
    """
)

ENGLISH = _words(
    """
    the a an and or but for to of in on at with by from as into about
    is are was were be been being has have had do does did will would can could should
    this that these those it its there their they you your yours we our i my me
    not no yes please which what how many much when who
    order orders ordered table tables total item items price costs cost bill
    added add adding opened open opening cancelled canceled removed voided paid closed
    recorded updated freed reserved
    would like want choose select pick specify level option options
    today yesterday top best selling sold sales report stock low
    one two three four five
    """
)

_WORD = re.compile(r"[a-zçğıöşüâîû]+")


def _lower(text: str) -> str:
    # Python's lower() turns "I" into "i" (English) and keeps "ı" apart; Turkish dotted
    # capital "İ" lowers to "i̇" (i + combining dot): drop the dot.
    return text.lower().replace("̇", "")


def detect(text: str | None) -> str | None:
    """'tr', 'en', or None when the text is too short or mixed to tell."""
    words = _WORD.findall(_lower(text or ""))
    tr = sum(w in TURKISH for w in words)
    en = sum(w in ENGLISH for w in words)
    if tr + en < 2 or tr == en:
        return None
    # A clear majority: a few English words in a Turkish answer ("order #12") or
    # Turkish ones in an English answer ("Adana ... Acılı") must not flip it.
    if tr >= 2 * en:
        return "tr"
    if en >= 2 * tr:
        return "en"
    return None


NAMES = {"tr": "Turkish", "en": "English"}
