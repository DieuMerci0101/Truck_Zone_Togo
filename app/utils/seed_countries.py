"""
Données initiales des pays et indicatifs téléphoniques internationaux.

Contient la totalité des 54 pays d'Afrique (marché principal de Togo Truck
Connect) complétés par les principaux pays internationaux. Le format de
`phone_code` est l'indicatif E.164 (ex: "+228").
"""

import uuid

# (code ISO2, nom en français, indicatif E.164, drapeau emoji)
# ── Les 54 pays d'Afrique ──
COUNTRIES = [
    ("DZ", "Algérie", "+213", "🇩🇿"),
    ("AO", "Angola", "+244", "🇦🇴"),
    ("BJ", "Bénin", "+229", "🇧🇯"),
    ("BW", "Botswana", "+267", "🇧🇼"),
    ("BF", "Burkina Faso", "+226", "🇧🇫"),
    ("BI", "Burundi", "+257", "🇧🇮"),
    ("CV", "Cap-Vert", "+238", "🇨🇻"),
    ("CM", "Cameroun", "+237", "🇨🇲"),
    ("CF", "République centrafricaine", "+236", "🇨🇫"),
    ("TD", "Tchad", "+235", "🇹🇩"),
    ("KM", "Comores", "+269", "🇰🇲"),
    ("CG", "Congo", "+242", "🇨🇬"),
    ("CD", "RD Congo", "+243", "🇨🇩"),
    ("CI", "Côte d'Ivoire", "+225", "🇨🇮"),
    ("DJ", "Djibouti", "+253", "🇩🇯"),
    ("EG", "Égypte", "+20", "🇪🇬"),
    ("GQ", "Guinée équatoriale", "+240", "🇬🇶"),
    ("ER", "Érythrée", "+291", "🇪🇷"),
    ("SZ", "Eswatini", "+268", "🇸🇿"),
    ("ET", "Éthiopie", "+251", "🇪🇹"),
    ("GA", "Gabon", "+241", "🇬🇦"),
    ("GM", "Gambie", "+220", "🇬🇲"),
    ("GH", "Ghana", "+233", "🇬🇭"),
    ("GN", "Guinée", "+224", "🇬🇳"),
    ("GW", "Guinée-Bissau", "+245", "🇬🇼"),
    ("KE", "Kenya", "+254", "🇰🇪"),
    ("LS", "Lesotho", "+266", "🇱🇸"),
    ("LR", "Liberia", "+231", "🇱🇷"),
    ("LY", "Libye", "+218", "🇱🇾"),
    ("MG", "Madagascar", "+261", "🇲🇬"),
    ("MW", "Malawi", "+265", "🇲🇼"),
    ("ML", "Mali", "+223", "🇲🇱"),
    ("MR", "Mauritanie", "+222", "🇲🇷"),
    ("MU", "Maurice", "+230", "🇲🇺"),
    ("MA", "Maroc", "+212", "🇲🇦"),
    ("MZ", "Mozambique", "+258", "🇲🇿"),
    ("NA", "Namibie", "+264", "🇳🇦"),
    ("NE", "Niger", "+227", "🇳🇪"),
    ("NG", "Nigeria", "+234", "🇳🇬"),
    ("RW", "Rwanda", "+250", "🇷🇼"),
    ("ST", "Sao Tomé-et-Principe", "+239", "🇸🇹"),
    ("SN", "Sénégal", "+221", "🇸🇳"),
    ("SC", "Seychelles", "+248", "🇸🇨"),
    ("SL", "Sierra Leone", "+232", "🇸🇱"),
    ("SO", "Somalie", "+252", "🇸🇴"),
    ("ZA", "Afrique du Sud", "+27", "🇿🇦"),
    ("SS", "Soudan du Sud", "+211", "🇸🇸"),
    ("SD", "Soudan", "+249", "🇸🇩"),
    ("TZ", "Tanzanie", "+255", "🇹🇿"),
    ("TG", "Togo", "+228", "🇹🇬"),
    ("TN", "Tunisie", "+216", "🇹🇳"),
    ("UG", "Ouganda", "+256", "🇺🇬"),
    ("ZM", "Zambie", "+260", "🇿🇲"),
    ("ZW", "Zimbabwe", "+263", "🇿🇼"),
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
