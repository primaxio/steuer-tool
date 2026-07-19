"""
Steuerjahr-Konfiguration
========================
Alle jahresabhängigen Pausch- und Freibeträge an einer Stelle.
Für ein neues Steuerjahr: Block kopieren, Jahr ändern, Werte anhand
BMF-Veröffentlichungen aktualisieren (jährlich prüfen!).

Alle Beträge in EUR.
"""


def _renten_besteuerungsanteil_kohorte(rentenbeginn_jahr: int) -> float:
    """Besteuerungsanteil der gesetzlichen Rente (§ 22 Nr. 1 S. 3 Bst. a
    EStG) nach Kohorte (Jahr des Rentenbeginns) – EIN fixer Prozentsatz
    fürs gesamte Rentnerleben, unabhängig vom aktuellen Steuerjahr.
    Stufen: bis 2005 50 %, 2006–2020 +2 Punkte/Jahr, 2021–2022 +1 Punkt/
    Jahr, ab 2023 +0,5 Punkte/Jahr (rückwirkend durch das Wachstums-
    chancengesetz 2024 verlangsamt) bis 100 % im Jahr 2058."""
    j = rentenbeginn_jahr
    if j <= 2005:
        anteil = 50.0
    elif j <= 2020:
        anteil = 50.0 + 2.0 * (j - 2005)
    elif j <= 2022:
        anteil = 80.0 + 1.0 * (j - 2020)
    else:
        anteil = 82.0 + 0.5 * (j - 2022)
    return round(min(anteil, 100.0), 1)


_RENTEN_BESTEUERUNGSANTEIL = {
    jahr: _renten_besteuerungsanteil_kohorte(jahr) for jahr in range(1990, 2059)
}

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
        "kleinunternehmer_grenze_vorjahr": 22000,   # § 19 UStG, bis 2024
        "kleinunternehmer_grenze_laufend": 50000,
        "gewerbesteuer_freibetrag": 24500,          # § 11 Abs. 1 GewStG
        "vorsorge_hoechstbetrag_arbeitnehmer": 1900,  # § 10 Abs. 4 EStG
        "vorsorge_hoechstbetrag_selbststaendig": 2800,  # ohne AG-Zuschuss
        # § 33 Abs. 3 EStG: Stufengrenzen unverändert seit Jahren (BFH-
        # Dreistufenberechnung VI R 75/14). Sätze nach Familienstand/
        # Kinderzahl je Stufe (bis 15.340 € / 15.340–51.130 € / darüber).
        "zumutbare_belastung_stufen": (15340, 51130),
        "zumutbare_belastung_saetze": {
            "ledig": (0.05, 0.06, 0.07),
            "verheiratet": (0.04, 0.05, 0.06),
            "kinder_1_2": (0.02, 0.03, 0.04),
            "kinder_3plus": (0.01, 0.01, 0.02),
        },
        # § 33b Abs. 3 EStG: Behinderten-Pauschbeträge je Grad der
        # Behinderung, unverändert seit der Reform ab VZ 2021.
        "behinderten_pauschbetrag": {
            20: 384, 30: 620, 40: 860, 50: 1140, 60: 1440,
            70: 1780, 80: 2120, 90: 2460, 100: 2840,
        },
        "behinderten_pauschbetrag_hilflos_blind": 7400,  # Merkzeichen H/Bl/TBl
        # § 33b Abs. 6 EStG: Pflege-Pauschbetrag nach Pflegegrad der
        # gepflegten Person (unentgeltliche häusliche Pflege).
        "pflege_pauschbetrag": {2: 600, 3: 1100, 4: 1800, 5: 1800},
        # § 33a Abs. 1 EStG: Höchstbetrag = Grundfreibetrag des Jahres
        # (gesetzlich gekoppelt, siehe cfg["grundfreibetrag"]); eigene
        # Einkünfte/Bezüge der unterstützten Person bleiben bis zu diesem
        # anrechnungsfreien Betrag unschädlich (seit Jahren unverändert).
        "unterhalt_anrechnungsfreier_betrag": 624,
        # § 10a EStG Riester: Höchstbeitrag, Grund-/Kinderzulage unverändert
        # seit Jahren.
        "riester_max_beitrag": 2100,
        "riester_grundzulage": 175,
        "riester_kinderzulage_ab_2008": 300,
        "riester_kinderzulage_vor_2008": 185,
        "riester_mindesteigenbeitrag_prozent": 0.04,
        "riester_sockelbetrag": 60,
        # § 22 Nr. 1 Satz 3 EStG: Besteuerungsanteil der gesetzlichen Rente
        # nach Jahr des Rentenbeginns (Kohortentabelle, seit Jahren fix je
        # Kohorte – neue Rentner rutschen jedes Jahr in eine neue Zeile).
        "renten_besteuerungsanteil": _RENTEN_BESTEUERUNGSANTEIL,
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
        "abgabefrist_hinweis": "31.07.2026 (ohne Berater; mit Berater 01.03.2027 – "
                               "dauerhafte Fristverkürzung auf Ende Februar ab VZ 2025)",
        "abgabefrist_datum": "2026-07-31",
        "soli_freigrenze_einzel": 19950, "soli_freigrenze_zusammen": 39900,
        "kleinunternehmer_grenze_vorjahr": 25000,   # § 19 UStG, ab 2025 (JStG 2024)
        "kleinunternehmer_grenze_laufend": 100000,
        "gewerbesteuer_freibetrag": 24500,          # § 11 Abs. 1 GewStG
        "vorsorge_hoechstbetrag_arbeitnehmer": 1900,  # § 10 Abs. 4 EStG
        "vorsorge_hoechstbetrag_selbststaendig": 2800,  # ohne AG-Zuschuss
        "zumutbare_belastung_stufen": (15340, 51130),
        "zumutbare_belastung_saetze": {
            "ledig": (0.05, 0.06, 0.07),
            "verheiratet": (0.04, 0.05, 0.06),
            "kinder_1_2": (0.02, 0.03, 0.04),
            "kinder_3plus": (0.01, 0.01, 0.02),
        },
        "behinderten_pauschbetrag": {
            20: 384, 30: 620, 40: 860, 50: 1140, 60: 1440,
            70: 1780, 80: 2120, 90: 2460, 100: 2840,
        },
        "behinderten_pauschbetrag_hilflos_blind": 7400,
        "pflege_pauschbetrag": {2: 600, 3: 1100, 4: 1800, 5: 1800},
        "unterhalt_anrechnungsfreier_betrag": 624,
        "riester_max_beitrag": 2100,
        "riester_grundzulage": 175,
        "riester_kinderzulage_ab_2008": 300,
        "riester_kinderzulage_vor_2008": 185,
        "riester_mindesteigenbeitrag_prozent": 0.04,
        "riester_sockelbetrag": 60,
        "renten_besteuerungsanteil": _RENTEN_BESTEUERUNGSANTEIL,
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
