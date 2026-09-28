import re


CYRILLIC_TRANSLITERATION = str.maketrans(
    {
        "а": "a",
        "б": "b",
        "в": "v",
        "г": "g",
        "д": "d",
        "е": "e",
        "ё": "e",
        "ж": "zh",
        "з": "z",
        "и": "i",
        "й": "y",
        "к": "k",
        "л": "l",
        "м": "m",
        "н": "n",
        "о": "o",
        "п": "p",
        "р": "r",
        "с": "s",
        "т": "t",
        "у": "u",
        "ф": "f",
        "х": "h",
        "ц": "ts",
        "ч": "ch",
        "ш": "sh",
        "щ": "sch",
        "ъ": "",
        "ы": "y",
        "ь": "",
        "э": "e",
        "ю": "yu",
        "я": "ya",
    }
)


def slugify(value: str) -> str:
    transliterated = value.strip().lower().translate(CYRILLIC_TRANSLITERATION)
    return re.sub(r"[^a-z0-9]+", "-", transliterated).strip("-") or "item"


def create_unique_slug(
    source: str,
    existing: set[str],
    *,
    max_length: int,
) -> str:
    base = slugify(source)[:max_length].rstrip("-") or "item"
    if base not in existing:
        return base

    counter = 2
    while True:
        suffix = f"-{counter}"
        candidate = f"{base[: max_length - len(suffix)].rstrip('-')}{suffix}"
        if candidate not in existing:
            return candidate
        counter += 1
