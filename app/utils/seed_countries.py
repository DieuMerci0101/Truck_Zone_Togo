"""
Données initiales des pays et indicatifs téléphoniques internationaux.

Liste axée sur l'Afrique de l'Ouest (marché principal de Togo Truck Connect)
complétée par les principaux pays internationaux. Le format de `phone_code`
est l'indicatif E.164 (ex: "+228").
"""

import uuid

# (code ISO2, nom, indicatif E.164, drapeau emoji)
COUNTRIES = [
    # ── Afrique de l'Ouest (marché principal) ──
    ("TG", "Togo", "+228", "🇹🇬"),
    ("BJ", "Bénin", "+229", "🇧🇯"),
    ("GH", "Ghana", "+233", "🇬🇭"),
    ("CI", "Côte d'Ivoire", "+225", "🇨🇮"),
    ("NG", "Nigeria", "+234", "🇳🇬"),
    ("SN", "Sénégal", "+221", "🇸🇳"),
    ("BF", "Burkina Faso", "+226", "🇧🇫"),
    ("CM", "Cameroun", "+237", "🇨🇲"),
    ("ML", "Mali", "+223", "🇲🇱"),
    ("NE", "Niger", "+227", "🇳🇪"),
    ("MR", "Mauritanie", "+222", "🇲🇷"),
    ("GN", "Guinée", "+224", "🇬🇳"),
    ("GW", "Guinée-Bissau", "+245", "🇬🇼"),
    ("SL", "Sierra Leone", "+232", "🇸🇱"),
    ("LR", "Liberia", "+231", "🇱🇷"),
    ("GM", "Gambie", "+220", "🇬🇲"),
    ("CV", "Cap-Vert", "+238", "🇨🇻"),
    ("ST", "Sao Tomé-et-Principe", "+239", "🇸🇹"),
    ("GA", "Gabon", "+241", "🇬🇦"),
    ("GQ", "Guinée équatoriale", "+240", "🇬🇶"),
    ("CG", "Congo", "+242", "🇨🇬"),
    ("CD", "RD Congo", "+243", "🇨🇩"),
    ("AO", "Angola", "+244", "🇦🇴"),
    ("MZ", "Mozambique", "+258", "🇲🇿"),
    ("MG", "Madagascar", "+261", "🇲🇬"),
    ("MW", "Malawi", "+265", "🇲🇼"),
    ("ZM", "Zambie", "+260", "🇿🇲"),
    ("ZW", "Zimbabwe", "+263", "🇿🇼"),
    ("TZ", "Tanzanie", "+255", "🇹🇿"),
    ("KE", "Kenya", "+254", "🇰🇪"),
    ("UG", "Ouganda", "+256", "🇺🇬"),
    ("ET", "Éthiopie", "+251", "🇪🇹"),
    ("EG", "Égypte", "+20", "🇪🇬"),
    ("MA", "Maroc", "+212", "🇲🇦"),
    ("DZ", "Algérie", "+213", "🇩🇿"),
    ("TN", "Tunisie", "+216", "🇹🇳"),
    ("LY", "Libye", "+218", "🇱🇾"),
    ("TD", "Tchad", "+235", "🇹🇩"),
    ("CF", "République centrafricaine", "+236", "🇨🇫"),
    ("DJ", "Djibouti", "+253", "🇩🇯"),
    ("RW", "Rwanda", "+250", "🇷🇼"),
    ("BI", "Burundi", "+257", "🇧🇮"),
    ("SO", "Somalie", "+252", "🇸🇴"),
    ("SD", "Soudan", "+249", "🇸🇩"),
    ("SS", "Soudan du Sud", "+211", "🇸🇸"),
    # ── Principaux pays internationaux ──
    ("FR", "France", "+33", "🇫🇷"),
    ("BE", "Belgique", "+32", "🇧🇪"),
    ("CH", "Suisse", "+41", "🇨🇭"),
    ("LU", "Luxembourg", "+352", "🇱🇺"),
    ("DE", "Allemagne", "+49", "🇩🇪"),
    ("IT", "Italie", "+39", "🇮🇹"),
    ("ES", "Espagne", "+34", "🇪🇸"),
    ("PT", "Portugal", "+351", "🇵🇹"),
    ("NL", "Pays-Bas", "+31", "🇳🇱"),
    ("GB", "Royaume-Uni", "+44", "🇬🇧"),
    ("US", "États-Unis", "+1", "🇺🇸"),
    ("CA", "Canada", "+1", "🇨🇦"),
    ("CN", "Chine", "+86", "🇨🇳"),
    ("JP", "Japon", "+81", "🇯🇵"),
    ("IN", "Inde", "+91", "🇮🇳"),
    ("AE", "Émirats arabes unis", "+971", "🇦🇪"),
    ("SA", "Arabie saoudite", "+966", "🇸🇦"),
    ("TR", "Turquie", "+90", "🇹🇷"),
    ("RU", "Russie", "+7", "🇷🇺"),
    ("BR", "Brésil", "+55", "🇧🇷"),
    ("AR", "Argentine", "+54", "🇦🇷"),
    ("MX", "Mexique", "+52", "🇲🇽"),
    ("AU", "Australie", "+61", "🇦🇺"),
    ("ZA", "Afrique du Sud", "+27", "🇿🇦"),
    ("NG", "Nigeria", "+234", "🇳🇬"),
]


def countries_data() -> list[dict]:
    """Retourne la liste des pays à insérer (dédoublonnée par code ISO)."""
    seen: set[str] = set()
    rows = []
    for code, name, phone_code, flag in COUNTRIES:
        if code in seen:
            continue
        seen.add(code)
        rows.append(
            {
                "id": uuid.uuid4(),
                "name": name,
                "code": code,
                "phone_code": phone_code,
                "flag_emoji": flag,
                "is_active": True,
                "sort_order": len(rows),
            }
        )
    return rows
