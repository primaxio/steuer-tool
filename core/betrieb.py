"""
Betriebsmodul: Einnahmen-Überschuss-Rechnung (EÜR) für kleine Betriebe/
Nebengewerbe (z. B. Photovoltaik-/Fernwärme-Verkauf, freiberufliche
Tätigkeit, Vermietung). Ergänzt die bestehenden Anlagen N/KAP/SO um
Anlage G (Gewerbebetrieb) bzw. Anlage S (Selbständige Arbeit).

Steuerliche Eckpunkte (siehe hinweise_fuer_betrieb):
- § 3 Nr. 72 EStG: Photovoltaikanlagen bis 30 kWp (Einfamilienhaus/
  vergleichbar) sind seit 2022 einkommensteuerfrei – gilt NUR für
  verkauften STROM, NICHT für Wärme (Fernwärme/BHKW bleibt gewerblich!).
- § 19 UStG Kleinunternehmer: keine Umsatzsteuer auf Rechnungen, aber
  Umsatzgrenzen (Vorjahr/laufendes Jahr, aus tax_config.py) beachten.
- § 11 Abs. 1 GewStG: Gewerbesteuer-Freibetrag 24.500 € für natürliche
  Personen/Personengesellschaften (NICHT bei Freiberuflern – die zahlen
  ohnehin keine Gewerbesteuer, § 18 EStG).
- § 11 EStG: Zu-/Abflussprinzip – Zahlungszeitpunkt zählt für die EÜR,
  nicht das Rechnungsdatum.
"""

from dataclasses import dataclass, field
from datetime import date

ARTEN = {
    "gewerblich": "Gewerbebetrieb (§ 15 EStG, Anlage G)",
    "freiberuflich": "Freiberufliche Tätigkeit (§ 18 EStG, Anlage S)",
    "photovoltaik": "Photovoltaikanlage (Stromverkauf)",
    "vermietung": "Vermietung (Anlage V, Einnahmen-Überschuss)",
}

def _e(v: float) -> str:
    return f"{v:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def _jahr_von(iso_datum: str) -> int | None:
    try:
        return date.fromisoformat(iso_datum).year
    except (ValueError, TypeError):
        return None


@dataclass
class Position:
    """Einnahme oder Ausgabe (§ 11 EStG: Zu-/Abflussprinzip zählt)."""
    datum: str            # ISO "YYYY-MM-DD" – Zahlungsdatum, nicht Rechnungsdatum!
    bezeichnung: str
    betrag: float          # immer positiv
    kategorie: str = "sonstiges"
    quelle: str = ""        # Dateiname des Belegs (leer = manuell erfasst)


