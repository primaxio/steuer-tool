"""
Prüfungsfester Krypto-Steuerreport (PDF) für die Anlage SO:
Methodik-Seite (BMF-Schreiben v. 06.03.2025, walletbezogene FIFO,
§ 23 EStG), Kennzahlen je Person, vollständige Veräußerungsliste und
offene Bestände. Ziel: dieselbe Nachvollziehbarkeit, wegen der
kommerzielle Reports vom Finanzamt akzeptiert werden.
"""

from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (PageBreak, Paragraph, SimpleDocTemplate,
                                Spacer, Table, TableStyle)

GOLD = colors.HexColor("#B08A2E")
GRAU = colors.HexColor("#F2F0EA")

_s = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=_s["Title"], fontSize=18, spaceAfter=4)
H2 = ParagraphStyle("H2", parent=_s["Heading2"], fontSize=12,
                    spaceBefore=10, spaceAfter=4)
P = ParagraphStyle("P", parent=_s["Normal"], fontSize=9.5, leading=13)
KLEIN = ParagraphStyle("K", parent=P, fontSize=8, textColor=colors.grey)

METHODIK = [
    "Rechtsgrundlage: § 22 Nr. 2 i. V. m. § 23 Abs. 1 Nr. 2 EStG (private "
    "Veräußerungsgeschäfte) sowie § 22 Nr. 3 EStG für Staking-/Reward-"
    "Einnahmen; Verwaltungsauffassung nach BMF-Schreiben vom 06.03.2025 "
    "(Ertragsteuerrechtliche Behandlung von Kryptowerten).",
    "Verbrauchsfolge: FIFO (First in – first out), WALLETBEZOGEN je "
    "(Inhaber, Verwahrstelle/Wallet, Kryptowert) angewendet.",
    "Haltefrist: 1 Jahr gem. § 23 EStG; Fristberechnung nach §§ 187, 188 "
    "BGB (Veräußerungen nach Ablauf des Jahrestags sind steuerfrei und in "
    "der Spalte 'steuerfrei' gekennzeichnet).",
    "Anschaffungskosten inkl. Erwerbsnebenkosten (Gebühren); "
    "Veräußerungserlöse abzüglich Veräußerungskosten.",
    "Tausch Krypto↔Krypto gilt als Veräußerung des hingegebenen und "
    "Anschaffung des erhaltenen Kryptowerts zum Marktwert.",
    "Bewertung: EUR-Werte aus Börsenabrechnungen; ersatzweise historische "
    "Tageskurse (CoinGecko) bzw. EZB-USD-Referenzkurse je Handelstag.",
    "Freigrenze § 23 Abs. 3 S. 5 EStG (1.000 € p. P. ab VZ 2024) und "
    "Freigrenze § 22 Nr. 3 EStG (256 €) werden je Person geprüft.",
    "Datenquellen: siehe Spalte 'Depot' (Börsen-Exporte, API-Abrufe, "
    "On-Chain-Daten Basescan). Vollständigkeit wurde durch "
    "Bestandsfortschreibung plausibilisiert; Warnhinweise sind im "
    "Anhang aufgeführt.",
]


