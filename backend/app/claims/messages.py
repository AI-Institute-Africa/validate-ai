"""Everything we say to a payer outside the console, in English, Shona and Ndebele.

Shona and Ndebele are DRAFTS written without a fluent speaker, so they are gated exactly like the
console's: a language is used for outbound messages only when it is switched on (see
`language_live`), or one string at a time once a fluent reviewer has signed it off (REVIEWED).
Otherwise the payer gets English. Never say a payment is verified here, never hint at suspicion.
"""

from typing import Any

from app.core.config import get_settings

LANGS = ("en", "sn", "nd")
LANG_NAMES = {"en": "English", "sn": "Shona", "nd": "Ndebele"}

# Strings a fluent reviewer has approved, per language. Add a key ONLY after a person approved it.
REVIEWED: dict[str, set[str]] = {"sn": set(), "nd": set()}

# The reasons a payer may be told about (blueprint 5.10). Several internal codes share one neutral
# key so the API never reveals why: a suspected-fake claim reads like any manual check.
PAYER_MESSAGE_KEY = {
    "SUSPECTED_FAKE": "MANUAL_CHECK",
    "CREDIT_DISPUTED": "MANUAL_CHECK",
    "TAMPER_SUSPECTED": "IMAGE_CHECK",
    "PAYEE_NOT_TRUSTED": "PAYEE_MISMATCH",
}

# internal reason code -> the key of its message
_REASON_CODES = (
    "CAPTURE_TOO_SMALL",
    "CAPTURE_BLURRY",
    "UNREADABLE",
    "MISSING_AMOUNT",
    "MISSING_REFERENCE",
    "TYPED_AMOUNT_DISAGREES",
    "TYPED_REFERENCE_DISAGREES",
    "DUPLICATE_FILE",
    "DUPLICATE_NEAR_FILE",
    "DUPLICATE_REFERENCE",
    "REFERENCE_ALREADY_CONSUMED",
    "RECEIPT_STATUS_NOT_SUCCESS",
    "AWAITING_CREDIT",
    "PAYEE_NOT_TRUSTED",
    "EXTRACTION_UNCONFIRMED",
    "MANY_LOW_CONFIDENCE_FIELDS",
    "TAMPER_SUSPECTED",
    "CURRENCY_MISMATCH",
    "WRONG_BENEFICIARY",
    "AMOUNT_MISMATCH",
    "PARTIAL_PAYMENT",
    "OVERPAYMENT",
    "SUSPECTED_FAKE",
    "NO_CREDIT_FOUND",
    "DOCUMENT_TRUNCATED",
    "CREDIT_DISPUTED",
)

