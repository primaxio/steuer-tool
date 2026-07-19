# Regressionstests für die in AUDIT.md als "kritisch" behobenen Punkte:
# 1) KeyError-Crash bei fehlendem "extrahierte_daten"-Key
# 2) krypto_report-Dokument ohne FIFO-Engine fehlte in der Steuerschätzung
# 3) Übergangsbeihilfe floss nirgends in Rechnung/Export ein
# Aufruf: python tests/test_audit_fixes.py (kein Framework nötig).
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.checks import run_checks
from core.elster_export import build_summary
from core.tax_config import get_config
from core.veranlagung import berechne_veranlagung

CFG = get_config(2024)


def test_kein_keyerror_ohne_extrahierte_daten():
    # Dokumente OHNE "extrahierte_daten"-Key (z. B. handgepflegtes/älteres
    # JSON) dürfen run_checks nicht mit KeyError abschießen.
    docs = [
        {"dateiname": "bank.pdf", "kategorie": "steuerbescheinigung_bank",
         "inhaber": "P1", "betrag_eur": 500.0},
        {"dateiname": "nk.pdf", "kategorie": "nebenkostenabrechnung",
         "inhaber": "P1"},
        {"dateiname": "broker.pdf", "kategorie": "broker_steuerbericht",
         "inhaber": "P1"},
    ]
    findings = run_checks(docs, CFG, {"zusammenveranlagung": False})
    assert isinstance(findings, list)
    print("✅ run_checks crasht nicht bei fehlendem extrahierte_daten-Key")


def test_krypto_report_fallback_in_schaetzung():
    docs = [{
        "dateiname": "lsb.pdf", "kategorie": "lohnsteuerbescheinigung_zivil",
        "inhaber": "P1",
        "extrahierte_daten": {"bruttoarbeitslohn": 40000, "lohnsteuer": 6000},
    }, {
        "dateiname": "blockpit.pdf", "kategorie": "krypto_report",
        "inhaber": "P1",
        "extrahierte_daten": {"gewinn_steuerpflichtig": 2000},
    }]
    interview = {"zusammenveranlagung": False}
    v = berechne_veranlagung(docs, CFG, interview)
    krypto_step = next(s for s in v["schritte"]
                       if "Krypto-Einkünfte" in s["text"])
    assert krypto_step["wert"] == 2000, krypto_step
    assert any("Krypto-Report-Dokument" in w for w in v["warnhinweise"])
    print("✅ krypto_report-Fallback fließt in die Steuerschätzung ein "
          f"({krypto_step['wert']} €)")

    # Mit FIFO-Engine-Daten darf NICHT zusätzlich der Report-Fallback
    # gezogen werden (sonst Doppelzählung!).
    interview["_crypto"] = {"pro_person": {
        "P1": {"steuerpflichtiger_betrag": 500, "rewards_steuerpflichtig": 0}}}
    v2 = berechne_veranlagung(docs, CFG, interview)
    krypto_step2 = next(s for s in v2["schritte"]
                        if "Krypto-Einkünfte" in s["text"])
    assert krypto_step2["wert"] == 500, \
        f"Doppelzählung! Erwartet 500 (nur FIFO-Engine): {krypto_step2}"
    print("✅ Kein Doppelzählung: FIFO-Engine-Daten haben Vorrang vor "
          "krypto_report-Fallback")


def test_uebergangsbeihilfe_in_rechnung_und_export():
    docs = [{
        "dateiname": "lsb.pdf", "kategorie": "lohnsteuerbescheinigung_zivil",
        "inhaber": "P1",
        "extrahierte_daten": {"bruttoarbeitslohn": 30000, "lohnsteuer": 4000},
    }, {
        "dateiname": "beihilfe.pdf", "kategorie": "uebergangsbeihilfe",
        "inhaber": "P1", "betrag_eur": 15000.0,
    }]
    interview = {"zusammenveranlagung": False}
    v = berechne_veranlagung(docs, CFG, interview)
    beihilfe_step = next(s for s in v["schritte"]
                         if "Übergangsbeihilfe" in s["text"])
    assert beihilfe_step["wert"] == 15000.0, beihilfe_step
    brutto_step = next(s for s in v["schritte"] if s["text"] == "Bruttolohn P1")
    assert brutto_step["wert"] == 45000.0, \
        f"Übergangsbeihilfe muss im Bruttolohn stecken: {brutto_step}"

    findings = run_checks(docs, CFG, interview)
    assert any("Fünftelregelung" in f["text"] for f in findings), \
        "Fünftelregelung-Hinweis fehlt"

    summary = build_summary(docs, CFG, interview)
    ub = summary["anlagen"]["N"]["uebergangsbeihilfe"]
    assert ub and ub[0]["betrag"] == 15000.0
    print("✅ Übergangsbeihilfe fließt in Bruttolohn, ELSTER-Export und "
          "Fünftelregelung-Hinweis ein")


if __name__ == "__main__":
    test_kein_keyerror_ohne_extrahierte_daten()
    test_krypto_report_fallback_in_schaetzung()
    test_uebergangsbeihilfe_in_rechnung_und_export()
    print("🎉 Alle Audit-Fix-Regressionstests bestanden.")