def _geld(v):
    return f"{v:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def erstelle_report(pfad: str, jahr: int, personen: dict, agg: dict,
                    disposals: list, open_lots: list, warnungen: list,
                    stammdaten: dict | None = None):
    doc = SimpleDocTemplate(pfad, pagesize=landscape(A4),
                            leftMargin=1.4*cm, rightMargin=1.4*cm,
                            topMargin=1.4*cm, bottomMargin=1.4*cm,
                            title=f"Krypto-Steuerreport {jahr}")
    story = [
        Paragraph(f"Krypto-Steuerreport {jahr}", H1),
        Paragraph(f"Anlage SO – private Veräußerungsgeschäfte · erstellt am "
                  f"{datetime.now():%d.%m.%Y %H:%M}", KLEIN),
        Spacer(1, 6),
    ]
    if stammdaten:
        zeilen = [f"Steuernummer: {stammdaten.get('steuernummer', '–')}",
                  f"Steuer-ID P1: {stammdaten.get('steuer_id_P1', '–')} · "
                  f"Steuer-ID P2: {stammdaten.get('steuer_id_P2', '–')}"]
        story.append(Paragraph(" · ".join(zeilen), P))

    story.append(Paragraph("Methodik", H2))
    for m in METHODIK:
        story.append(Paragraph("– " + m, P))

    story.append(Paragraph("Ergebnis je steuerpflichtiger Person", H2))
    kopf = ["Person", "Veräußerungen", "Gewinn (<1 J.)", "Verluste",
            "Netto", "Steuerfrei (>1 J.)", "Gebühren", "Freigrenze",
            "Steuerpflichtig", "Rewards"]
    daten = [kopf]
    for p_key, a in agg.items():
        if not (a["veraeusserungen"] or a["rewards_summe"]):
            continue
        daten.append([
            personen.get(p_key, p_key), a["veraeusserungen"],
            _geld(a["gewinn_brutto"]), _geld(a["verluste"]),
            _geld(a["netto_gewinn"]),
            _geld(a["gewinn_steuerfrei_haltefrist"]), _geld(a["gebuehren"]),
            "unterschritten ✓" if a["unter_freigrenze"] else "überschritten",
            _geld(a["steuerpflichtiger_betrag"]), _geld(a["rewards_summe"])])
    t = Table(daten, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), GOLD),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, GRAU])]))
    story += [t, PageBreak(),
              Paragraph("Einzelaufstellung aller Veräußerungen", H2)]

    kopf2 = ["Person", "Depot", "Asset", "Menge", "Anschaffung",
             "Veräußerung", "Haltetage", "Kosten", "Erlös", "Gebühren",
             "Gewinn/Verlust", "steuerfrei"]
    daten2 = [kopf2]
    for d in sorted(disposals, key=lambda x: (x.inhaber, x.verkauf_ts)):
        daten2.append([
            personen.get(d.inhaber, d.inhaber), d.depot, d.asset,
            f"{d.menge:.8g}", f"{d.kauf_ts:%d.%m.%Y}",
            f"{d.verkauf_ts:%d.%m.%Y}", d.haltetage, _geld(d.kosten_eur),
            _geld(d.erloes_eur), _geld(d.gebuehren_eur), _geld(d.gewinn),
            "ja" if d.steuerfrei else "nein"])
    t2 = Table(daten2, repeatRows=1)
    t2.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1A1A21")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, GRAU])]))
    story.append(t2)

    if open_lots:
        story += [PageBreak(),
                  Paragraph("Bestände zum Berichtszeitpunkt (offene Lots)",
                            H2)]
        daten3 = [["Person", "Depot", "Asset", "Menge", "Anschaffung",
                   "Kosten", "steuerfrei ab"]]
        for l in sorted(open_lots, key=lambda x: x.steuerfrei_ab):
            daten3.append([personen.get(l.inhaber, l.inhaber), l.depot,
                           l.asset, f"{l.menge:.8g}",
                           f"{l.kauf_ts:%d.%m.%Y}", _geld(l.kosten_eur),
                           f"{l.steuerfrei_ab:%d.%m.%Y}"])
        t3 = Table(daten3, repeatRows=1)
        t3.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), GOLD),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.grey)]))
        story.append(t3)

    if warnungen:
        story += [PageBreak(), Paragraph("Anhang: Hinweise & offene Punkte",
                                         H2)]
        for w in warnungen:
            story.append(Paragraph("– " + str(w), P))

    story += [Spacer(1, 14), Paragraph(
        "Dieser Report wurde mit einem privaten Berechnungstool erstellt "
        "(FIFO walletbezogen). Er dient als Anlage zur Einkommensteuer-"
        "erklärung und ersetzt keine Steuerberatung. Zugrunde liegende "
        "Exporte/Belege werden gem. Vorhaltepflicht aufbewahrt.", KLEIN)]
    doc.build(story)
    return pfad
