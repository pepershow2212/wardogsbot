from deep_translator import GoogleTranslator

# названия игр/термины которые нельзя переводить
GLOSSARY = [
    "WARDOGS",
    "HELLDIVERS",
    "Call of Duty",
    "Modern Warfare",
    "Mortal Shell",
    "S.T.A.L.K.E.R.",
    "Black Myth: Wukong",
    "No More Room in Hell",
    "Hell Let Loose",
    "Big Walk",
    "STAR WARS Zero Company",
    "SteamDB",
    "PCGamesN",
    "Team17",
    "Bulkhead",
]


def translate_to_russian(text: str) -> str:
    if not text.strip():
        return text
    try:
        # защита терминов от перевода через плейсхолдеры
        placeholders = {}
        protected = text
        for i, term in enumerate(GLOSSARY):
            if term.lower() in protected.lower():
                ph = f"__TERM{i}__"
                placeholders[ph] = term
                protected = protected.replace(term, ph)

        translated = GoogleTranslator(source="en", target="ru").translate(protected)
        if not translated:
            return text
        for ph, term in placeholders.items():
            translated = translated.replace(ph, term)
            translated = translated.replace(ph.lower(), term)
            translated = translated.replace(ph.upper(), term)
        return translated
    except Exception:
        return text
