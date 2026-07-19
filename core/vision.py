"""
Dokumentenerkennung per Claude Vision (Anthropic API).
Klassifiziert jedes Dokument in eine Steuer-Kategorie und extrahiert
die relevanten Werte als strukturiertes JSON.
"""

import base64
import json
import re
from datetime import datetime

import anthropic

from .categories import CATEGORIES
from .tax_config import VISION_MODEL

SUPPORTED_IMAGE_TYPES = {
    "image/jpeg", "image/png", "image/gif", "image/webp",
}

_SYSTEM_PROMPT = """Du bist ein erfahrener deutscher Steuerfachangestellter und analysierst
Belege für eine private Einkommensteuererklärung (Wohnsitz: Bonn, NRW).

Kontext zur Person:
- Zwei Arbeitsverhältnisse: (1) ziviler Arbeitgeber, (2) Übergangsgebührnisse
  der Bundeswehr (ehem. Soldat auf Zeit) – beides Anlage N.
- Kapitalerträge aus Aktien (Anlage KAP) und Kryptowährungen (Anlage SO).

Deine Aufgabe: Ordne das Dokument GENAU EINER Kategorie zu und extrahiere die
steuerlich relevanten Werte. Antworte AUSSCHLIESSLICH mit einem JSON-Objekt,
ohne Markdown, ohne Erklärtext davor oder danach.

Verfügbare Kategorien (Schlüssel exakt so verwenden):
{kategorien}

JSON-Schema:
{{
  "kategorie": "<schlüssel>",
  "confidence": <0.0 bis 1.0>,
  "dokumenttyp": "<kurze Beschreibung, z. B. 'Lohnsteuerbescheinigung 2025'>",
  "aussteller": "<Arbeitgeber/Bank/Firma oder null>",
  "datum": "<TT.MM.JJJJ oder Zeitraum oder null>",
  "steuerjahr": <Jahr als Zahl oder null>,
  "betrag_eur": <Hauptbetrag als Zahl oder null>,
  "extrahierte_daten": {{ ... kategoriespezifische Felder ... }},
  "rueckfragen": ["<Frage an den Nutzer, falls etwas unklar ist>"],
  "hinweise": ["<steuerlicher Hinweis oder erkannter Fehler>"]
}}

Kategoriespezifische Felder für "extrahierte_daten":
- Lohnsteuerbescheinigungen: bruttoarbeitslohn (Zeile 3), lohnsteuer (Z. 4),
  soli (Z. 5), kirchensteuer (Z. 6/7), steuerklasse, zeitraum_von, zeitraum_bis,
  rv_arbeitnehmer (Z. 23a), kv_beitraege (Z. 25), pv_beitraege (Z. 26),
  av_beitraege (Z. 27). Erkenne am Aussteller (BVA, Bundeswehr,
  Dienstleistungszentrum), ob es die Bundeswehr-Bescheinigung ist.
- Übergangsbeihilfe: lohnsteuer, soli, kirchensteuer (falls auf der
  Bescheinigung/Abrechnung einbehalten ausgewiesen, sonst null – NICHT
  raten). Diese Beträge zählen wie normale Lohnsteuervorauszahlung.
- Bank-Steuerbescheinigung: kapitalertraege_zeile7, kapitalertragsteuer, soli,
  kirchensteuer, in_anspruch_genommener_freistellungsauftrag,
  verlust_aktien, verlust_sonstige, auslaendische_quellensteuer.
- Krypto-Report: gewinn_steuerpflichtig (Haltefrist < 1 Jahr),
  gewinn_steuerfrei (> 1 Jahr), verluste, anzahl_transaktionen, tool_name.
- Werbungskosten: einzelposten als Liste [{{"bezeichnung", "betrag"}}],
  beruflicher_anlass.
- § 35a: arbeitskosten (nur Lohn/Fahrt!), materialkosten, zahlungsart.
- Nebenkostenabrechnung: posten_haushaltsnah als Liste
  [{{"bezeichnung", "betrag"}}] – NUR der Mieteranteil ("Ihr Anteil") von:
  Treppenhaus-/Gebäudereinigung, Hausmeister, Gartenpflege, Winterdienst,
  Aufzugswartung, Feuerlöscherwartung, Ablese-/Messdienst (z. B. Brunata);
  posten_handwerker analog für: Schornsteinfeger, Heizungs-/Gerätewartung,
  kleine Reparaturen. summe_haushaltsnah und summe_handwerker als Zahlen.
  NICHT begünstigt (weglassen!): Grundsteuer, Wasser/Abwasser, Müll,
  Straßenreinigung, Versicherungen, Allgemeinstrom, Brennstoff/Heizöl,
  Heizkosten selbst. steuerjahr = Jahr des ABRECHNUNGSDATUMS (Wahlrecht
  des Mieters), nicht der Abrechnungszeitraum.
- Broker-Steuerbericht (z. B. eToro "Steuerbericht"): kap_zeile19_zinsen
  (nur Zins-/Kapitalerträge ohne Termingeschäfte), kap_zeile21_termingewinne,
  kap_zeile24_terminverluste (als positive Zahl), so_krypto_gewinn
  (Anlage SO Zeile 47/54, Kontrollwert), broker_name, quellensteuer.
- Spenden: organisation, betrag, zuwendungsbestaetigung_vorhanden (bool).
- Betriebseinnahme/-ausgabe (z. B. Gutschrift/Abrechnung eines
  Energieversorgers für verkauften Strom/Wärme, Ausgangsrechnung,
  Wartungsrechnung, Materialbeleg, Anschaffungsbeleg eines Nebengewerbes):
  betrieb_zuordnung (Name/Art des Betriebs, falls aus dem Beleg erkennbar,
  sonst null), netto, umsatzsteuer, brutto, leistungszeitraum (Zeitraum
  oder Datum), menge_und_einheit (z. B. "1.234 kWh"), gegenpartei
  (z. B. "Stadtwerke Bonn"). Bei Anschaffungen von Anlagegütern (Maschinen,
  Geräte, technische Anlagen wie BHKW/PV): zusätzlich ist_anlagegut (bool,
  true bei Wirtschaftsgütern > 800 € netto mit mehrjähriger Nutzung) und
  geschaetzte_nutzungsdauer (Jahre, nach amtlicher AfA-Tabelle schätzen,
  z. B. technische Anlagen 10 Jahre, Büroausstattung 13 Jahre, PC/Software
  3 Jahre – bei Unsicherheit vorsichtig schätzen und rueckfrage stellen).
  Rechnung = "betrieb_einnahme" nur, wenn der Nutzer der Rechnungssteller
  ist (Ausgangsrechnung/Gutschrift AN ihn); Belege, die er selbst bezahlt
  hat, sind "betrieb_ausgabe".
- Rentenbezugsmitteilung (Deutsche Rentenversicherung, Rürup-Anbieter):
  jahresbetrag_rente (Brutto-Jahresbetrag der Rente), rentenbeginn_jahr
  (Jahr, in dem die Rente ERSTMALIG bezogen wurde – steht meist als
  "Rentenbeginn" oder im Betreff, NICHT das Jahr der Mitteilung selbst!).

Regel für "steuerjahr" (WICHTIG für die automatische Sortierung):
- Maßgeblich ist das ZAHLUNGS-/Zuflussjahr (§ 11 EStG, Abflussprinzip),
  nicht das Rechnungsdatum: eine im Januar 2026 bezahlte Rechnung von
  Dezember 2025 → steuerjahr 2026.
- Lohnsteuer-/Bank-/Krypto-Bescheinigungen: das bescheinigte Jahr.
- Ist kein Zahlungsdatum erkennbar, nimm das Belegdatum und formuliere
  eine Rückfrage nach dem Zahlungszeitpunkt, wenn der Beleg aus Dez/Jan
  stammt (Jahreswechsel!).

Regeln für Rückfragen und Hinweise:
- Stelle eine Rückfrage, wenn Werte unleserlich, mehrdeutig oder unvollständig sind.
- Weise auf Fehler hin: falsches Steuerjahr, fehlende Pflichtangaben,
  Barzahlung bei § 35a, Materialkosten in Handwerkerrechnungen,
  Krypto fälschlich als Kapitalertrag deklariert usw.
- Wenn du unsicher bist (confidence < 0.7), wähle "sonstiges" NICHT vorschnell –
  wähle die wahrscheinlichste Kategorie und formuliere eine Rückfrage.
"""


