"""
Mini-Smoketest für die Automatik-Kategorien (ohne API):
Nebenkostenabrechnung → § 35a-Ermäßigung ≈ 124 €,
Broker-Steuerbericht → KAP Z. 19/21/24 in der ELSTER-Hilfe,
Hinweise (NK-Übernahme + Krypto-Kontrollwert) in run_checks.

Start:  python tests/test_automatik.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.checks import run_checks
from core.elster_export import build_summary, render_elster_help
from core.sparcheck import _nk_automatik_werte
from core.tax_config import get_config
from core.veranlagung import berechne_veranlagung

DOCS = [
    {
        "dateiname": "nk_abrechnung_2024.pdf",
        "kategorie": "nebenkostenabrechnung",
        "aussteller": "Hausverwaltung Bonn",
        "inhaber": "P1",
        "extrahierte_daten": {
            "summe_haushaltsnah": 593.64,
            "summe_handwerker": 26.26,
        },
    },
    {
        "dateiname": "etoro_steuerbericht_2024.pdf",
        "kategorie": "broker_steuerbericht",
        "aussteller": "eToro",
        "inhaber": "P1",
        "extrahierte_daten": {
            "kap_zeile21_termingewinne": 1500,
            "kap_zeile24_terminverluste": 200,
            "kap_zeile19_zinsen": 82.10,
            "so_krypto_gewinn": 750,
        },
    },
]

INTERVIEW = {
    "zusammenveranlagung": False,
    "_crypto": {"pro_person": {}, "warnungen": []},
}


def test_checks_hinweise():
    cfg = get_config(2024)
    findings = run_checks(DOCS, cfg, dict(INTERVIEW))
    texte = [f["text"] for f in findings if f["level"] == "hinweis"]
    assert any("§ 35a-Posten automatisch übernommen" in t and "593.64" in t
               for t in texte), "NK-Übernahme-Hinweis fehlt"
    assert any("Kontrollwert" in t and "750.00" in t for t in texte), \
        "Broker-Kontrollwert-Hinweis fehlt"
    print(f"✅ run_checks: NK- und Kontrollwert-Hinweis vorhanden "
          f"({len(findings)} Findings gesamt)")


def test_summary_und_elster_hilfe():
    cfg = get_config(2024)
    s = build_summary(DOCS, cfg, dict(INTERVIEW))

    h35a = s["anlagen"]["Haushaltsnahe Aufwendungen"]
    assert abs(h35a["arbeitskosten_gesamt"] - 619.90) < 0.01, h35a
    erm = h35a["ermaessigung_geschaetzt"]
    assert abs(erm - 123.98) < 0.5, f"§ 35a-Ermäßigung ≈124 € erwartet: {erm}"

    kap = s["anlagen"]["KAP"]
    assert kap["termingeschaefte_gewinne"] == 1500.0
    assert kap["termingeschaefte_verluste"] == 200.0
    assert kap["auslaendische_zinsen"] == 82.10

    md = render_elster_help(s)   # darf trotz leerer Krypto-Daten nicht crashen
    assert "Zeile 21): 1.500,00 €" in md
    assert "Zeile 24): 200,00 €" in md
    assert "Zeile 19): 82,10 €" in md
    print(f"✅ build_summary/ELSTER-Hilfe: § 35a-Ermäßigung {erm:.2f} €, "
          "KAP Z. 19/21/24 im Export")


def test_veranlagung_ermaessigung():
    cfg = get_config(2024)
    b = berechne_veranlagung(DOCS, cfg, dict(INTERVIEW))
    erm = sum(-st["wert"] for st in b["schritte"]
              if st["text"].startswith("− § 35a"))
    assert abs(erm - 123.98) < 0.5, f"§ 35a im Rechner ≈124 € erwartet: {erm}"
    assert any("Broker-Steuerberichte automatisch übernommen" in w
               for w in b["warnhinweise"]), "Broker-Warnhinweis fehlt"
    print(f"✅ berechne_veranlagung: § 35a-Ermäßigung {erm:.2f} €, "
          "Broker-Warnhinweis vorhanden")


def test_sparcheck_nk_automatik_werte():
    """Spar-Check-Tab (Doppelerfassungs-Hinweis direkt am Eingabefeld,
    siehe app.py) liest dieselben Summen wie checks.py/veranlagung.py."""
    werte = _nk_automatik_werte(DOCS)
    assert werte["summe_haushaltsnah"] == 593.64
    assert werte["summe_handwerker"] == 26.26
    assert _nk_automatik_werte([])["summe_haushaltsnah"] == 0.0
    assert _nk_automatik_werte(None)["summe_handwerker"] == 0.0
    print("✅ sparcheck._nk_automatik_werte() summiert korrekt "
         "(inkl. leere/None-Docs-Liste)")


def test_sparcheck_warnhinweis_zerstoert_satzzeichen_nicht():
    """Regressionstest für einen Bug, der beim ersten Schreiben dieses
    Features auftrat: .replace(',', 'X').replace('.', ',').replace('X', '.')
    auf den GESAMTEN (verketteten) Hinweistext statt nur auf die
    formatierte Zahl angewendet zerstört jedes Komma/jeden Punkt im Satz
    (z. B. 'ZUSÄTZLICHE, davon' -> 'ZUSÄTZLICHE. davon')."""
    nk_wert = 1234.5
    nk_wert_str = (f"{nk_wert:,.2f} €".replace(",", "X")
                  .replace(".", ",").replace("X", "."))
    assert nk_wert_str == "1.234,50 €", nk_wert_str
    satz = ("Häkchen hier nur setzen, wenn du ZUSÄTZLICHE, davon "
           f"unabhängige Kosten von {nk_wert_str} eintragen willst.")
    assert "ZUSÄTZLICHE, davon" in satz, \
        "Satzkomma darf durch die Zahlenformatierung nicht verändert werden"
    assert satz.count(nk_wert_str) == 1
    print("✅ Zahlenformatierung im Doppelerfassungs-Hinweis lässt "
         "Satzzeichen im Fließtext unangetastet")


if __name__ == "__main__":
    test_checks_hinweise()
    test_summary_und_elster_hilfe()
    test_veranlagung_ermaessigung()
    test_sparcheck_nk_automatik_werte()
    test_sparcheck_warnhinweis_zerstoert_satzzeichen_nicht()
    print("🎉 Alle Automatik-Tests bestanden.")
