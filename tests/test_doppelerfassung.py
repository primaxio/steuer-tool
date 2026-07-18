# Mini-Smoketest für den Doppelerfassungs-Wächter in core/checks.py.
# Aufruf: python tests/test_doppelerfassung.py (kein Framework nötig).
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.checks import run_checks
from core.tax_config import get_config


def test_nk_doppelerfassung():
    docs = [{
        "dateiname": "nk_2024.pdf",
        "kategorie": "nebenkostenabrechnung",
        "extrahierte_daten": {},
    }]
    interview = {"spar": {"nk_abrechnung": {"aktiv": True}}}
    findings = run_checks(docs, get_config(2024), interview)
    treffer = [f for f in findings
               if f["level"] == "fehler" and "DOPPELERFASSUNG" in f["text"]]
    assert treffer, "Kein DOPPELERFASSUNG-Fehler gefunden: %r" % findings


def test_kap_doppelerfassung():
    docs = [{
        "dateiname": "etoro_report.pdf",
        "kategorie": "broker_steuerbericht",
        "extrahierte_daten": {},
    }]
    interview = {"termin_gewinne_P1": "906,49"}
    findings = run_checks(docs, get_config(2024), interview)
    treffer = [f for f in findings
               if f["level"] == "warnung" and "Doppelerfassung KAP" in f["text"]]
    assert treffer, "Keine KAP-Doppelerfassungs-Warnung gefunden: %r" % findings


def test_keine_falschmeldung():
    # Scan ohne Spar-Check-Haken darf KEINEN Doppelerfassungs-Fehler geben.
    docs = [{
        "dateiname": "nk_2024.pdf",
        "kategorie": "nebenkostenabrechnung",
        "extrahierte_daten": {},
    }]
    findings = run_checks(docs, get_config(2024), {})
    assert not any("DOPPELERFASSUNG" in f["text"] for f in findings)


if __name__ == "__main__":
    test_nk_doppelerfassung()
    test_kap_doppelerfassung()
    test_keine_falschmeldung()
    print("OK – Doppelerfassungs-Wächter greift wie erwartet.")