def _build_system_prompt() -> str:
    kat_lines = "\n".join(
        f'- "{key}": {info["label"]} → {info["anlage"]}'
        for key, info in CATEGORIES.items()
    )
    return _SYSTEM_PROMPT.replace("{kategorien}", kat_lines)


def _berechne_klaerungsbedarf(result: dict) -> bool:
    """Klärungsbedarf: unsicher erkannt, 'sonstiges' oder steuerlich
    relevante Angaben fehlen (Betrag/Datum unklar, offene Rückfrage, bei
    Betriebsbelegen fehlende Betrieb-Zuordnung). Deterministisch in Python
    berechnet statt vom Modell selbst behauptet – reproduzierbar testbar."""
    fehlt_relevantes = (
        result.get("betrag_eur") is None
        or not result.get("datum")
        or bool(result.get("rueckfragen"))
        or (result.get("kategorie") in ("betrieb_einnahme", "betrieb_ausgabe")
            and not result.get("extrahierte_daten", {}).get("betrieb_zuordnung"))
    )
    return (result.get("confidence", 0.0) < 0.7
            or result.get("kategorie") == "sonstiges"
            or fehlt_relevantes)


def _content_block(file_bytes: bytes, mime: str) -> dict:
    data = base64.standard_b64encode(file_bytes).decode("ascii")
    if mime == "application/pdf":
        return {
            "type": "document",
            "source": {"type": "base64", "media_type": mime, "data": data},
        }
    if mime in SUPPORTED_IMAGE_TYPES:
        return {
            "type": "image",
            "source": {"type": "base64", "media_type": mime, "data": data},
        }
    raise ValueError(f"Nicht unterstützter Dateityp: {mime}")