TEXTS: dict[str, dict[str, str]] = {
    "AMOUNT_MISMATCH": {
        "en": "The amount received differs from the amount claimed.",
        "sn": "Mari yakagamuchirwa yakasiyana neyawakataura.",
        "nd": "Imali eyamukelweyo yehlukile kuleyo oyishilo.",
    },
    "AWAITING_CREDIT": {
        "en": "Your payment is waiting for confirmation from our bank records.",
        "sn": "Kubhadhara kwako kuri kumirira kusimbiswa kubva kumarekodhi edu ebhengi.",
        "nd": "Ukukhokha kwakho kulindele ukuqinisekiswa kumarekhodi ethu ebhanki.",
    },
    "CAPTURE_BLURRY": {
        "en": "The image is blurry. Please upload a clearer photo or screenshot.",
        "sn": "Mufananidzo hauna kujeka. Tumira foto kana skrini yakajeka.",
        "nd": "Isithombe asicacile. Sicela uthumele isithombe kumbe i-screenshot ecacileyo.",
    },
    "CAPTURE_TOO_SMALL": {
        "en": "The image is too small to read. Please upload a full-size screenshot.",
        "sn": "Mufananidzo mudiki zvakanyanya kuti uverengwe. Tumira skrini yakazara.",
        "nd": "Isithombe sincane kakhulu ukuthi sifundeke. Sicela uthumele i-screenshot egcweleyo.",
    },
    "CURRENCY_MISMATCH": {
        "en": "The currency paid does not match the invoice currency.",
        "sn": "Mari yawakabhadhara haienderani neyeindivhoyisi.",
        "nd": "Imali okhokhe ngayo ayivumelani lemali yeinvoyisi.",
    },
    "DOCUMENT_TRUNCATED": {
        "en": "Your document is long; our finance team will check the remaining pages.",
        "sn": "Gwaro rako rakareba; chikwata chedu chemari chichatarisa mapeji asara.",
        "nd": "Incwadi yakho ende; iqembu lethu lezimali lizahlola amakhasi asele.",
    },
    "DUPLICATE_FILE": {
        "en": "This receipt has already been submitted.",
        "sn": "Risiti iyi yakatotumirwa kare.",
        "nd": "Le risithi isithunyelwe kakade.",
    },
    "DUPLICATE_NEAR_FILE": {
        "en": "A very similar receipt has already been submitted.",
        "sn": "Risiti yakafanana nayo zvikuru yakatotumirwa kare.",
        "nd": "Irisithi efanana kakhulu isithunyelwe kakade.",
    },
    "DUPLICATE_REFERENCE": {
        "en": "This transaction reference has already been submitted.",
        "sn": "Nhamba yekubhadhara iyi yakatoshandiswa kare.",
        "nd": "Le nombolo yokukhokha isisetshenzisiwe kakade.",
    },
    "EXTRACTION_UNCONFIRMED": {
        "en": "Some payment details need a quick check by our finance team.",
        "sn": "Mamwe mashoko ekubhadhara anoda kutariswa nechikwata chedu chemari.",
        "nd": "Eminye imininingwane yokukhokha idinga ukubukwa liqembu lethu lezimali.",
    },
    "IMAGE_CHECK": {
        "en": "The receipt image needs a manual check by our finance team.",
        "sn": "Mufananidzo werisiti unoda kutariswa nechikwata chedu chemari.",
        "nd": "Isithombe sirisithi sidinga ukubukwa liqembu lethu lezimali.",
    },
    "MANUAL_CHECK": {
        "en": "Your payment needs a manual check by our finance team.",
        "sn": "Kubhadhara kwako kunoda kutariswa nechikwata chedu chemari.",
        "nd": "Ukukhokha kwakho kudinga ukubukwa liqembu lethu lezimali.",
    },
    "MANY_LOW_CONFIDENCE_FIELDS": {
        "en": "Some details were hard to read, so our finance team will check.",
        "sn": "Mamwe mashoko akaomera kuverenga, saka chikwata chedu chemari chichaatarisa.",
        "nd": "Eminye imininingwane bekunzima ukuyifunda, ngakho iqembu lethu lezimali "
        "lizayihlola.",
    },
    "MISSING_AMOUNT": {
        "en": "We could not find the amount on your receipt.",
        "sn": "Hatina kuwana mari parisiti yako.",
        "nd": "Asiyitholanga imali kurisithi yakho.",
    },
    "MISSING_REFERENCE": {
        "en": "We could not find a transaction reference on your receipt.",
        "sn": "Hatina kuwana nhamba yekubhadhara parisiti yako.",
        "nd": "Asiyitholanga inombolo yokukhokha kurisithi yakho.",
    },
    "NO_CREDIT_FOUND": {
        "en": "We have not yet seen this payment in our bank records.",
        "sn": "Hatisati taona kubhadhara uku mumarekodhi edu ebhengi.",
        "nd": "Asikakuboni lokhu kukhokha kumarekhodi ethu ebhanki.",
    },
    "OVERPAYMENT": {
        "en": "Your payment exceeds the amount due; the remainder is held for you.",
        "sn": "Kubhadhara kwako kwakapfuura mari yaidiwa; yasara yakachengetwa iwe.",
        "nd": "Ukukhokha kwakho kudlula imali edingekayo; okusele kugcinelwe wena.",
    },
    "PARTIAL_PAYMENT": {
        "en": "Your payment was recorded, but the invoice is not yet fully paid.",
        "sn": "Kubhadhara kwako kwanyorwa, asi indivhoyisi haisati yapera kubhadharwa.",
        "nd": "Ukukhokha kwakho kuqoshiwe, kodwa iinvoyisi ayikaphelelwa ukukhokhwa.",
    },
    "RECEIPT_STATUS_NOT_SUCCESS": {
        "en": "The receipt shows the payment as not completed.",
        "sn": "Risiti inoratidza kuti kubhadhara hakuna kupera.",
        "nd": "Irisithi ikhombisa ukuthi ukukhokha akuphelanga.",
    },
    "REFERENCE_ALREADY_CONSUMED": {
        "en": "This transaction has already been credited.",
        "sn": "Kubhadhara uku kwakatoverengerwa kare.",
        "nd": "Lokhu kukhokha sekubaliwe kakade.",
    },
    "TYPED_AMOUNT_DISAGREES": {
        "en": "The amount you typed does not match the receipt.",
        "sn": "Mari yawakanyora haienderani nerisiti.",
        "nd": "Imali oyibhalileyo ayivumelani lerisithi.",
    },
    "TYPED_REFERENCE_DISAGREES": {
        "en": "The reference you typed does not match the receipt.",
        "sn": "Nhamba yawakanyora haienderani nerisiti.",
        "nd": "Inombolo oyibhalileyo ayivumelani lerisithi.",
    },
    "UNREADABLE": {
        "en": "We could not read the payment details. Please upload a clearer copy.",
        "sn": "Hatina kukwanisa kuverenga mashoko ekubhadhara. Tumira kopi yakajeka.",
        "nd": "Asikwazanga ukufunda imininingwane yokukhokha. Sicela uthumele ikhophi ecacileyo.",
    },
    "WRONG_BENEFICIARY": {
        "en": "The payment does not appear to have been sent to our account.",
        "sn": "Kubhadhara hakuna kuratidzika kuti kwakaendeswa kuakaundi yedu.",
        "nd": "Ukukhokha akubonakali kuthunyelwe ku-akhawunti yethu.",
    },
    "PAYEE_MISMATCH": {
        "en": "The recipient on your receipt does not match our account. Please check that you "
        "paid the right account.",
        "sn": "Munhu anogamuchira parisiti yako haaenderani neakaundi yedu. Tarisa kuti "
        "wakabhadhara kuakaundi chaiyo.",
        "nd": "Ogunyaziweyo kurisithi yakho akavumelani le-akhawunti yethu. Sicela uhlole ukuthi "
        "ukhokhele ku-akhawunti efanele.",
    },
    # outcomes sent to a payer when a claim's state changes
    "payer.approved": {
        "en": "Thank you. Your payment has been confirmed.",
        "sn": "Tatenda. Kubhadhara kwako kwasimbiswa.",
        "nd": "Siyabonga. Ukukhokha kwakho kuqinisekisiwe.",
    },
    "payer.rejected": {
        "en": "We could not confirm your payment. Please contact our finance team.",
        "sn": "Hatina kukwanisa kusimbisa kubhadhara kwako. Bata chikwata chedu chemari.",
        "nd": "Asikwazanga ukuqinisekisa ukukhokha kwakho. Sicela uxhumane leqembu lethu lezimali.",
    },
    "payer.needs_info": {
        "en": "We need a little more information about your payment. Please send a clearer copy "
        "of your proof of payment.",
        "sn": "Tinoda mashoko mamwe nezve kubhadhara kwako. Tumira kopi yakajeka yehumbowo hwako.",
        "nd": "Sidinga imininingwane eyengeziweyo ngokukhokha kwakho. Sicela uthumele ikhophi "
        "ecacileyo yobufakazi bakho.",
    },
    "payer.provisional": {
        "en": "Access is open until {until} UTC while we confirm your payment.",
        "sn": "Mvumo yakavhurika kusvika {until} UTC tichiri kusimbisa kubhadhara kwako.",
        "nd": "Imvume ivuliwe kuze kube ngu-{until} UTC siqinisekisa ukukhokha kwakho.",
    },
    # WhatsApp replies
    "wa.send_proof": {
        "en": "Thanks. Now send the proof of payment for {code}.",
        "sn": "Tatenda. Zvino tumira humbowo hwekubhadhara (kodhi {code}).",
        "nd": "Siyabonga. Manje thumela ubufakazi bokukhokha (ikhodi {code}).",
    },
    "wa.need_code": {
        "en": "Please send your proof of payment with your payment code (for example "
        "CG-H4CC093) in the caption. You will find the code on your invoice.",
        "sn": "Tumira humbowo hwekubhadhara kwako nekodhi yekubhadhara (semuenzaniso CG-H4CC093) "
        "pamusoro pefoto (caption). Uchawana kodhi iyi paindivhoyisi yako.",
        "nd": "Sicela uthumele ubufakazi bokukhokha lekhodi yokukhokha (isibonelo CG-H4CC093) "
        "embhalweni ongaphansi kwesithombe. Ikhodi uzayithola kuhinvoyisi yakho.",
    },
    "wa.need_proof": {
        "en": "Please send a screenshot, PDF or the payment SMS as your proof.",
        "sn": "Tumira skrini, PDF kana SMS yekubhadhara sehumbowo.",
        "nd": "Sicela uthumele i-screenshot, i-PDF kumbe i-SMS yokukhokha njengobufakazi.",
    },
    "wa.too_fast": {
        "en": "You are sending too fast. Please wait a minute and try again.",
        "sn": "Uri kutumira nekukurumidza. Mirira miniti woedza zvakare.",
        "nd": "Uthumela ngokuphangisa. Sicela ulinde umzuzu bese uzama futhi.",
    },
    "wa.file_refused": {
        "en": "We could not accept that file: {reason}",
        "sn": "Hatina kukwanisa kugamuchira faira iyo: {reason}",
        "nd": "Asikwazanga ukwamukela ifayili leyo: {reason}",
    },
    "wa.received": {
        "en": "Received your proof of payment for {code}. We will confirm it once the money "
        "reaches our account.",
        "sn": "Tagamuchira humbowo hwekubhadhara (kodhi {code}). Tichahusimbisa mari kana "
        "yasvika muakaundi yedu.",
        "nd": "Sikwamukele ubufakazi bokukhokha (ikhodi {code}). Sizabuqinisekisa lapho imali "
        "isifike ku-akhawunti yethu.",
    },
    "wa.lang_set": {
        "en": "Language set to English.",
        "sn": "Mutauro washandurwa kuita Shona.",
        "nd": "Ulimi lushintshelwe kuNdebele.",
    },
}