@dataclass
class AfaPosition:
    """Abnutzbares Anlagegut, lineare AfA (§ 7 Abs. 1 EStG), zeitanteilig
    (volle Monate) im Anschaffungsjahr."""
    bezeichnung: str
    anschaffungskosten: float
    anschaffungsdatum: str        # ISO "YYYY-MM-DD"
    nutzungsdauer_jahre: int
    quelle: str = ""

    def afa_fuer_jahr(self, jahr: int) -> float:
        if self.nutzungsdauer_jahre <= 0 or self.anschaffungskosten <= 0:
            return 0.0
        try:
            d = date.fromisoformat(self.anschaffungsdatum)
        except (ValueError, TypeError):
            return 0.0
        gesamt_monate = self.nutzungsdauer_jahre * 12
        monatliche_afa = self.anschaffungskosten / gesamt_monate
        monate_im_jahr = sum(
            1 for offset in range(gesamt_monate)
            if d.year + (d.month - 1 + offset) // 12 == jahr)
        return round(monatliche_afa * monate_im_jahr, 2)

    @property
    def restwert(self) -> float:
        """Buchwert am Ende der Nutzungsdauer (Rundungsreste), informativ."""
        jahre = range(date.fromisoformat(self.anschaffungsdatum).year,
                      date.fromisoformat(self.anschaffungsdatum).year
                      + self.nutzungsdauer_jahre + 1)
        abgeschrieben = sum(self.afa_fuer_jahr(j) for j in jahre)
        return round(self.anschaffungskosten - abgeschrieben, 2)


@dataclass
class Betrieb:
    name: str
    art: str = "gewerblich"                # Key aus ARTEN
    inhaber: str = "P1"                    # P1 | P2
    kleinunternehmer_19ustg: bool = True
    gruendung: str = ""                     # ISO-Datum, optional
    gewinnermittlung: str = "EÜR"
    einnahmen: list = field(default_factory=list)       # list[Position]
    ausgaben: list = field(default_factory=list)        # list[Position]
    afa_positionen: list = field(default_factory=list)  # list[AfaPosition]


def _hinweise_fuer_betrieb(betrieb: Betrieb, jahr: int, cfg: dict,
                          gewinn: float, umsatz_jahr: float,
                          umsatz_vorjahr: float) -> list[str]:
    hinweise = [
        "EÜR-Grundprinzip (§ 11 EStG, Zu-/Abflussprinzip): Zählt ist das "
        "ZAHLUNGSDATUM, nicht das Rechnungsdatum – eine im Januar bezahlte "
        "Rechnung von Dezember gehört ins neue Jahr."
    ]

    if betrieb.art == "photovoltaik":
        hinweise.append(
            "§ 3 Nr. 72 EStG: Photovoltaikanlagen bis 30 kWp (Einfamilien-"
            "haus/vergleichbar, bzw. bis 15 kWp je Wohn-/Gewerbeeinheit bei "
            "Mehrfamilienhäusern) sind seit 2022 EINKOMMENSTEUERFREI – dann "
            "KEINE Anlage G/EÜR nötig (nur formlose Anzeige beim "
            "Finanzamt). Prüfe die kWp-Leistung deiner Anlage! ⚠️ Diese "
            "Befreiung gilt NUR für verkauften STROM, NICHT für verkaufte "
            "WÄRME (Fernwärme/BHKW) – Wärmeverkauf bleibt in jedem Fall "
            "gewerblich (Anlage G + EÜR)!")
    if betrieb.art != "photovoltaik" and any(
            w in (betrieb.name or "").lower()
            for w in ("wärme", "waerme", "fernwärme", "fernwaerme", "bhkw")):
        hinweise.append(
            "⚠️ Wärme-/Fernwärmeverkauf erkannt: Die PV-Steuerbefreiung "
            "(§ 3 Nr. 72 EStG) gilt NUR für verkauften Strom, NICHT für "
            "Wärme – auch nicht, wenn die Wärme aus einer PV-gekoppelten "
            "Anlage (z. B. Wärmepumpe, BHKW) stammt. Der Wärmeverkauf ist "
            "ein eigener, voll steuerpflichtiger Gewerbebetrieb (§ 15 EStG, "
            "Anlage G + EÜR) – unabhängig von einem eventuell steuerfreien "
            "Stromanteil.")

    if betrieb.art == "vermietung":
        hinweise.append(
            "Vermietungseinkünfte gehören steuerlich in die Anlage V "
            "(§ 21 EStG), nicht in Anlage G/EÜR – dieses Tool rechnet sie "
            "strukturell gleich (Einnahmen − Werbungskosten − AfA), damit "
            "du eine Schätzung hast. Keine Gewerbesteuer, i. d. R. auch "
            "keine Umsatzsteuer (§ 4 Nr. 12 UStG bei Wohnraumvermietung).")
        hinweise.append(
            "Gebäude-AfA (§ 7 Abs. 4 EStG) folgt EIGENEN festen Sätzen "
            "nach Fertigstellungsjahr – NICHT frei wählbar wie bei "
            "sonstigen Anlagegütern: 2 % p. a. (50 Jahre ND) bei "
            "Fertigstellung nach 1924, 2,5 % (40 Jahre) bei Fertigstellung "
            "vor 1925, 3 % (rund 33 Jahre) bei Neubauten mit "
            "Fertigstellung ab 2023 (Wachstumschancengesetz). Nur der "
            "Gebäudeanteil ist abschreibbar, NICHT der Grund-und-Boden-"
            "Anteil (i. d. R. per Kaufpreisaufteilung/Bodenrichtwert "
            "ermitteln) – bei der AfA-Position entsprechend die "
            "Nutzungsdauer manuell auf 50/40/33 Jahre setzen.")
    elif betrieb.kleinunternehmer_19ustg:
        hinweise.append(
            "§ 19 UStG Kleinunternehmer: keine Umsatzsteuer auf Rechnungen "
            "– Pflichthinweis 'Kein Ausweis von Umsatzsteuer gem. § 19 "
            "UStG' auf jeder Rechnung.")
        grenze_vj = cfg.get("kleinunternehmer_grenze_vorjahr", 25_000.0)
        grenze_lfd = cfg.get("kleinunternehmer_grenze_laufend", 100_000.0)
        ist_gruendungsjahr = _jahr_von(betrieb.gruendung) == jahr
        if not ist_gruendungsjahr and umsatz_vorjahr > grenze_vj:
            hinweise.append(
                f"⚠️ Vorjahresumsatz ({_e(umsatz_vorjahr)}) liegt über der "
                f"Kleinunternehmer-Grenze ({_e(grenze_vj)}) – ab diesem "
                "Jahr regelbesteuert (Umsatzsteuer ausweisen und abführen)! "
                "Bitte mit einem Steuerberater klären.")
        elif umsatz_jahr > grenze_lfd:
            hinweise.append(
                f"⚠️ Laufender Umsatz ({_e(umsatz_jahr)}) hat die "
                f"Kleinunternehmer-Grenze für das Jahr ({_e(grenze_lfd)}) "
                "bereits überschritten – seit 2025 gilt der Wechsel zur "
                "Regelbesteuerung UNTERJÄHRIG ab dem übersteigenden Umsatz "
                "(kein Bestandsschutz bis Jahresende mehr)!")

    if betrieb.art == "gewerblich":
        gewst_freibetrag = cfg.get("gewerbesteuer_freibetrag", 24_500.0)
        if gewinn <= gewst_freibetrag:
            hinweise.append(
                f"Gewerbesteuer: Gewinn ({_e(gewinn)}) liegt unter dem "
                f"Freibetrag von {_e(gewst_freibetrag)} – keine "
                "Gewerbesteuer fällig (Gewerbesteuererklärung ist trotzdem "
                "oft einzureichen, das Finanzamt prüft automatisch).")
        else:
            hinweise.append(
                f"Gewerbesteuer: Gewinn ({_e(gewinn)}) übersteigt den "
                f"Freibetrag ({_e(gewst_freibetrag)}) um "
                f"{_e(gewinn - gewst_freibetrag)} – darauf fällt "
                "Gewerbesteuer an. Bei Einzelunternehmen/Personengesell-"
                "schaften wird sie über § 35 EStG weitgehend auf die "
                "Einkommensteuer angerechnet. Gewerbesteuererklärung "
                "separat bei der Gemeinde/dem Finanzamt einreichen.")
    elif betrieb.art == "freiberuflich":
        hinweise.append(
            "Freiberufliche Tätigkeit (§ 18 EStG): KEINE Gewerbesteuer, "
            "keine Gewerbeanmeldung nötig – Gewinn gehört in Anlage S "
            "statt Anlage G.")

    if not betrieb.einnahmen and not betrieb.ausgaben:
        hinweise.append(
            f"Betrieb '{betrieb.name}' wurde angelegt, hat aber noch keine "
            "erfassten Einnahmen/Ausgaben für dieses Jahr – Belege "
            "hochladen oder manuell eintragen.")

    return hinweise


def berechne_euer(betrieb: Betrieb, jahr: int, cfg: dict) -> dict:
    """Einnahmen-Überschuss-Rechnung für einen Betrieb und ein Steuerjahr."""
    einnahmen_jahr = [p for p in betrieb.einnahmen if _jahr_von(p.datum) == jahr]
    ausgaben_jahr = [p for p in betrieb.ausgaben if _jahr_von(p.datum) == jahr]
    umsatz_jahr = round(sum(p.betrag for p in einnahmen_jahr), 2)
    umsatz_vorjahr = round(sum(
        p.betrag for p in betrieb.einnahmen if _jahr_von(p.datum) == jahr - 1), 2)
    summe_ausgaben = round(sum(p.betrag for p in ausgaben_jahr), 2)
    afa_jahr = round(sum(a.afa_fuer_jahr(jahr) for a in betrieb.afa_positionen), 2)
    gewinn = round(umsatz_jahr - summe_ausgaben - afa_jahr, 2)

    return {
        "betrieb": betrieb.name, "art": betrieb.art, "inhaber": betrieb.inhaber,
        "jahr": jahr,
        "einnahmen": umsatz_jahr, "ausgaben": summe_ausgaben, "afa": afa_jahr,
        "gewinn": gewinn,
        "einnahmen_positionen": einnahmen_jahr,
        "ausgaben_positionen": ausgaben_jahr,
        "afa_positionen": [
            {"bezeichnung": a.bezeichnung,
             "anschaffungskosten": a.anschaffungskosten,
             "anschaffungsdatum": a.anschaffungsdatum,
             "nutzungsdauer_jahre": a.nutzungsdauer_jahre,
             "afa_jahr": a.afa_fuer_jahr(jahr)}
            for a in betrieb.afa_positionen],
        "hinweise": _hinweise_fuer_betrieb(
            betrieb, jahr, cfg, gewinn, umsatz_jahr, umsatz_vorjahr),
    }


def gewinn_pro_person(betriebe: list, jahr: int, cfg: dict) -> dict:
    """Summierter Betriebsgewinn je Person – Eingang für veranlagung.py."""
    out = {"P1": 0.0, "P2": 0.0}
    for b in betriebe:
        r = berechne_euer(b, jahr, cfg)
        out[b.inhaber] = out.get(b.inhaber, 0.0) + r["gewinn"]
    return {k: round(v, 2) for k, v in out.items()}