def _parse_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("Keine JSON-Antwort erhalten.")
    return json.loads(text[start : end + 1])


def analyze_document(
    file_bytes: bytes,
    mime: str,
    filename: str,
    api_key: str,
    tax_year: int,
    model: str = VISION_MODEL,
) -> dict:
    """Analysiert ein Dokument und gibt das Klassifikations-JSON zurück."""
    client = anthropic.Anthropic(api_key=api_key)

    user_text = (
        f"Steuerjahr der Erklärung: {tax_year}. Dateiname: {filename}.\n"
        "Analysiere das Dokument und antworte nur mit dem JSON-Objekt."
    )

    response = client.messages.create(
        model=model,
        max_tokens=4000,
        system=_build_system_prompt(),
        messages=[
            {
                "role": "user",
                "content": [
                    _content_block(file_bytes, mime),
                    {"type": "text", "text": user_text},
                ],
            }
        ],
    )

    raw = "".join(
        block.text for block in response.content if block.type == "text"
    )
    result = _parse_json(raw)

    # Defaults absichern
    result.setdefault("kategorie", "sonstiges")
    if result["kategorie"] not in CATEGORIES:
        result["hinweise"] = result.get("hinweise", []) + [
            f"Unbekannte Kategorie '{result['kategorie']}' – bitte manuell zuordnen."
        ]
        result["kategorie"] = "sonstiges"
    result.setdefault("confidence", 0.0)
    result.setdefault("extrahierte_daten", {})
    result.setdefault("rueckfragen", [])
    result.setdefault("hinweise", [])
    result.setdefault("betrag_eur", None)
    result["dateiname"] = filename

    result["klaerungsbedarf"] = _berechne_klaerungsbedarf(result)
    result["zuordnungs_historie"] = [{
        "zeitpunkt": datetime.now().isoformat(timespec="seconds"),
        "aktion": "automatische Kategorisierung",
        "von": None, "nach": result["kategorie"], "quelle": "automatisch",
        "begruendung": f"Claude Vision, Confidence {result['confidence']:.0%}",
    }]
    return result
