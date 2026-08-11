"""
Validation des numéros de téléphone par pays (indicatif E.164).

Mìroit du dictionnaire `NATIONAL_LENGTH` du sélecteur côté frontend :
nombre de chiffres (hors indicatif) attendu pour chaque pays ISO2.
"""

from app.models.country import Country

# (min, max) — nombre de chiffres du numéro national SANS l'indicatif.
NATIONAL_DIGITS: dict[str, tuple[int, int]] = {
    "TG": (8, 8),
    "BJ": (8, 8),
    "GH": (8, 9),
    "CI": (8, 10),
    "NG": (7, 10),
    "SN": (9, 9),
    "BF": (8, 8),
    "CM": (9, 9),
    "ML": (8, 8),
    "NE": (8, 8),
    "GN": (8, 8),
    "MR": (8, 8),
    "SL": (8, 8),
    "LR": (7, 8),
    "GM": (7, 7),
    "CV": (7, 7),
    "GA": (8, 8),
    "CG": (9, 9),
    "CD": (9, 9),
    "AO": (9, 9),
    "MZ": (9, 9),
    "MG": (9, 9),
    "MW": (7, 9),
    "ZM": (9, 9),
    "ZW": (9, 9),
    "TZ": (9, 9),
    "KE": (9, 9),
    "UG": (9, 9),
    "ET": (9, 9),
    "EG": (8, 9),
    "MA": (9, 9),
    "DZ": (9, 9),
    "TN": (8, 8),
    "LY": (9, 9),
    "TD": (8, 8),
    "CF": (8, 8),
    "DJ": (8, 8),
    "RW": (9, 9),
    "BI": (8, 8),
    "SO": (7, 9),
    "SD": (9, 9),
    "SS": (9, 9),
    "BW": (7, 8),
    "KM": (7, 7),
    "ER": (7, 7),
    "SZ": (7, 7),
    "LS": (8, 8),
    "MU": (8, 8),
    "NA": (9, 9),
    "ST": (7, 7),
    "SC": (7, 7),
    "ZA": (9, 9),
    "FR": (9, 9),
    "BE": (8, 8),
    "CH": (9, 9),
    "LU": (6, 9),
    "DE": (6, 11),
    "IT": (8, 10),
    "ES": (9, 9),
    "PT": (9, 9),
    "NL": (9, 9),
    "GB": (9, 10),
    "US": (10, 10),
    "CA": (10, 10),
    "CN": (8, 11),
    "JP": (9, 10),
    "IN": (10, 10),
    "AE": (9, 9),
    "SA": (9, 9),
    "TR": (10, 10),
    "RU": (10, 10),
    "BR": (10, 11),
    "AR": (8, 10),
    "MX": (10, 10),
    "AU": (9, 9),
}

DEFAULT_NATIONAL_DIGITS: tuple[int, int] = (6, 13)


def national_digits(national: str) -> str:
    """Extrait les chiffres d'un numéro national (ignore espaces, tirets, etc.)."""
    return "".join(ch for ch in national if ch.isdigit())


def is_valid_national_number(country: Country | None, national: str) -> bool:
    """Le nombre de chiffres du numéro national est-il conforme au pays ?"""
    if country is None:
        return False
    digits = national_digits(national)
    if not digits:
        return False
    min_digits, max_digits = NATIONAL_DIGITS.get(country.code, DEFAULT_NATIONAL_DIGITS)
    return min_digits <= len(digits) <= max_digits


def build_e164(country: Country, national: str) -> str:
    """Construit le numéro complet au format E.164 : indicatif + numéro national."""
    return f"{country.phone_code}{national_digits(national)}"
