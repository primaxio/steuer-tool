"""
Steuerjahr-Konfiguration
========================
Alle jahresabhängigen Pausch- und Freibeträge an einer Stelle.
Für ein neues Steuerjahr: Block kopieren, Jahr ändern, Werte anhand
BMF-Veröffentlichungen aktualisieren (jährlich prüfen!).

Alle Beträge in EUR.
"""

TAX_YEARS = {
    2024: {
        "grundfreibetrag": 11784,  # rückwirkend angehoben (Ges. z. steuerl. Freistellung d. Existenzminimums)
        "arbeitnehmer_pauschbetrag": 1230,        # Werbungskostenpauschale Anlage N
        "sparer_pauschbetrag": 1000,              # pro Person (Ehegatten: 2000)
        "sonderausgaben_pauschbetrag": 36,
        "entfernungspauschale_bis_20km": 0.30,    # EUR je Entfernungs-km
        "entfernungspauschale_ab_21km": 0.38,
        "homeoffice_pauschale_pro_tag": 6.00,
        "homeoffice_max": 1260,
        "freigrenze_private_veraeusserung": 1000, # § 23 EStG (Krypto etc.), ab 2024
        "handwerker_max_ermaessigung": 1200,      # § 35a: 20% der Arbeitskosten, max.
        "haushaltsnahe_max_ermaessigung": 4000,   # § 35a: 20%, max.
        "verpflegung_teiltag": 14.00,             # Verpflegungsmehraufwand > 8h
        "verpflegung_volltag": 28.00,
        "gwg_grenze_brutto": 952,                 # Arbeitsmittel Sofortabzug (800 netto)
        "freigrenze_sonstige_leistungen": 256,    # § 22 Nr. 3 (Staking/Rewards)
        "kinderbetreuung": {"anteil_prozent": 67, "max": 4000},  # 2/3, § 10 (1) 5
        "abgabefrist_hinweis": "31.07.2025 (ohne Berater; mit Berater 30.04.2026)",
        "abgabefrist_datum": "2025-07-31",
        "soli_freigrenze_einzel": 18130, "soli_freigrenze_zusammen": 36260,
        # § 32a EStG Tarifformel 2024 (für Schätzungen; jährlich prüfen!)
        "tarif": {"gfb": 11784, "z2_ende": 17005, "z3_ende": 66760,
                  "z4_ende": 277825, "z2": (954.80, 1400),
                  "z3": (181.19, 2397, 991.21),
                  "z4": (0.42, 10636.31), "z5": (0.45, 18971.06)},
    },
    2025: {
        "grundfreibetrag": 12096,
        "arbeitnehmer_pauschbetrag": 1230,
        "sparer_pauschbetrag": 1000,
        "sonderausgaben_pauschbetrag": 36,
        "entfernungspauschale_bis_20km": 0.30,
        "entfernungspauschale_ab_21km": 0.38,
        "homeoffice_pauschale_pro_tag": 6.00,
        "homeoffice_max": 1260,
        "freigrenze_private_veraeusserung": 1000,
        "handwerker_max_ermaessigung": 1200,
        "haushaltsnahe_max_ermaessigung": 4000,
        "verpflegung_teiltag": 14.00,
        "verpflegung_volltag": 28.00,
        "gwg_grenze_brutto": 952,
        "freigrenze_sonstige_leistungen": 256,    # § 22 Nr. 3 (Staking/Rewards)
        "kinderbetreuung": {"anteil_prozent": 80, "max": 4800},  # ab 2025 erhöht
        "abgabefrist_hinweis": "31.07.2026 (ohne Berater; mit Berater 30.04.2027)",
        "abgabefrist_datum": "2026-07-31",
        "soli_freigrenze_einzel": 19950, "soli_freigrenze_zusammen": 39900,
        # § 32a EStG Tarifformel 2025 (für Schätzungen; jährlich prüfen!)
        "tarif": {"gfb": 12096, "z2_ende": 17443, "z3_ende": 68480,
                  "z4_ende": 277825, "z2": (932.30, 1400),
                  "z3": (176.64, 2397, 1015.13),
                  "z4": (0.42, 10911.92), "z5": (0.45, 19246.67)},
    },
}

DEFAULT_YEAR = 2025

# Modell für die Dokumentenerkennung (Anthropic API)
VISION_MODEL = "claude-sonnet-4-6"


def get_config(year: int) -> dict:
    """Konfiguration für ein Jahr holen. Fällt auf das nächstliegende Jahr
    zurück und markiert die Werte dann als ungeprüft."""
    if year in TAX_YEARS:
        cfg = dict(TAX_YEARS[year])
        cfg["_geprueft"] = True
    else:
        naechstes = min(TAX_YEARS.keys(), key=lambda y: abs(y - year))
        cfg = dict(TAX_YEARS[naechstes])
        cfg["_geprueft"] = False
        cfg["_basisjahr"] = naechstes
    cfg["jahr"] = year
    return cfg
