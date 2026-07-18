"""Mini-Test: Doppelerfassungs-Wächter in run_checks()."""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from core.checks import run_checks

BASE_CFG = {
    "jahr": 2024,
    "abgabefrist_datum": "2025-07-31",
    "_geprueft": True,
    "sparer_pauschbetrag": 1000,
    "arbeitnehmer_pauschbetrag": 1230,
    "entfernungspauschale_bis_20km": 0.30,
    "entfernungspauschale_ab_21km": 0.38,
    "homeoffice_pauschale_pro_tag": 6,
    "homeoffice_max": 1260,
    "freigrenze_private_veraeusserung": 1000,
    "kinderbetreuung": {"anteil_prozent": 80, "max": 4800},
}

NK_DOC = {
    "dateiname": "nk.pdf",
    "kategorie": "nebenkostenabrechnung",
    "extrahierte_daten": {},
    "inhaber": "P1",
    "steuerjahr": 2024,
}

BROKER_DOC = {
    "dateiname": "broker.pdf",
    "kategorie": "broker_steuerbericht",
    "extrahierte_daten": {},
    "inhaber": "P1",
    "steuerjahr": 2024,
}


def test_nk_doppelerfassung_fehler():
    interview = {
        "hat_bundeswehr": False,
        "spar": {"nk_abrechnung": {"aktiv": True}},
        "personen": {"P1": "Person 1"},
    }
    findings = run_checks([NK_DOC], BASE_CFG, interview)
    fehler = [f for f in findings
              if f["level"] == "fehler" and "DOPPELERFASSUNG" in f["text"]]
    assert fehler, "Kein Fehler mit 'DOPPELERFASSUNG' gefunden!"
    print("PASS: NK-Doppelerfassung → fehler mit 'DOPPELERFASSUNG'")


def test_nk_kein_fehler_ohne_spar_haken():
    interview = {
        "hat_bundeswehr": False,
        "spar": {"nk_abrechnung": {"aktiv": False}},
        "personen": {"P1": "Person 1"},
    }
    findings = run_checks([NK_DOC], BASE_CFG, interview)
    fehler = [f for f in findings
              if f["level"] == "fehler" and "DOPPELERFASSUNG" in f["text"]]
    assert not fehler, "Fälschlich DOPPELERFASSUNG-Fehler ohne aktiven Spar-Haken!"
    print("PASS: kein falscher DOPPELERFASSUNG-Fehler ohne aktiven Spar-Haken")


def test_broker_warnung_bei_manuellen_kap_feldern():
    interview = {
        "hat_bundeswehr": False,
        "personen": {"P1": "Person 1"},
        "termin_gewinne_P1": "500",
    }
    findings = run_checks([BROKER_DOC], BASE_CFG, interview)
    warnungen = [f for f in findings
                 if f["level"] == "warnung" and "Doppelerfassung KAP" in f["text"]]
    assert warnungen, "Keine KAP-Doppelerfassungs-Warnung gefunden!"
    print("PASS: Broker-Doppelerfassung → warnung mit 'Doppelerfassung KAP'")


def test_broker_keine_warnung_ohne_manuelle_felder():
    interview = {
        "hat_bundeswehr": False,
        "personen": {"P1": "Person 1"},
    }
    findings = run_checks([BROKER_DOC], BASE_CFG, interview)
    warnungen = [f for f in findings
                 if f["level"] == "warnung" and "Doppelerfassung KAP" in f["text"]]
    assert not warnungen, "Fälschliche KAP-Warnung ohne manuelle Felder!"
    print("PASS: keine KAP-Warnung ohne manuelle Felder")


if __name__ == "__main__":
    test_nk_doppelerfassung_fehler()
    test_nk_kein_fehler_ohne_spar_haken()
    test_broker_warnung_bei_manuellen_kap_feldern()
    test_broker_keine_warnung_ohne_manuelle_felder()
    print("\nAlle Tests bestanden.")