# Always English on purpose: said when someone asks for a language that is not switched on yet.
NOT_LIVE = "{name} replies are not switched on yet, so we will keep using English."


def language_live(lang: str) -> bool:
    """May whole outbound messages be sent in this language?"""
    s = get_settings()
    return lang == "en" or lang in s.payer_message_languages_live or s.allow_draft_payer_messages


def usable_language(lang: str | None, key: str = "") -> str:
    """The language a message will really be sent in: English unless it is live or signed off."""
    if lang and lang != "en" and lang in LANGS and (language_live(lang) or key in REVIEWED[lang]):
        return lang
    return "en"


def render(key: str, lang: str | None = "en", **params: Any) -> str:
    entry = TEXTS[key]
    text = entry[usable_language(lang, key)]
    return text.format(**params) if params else text


def message_key(code: str) -> str:
    return PAYER_MESSAGE_KEY.get(code, code)


def explain(reasons: list[str], lang: str | None = "en") -> list[str]:
    """The payer-safe sentence for each reason that has one, in the payer's language."""
    return [render(message_key(r), lang) for r in reasons if r in _REASON_CODES]


def explain_keys(reasons: list[str]) -> list[str]:
    """One neutral key per sentence `explain` returns, in the same order."""
    return [message_key(r) for r in reasons if r in _REASON_CODES]


# English text per internal reason code, for the code that still reads REASON_TEXT[...]
REASON_TEXT: dict[str, str] = {c: TEXTS[message_key(c)]["en"] for c in _REASON_CODES}
