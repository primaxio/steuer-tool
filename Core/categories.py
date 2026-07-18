"""
Dokument-Kategorien und Zuordnung zu den Anlagen der Einkommensteuererklärung.
Zugeschnitten auf das Profil: Angestellt + Übergangsgebührnisse (Bundeswehr)
+ Kapitalerträge (Aktien) + Krypto.
"""

CATEGORIES = {
    "lohnsteuerbescheinigung_zivil": {
        "label": "Lohnsteuerbescheinigung – ziviler Arbeitgeber",
        "anlage": "Anlage N (Arbeitgeber 1)",
        "beschreibung": "Jährliche Lohnsteuerbescheinigung des zivilen Hauptarbeitgebers.",
    },
    "lohnsteuerbescheinigung_bundeswehr": {
        "label": "Lohnsteuerbescheinigung – Bundeswehr / Übergangsgebührnisse",
        "anlage": "Anlage N (Arbeitgeber 2)",
        "beschreibung": (
            "Bescheinigung des BVA/Bundeswehr-Dienstleistungszentrums über "
            "Übergangsgebührnisse (SaZ). Voll steuerpflichtiger Arbeitslohn, "
            "häufig Steuerklasse VI."
        ),
    },
    "uebergangsbeihilfe": {
        "label": "Übergangsbeihilfe (Einmalzahlung Bundeswehr)",
        "anlage": "Anlage N (ermäßigt zu besteuernder Arbeitslohn)",
        "beschreibung": (
            "Einmalige Übergangsbeihilfe. Ggf. Fünftelregelung (§ 34 EStG) "
            "als Vergütung für mehrjährige Tätigkeit prüfen."
        ),
    },
    "steuerbescheinigung_bank": {
        "label": "Steuerbescheinigung Bank/Broker (Aktien, Dividenden)",
        "anlage": "Anlage KAP",
        "beschreibung": (
            "Jahressteuerbescheinigung: Kapitalerträge, einbehaltene "
            "Kapitalertragsteuer, Soli, Kirchensteuer, Freistellungsauftrag, "
            "Verlusttöpfe."
        ),
    },
    "krypto_report": {
        "label": "Krypto-Steuerreport (z. B. Blockpit, CoinTracking)",
        "anlage": "Anlage SO (private Veräußerungsgeschäfte, § 23 EStG)",
        "beschreibung": (
            "Gewinne/Verluste aus Kryptoverkäufen. Haltefrist > 1 Jahr = "
            "steuerfrei; Freigrenze beachten."
        ),
    },
    "werbungskosten": {
        "label": "Werbungskosten-Beleg (Arbeitsmittel, Fortbildung, Fachliteratur …)",
        "anlage": "Anlage N – Werbungskosten",
        "beschreibung": "Rechnungen/Quittungen für beruflich veranlasste Ausgaben.",
    },
    "vorsorge_versicherung": {
        "label": "Versicherung / Vorsorgeaufwand",
        "anlage": "Anlage Vorsorgeaufwand",
        "beschreibung": (
            "Kranken-/Pflegeversicherung, Haftpflicht, Unfall-, "
            "Berufsunfähigkeits-, Riester-/Rürup-Beiträge."
        ),
    },
    "spende": {
        "label": "Spendenquittung / Mitgliedsbeitrag",
        "anlage": "Anlage Sonderausgaben",
        "beschreibung": "Zuwendungsbestätigungen gemeinnütziger Organisationen.",
    },
    "handwerker_haushaltsnah": {
        "label": "Handwerkerrechnung / haushaltsnahe Dienstleistung (§ 35a)",
        "anlage": "Anlage Haushaltsnahe Aufwendungen",
        "beschreibung": (
            "Nur Arbeits-/Fahrtkosten (nicht Material) zählen; Zahlung muss "
            "per Überweisung erfolgt sein."
        ),
    },
    "krankheitskosten": {
        "label": "Krankheitskosten / außergewöhnliche Belastungen",
        "anlage": "Anlage Außergewöhnliche Belastungen",
        "beschreibung": "Arzt-, Zahnarzt-, Brillen-, Medikamentenrechnungen etc.",
    },
    "sonstiges": {
        "label": "Sonstiges / Unklar",
        "anlage": "— manuell zuordnen —",
        "beschreibung": "Konnte nicht sicher zugeordnet werden.",
    },
}


def category_options():
    return list(CATEGORIES.keys())


def label_of(key: str) -> str:
    return CATEGORIES.get(key, CATEGORIES["sonstiges"])["label"]


def anlage_of(key: str) -> str:
    return CATEGORIES.get(key, CATEGORIES["sonstiges"])["anlage"]
