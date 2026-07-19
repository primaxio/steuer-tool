# Mini-Smoketest für das Betriebsmodul (core/betrieb.py + Integration).
# Beispieldaten aus der Aufgabenstellung: Fernwärme-Gutschriften 3.000 €,
# Wartung 400 €, Anlagegut 12.000 € / 10 Jahre ND, Anschaffung im Juli
# → zeitanteilige AfA 600 € → Gewinn 2.000 €.
# Aufruf: python tests/test_betrieb.py (kein Framework nötig).
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.betrieb import AfaPosition, Betrieb, Position, berechne_euer
from core.checks import run_checks
from core.elster_export import build_summary, render_elster_help
from core.tax_config import get_config
from core.veranlagung import berechne_veranlagung

CFG = get_config(2024)


def _beispiel_betrieb():
    b = Betrieb(name="Fernwärme-Verkauf", art="gewerblich", inhaber="P1",
               kleinunternehmer_19ustg=True)
    b.einnahmen.append(Position("2024-03-15", "Gutschrift Stadtwerke Q1",
                                3000.0, "beleg", "gutschrift.pdf"))
    b.ausgaben.append(Position("2024-05-01", "Wartung Heizanlage", 400.0,
                               "beleg", "wartung.pdf"))
    b.afa_positionen.append(AfaPosition("BHKW-Anlage", 12000.0,
                                        "2024-07-10", 10, "afa.pdf"))
    return b


def test_afa_zeitanteilig():
    a = AfaPosition("Testgut", 12000.0, "2024-07-10", 10)
    assert a.afa_fuer_jahr(2024) == 600.0, a.afa_fuer_jahr(2024)
    assert a.afa_fuer_jahr(2025) == 1200.0, a.afa_fuer_jahr(2025)
    assert a.afa_fuer_jahr(2023) == 0.0
    print("✅ AfA zeitanteilig im Anschaffungsjahr (600 €), volles "
          "Folgejahr (1.200 €)")


def test_euer_gewinn():
    r = berechne_euer(_beispiel_betrieb(), 2024, CFG)
    assert r["einnahmen"] == 3000.0, r["einnahmen"]
    assert r["ausgaben"] == 400.0, r["ausgaben"]
    assert r["afa"] == 600.0, r["afa"]
    assert r["gewinn"] == 2000.0, r["gewinn"]
    assert any("Gewerbesteuer" in h for h in r["hinweise"])
    assert any("Kleinunternehmer" in h for h in r["hinweise"])
    print(f"✅ berechne_euer: Gewinn {r['gewinn']} € (erwartet 2.000 €)")


def test_gewinn_in_veranlagung():
    interview = {
        "zusammenveranlagung": False,
        "_betriebe": {"jahr": 2024, "betriebe": [],
                      "gewinn_pro_person": {"P1": 2000.0, "P2": 0.0}},
    }
    docs = [{
        "dateiname": "lsb.pdf", "kategorie": "lohnsteuerbescheinigung_zivil",
        "inhaber": "P1",
        "extrahierte_daten": {"bruttoarbeitslohn": 40000, "lohnsteuer": 6000},
    }]
    v = berechne_veranlagung(docs, CFG, interview)
    step = next(s for s in v["schritte"] if "Gewerbebetrieb" in s["text"])
    assert step["wert"] == 2000.0, step
    summe_step = next(s for s in v["schritte"]
                      if s["text"] == "= Summe der Einkünfte")
    # Bruttolohn 40000 - WK-Pauschbetrag 1230 + Betriebsgewinn 2000
    assert summe_step["wert"] == 40000 - CFG["arbeitnehmer_pauschbetrag"] + 2000, \
        summe_step
    print(f"✅ Betriebsgewinn fließt in die Summe der Einkünfte ein "
          f"({step['wert']} €)")


def test_elster_export_und_checks():
    b = _beispiel_betrieb()
    r = berechne_euer(b, 2024, CFG)
    interview = {
        "zusammenveranlagung": False, "hat_betrieb_P1": True,
        "_betriebe": {"jahr": 2024, "betriebe": [r],
                      "gewinn_pro_person": {"P1": r["gewinn"], "P2": 0.0}},
    }
    summary = build_summary([], CFG, interview)
    block = summary["anlagen"]["Gewerbe & Selbständigkeit (EÜR)"]
    assert block["gewinn_pro_person"]["P1"] == 2000.0

    md = render_elster_help(summary)
    assert "Anlage G / Anlage EÜR" in md
    assert "Fernwärme-Verkauf" in md
    assert "2.000,00 €" in md
    assert "BHKW-Anlage" in md and "600,00 €" in md
    print("✅ ELSTER-Hilfe enthält Anlage-G-Block mit Betrieb, Gewinn "
          "und AfA-Position")

    findings = run_checks([], CFG, interview)
    assert not any("noch kein Betrieb" in f["text"] for f in findings), \
        "Sollte keinen 'fehlenden Betrieb'-Hinweis geben, da einer erfasst ist"

    # Zweiter Fall: hat_betrieb=True, aber KEIN Betrieb erfasst.
    findings2 = run_checks([], CFG, {"hat_betrieb_P1": True})
    assert any("noch kein Betrieb" in f["text"] for f in findings2)
    print("✅ checks.py meldet fehlenden Betrieb korrekt (nur wenn wirklich "
          "keiner erfasst ist)")

    # Dritter Fall: Betrieb erfasst, aber ohne jegliche Einnahmen/Ausgaben.
    leer = Betrieb(name="Leerer Betrieb", art="freiberuflich", inhaber="P2")
    r_leer = berechne_euer(leer, 2024, CFG)
    findings3 = run_checks([], CFG, {"_betriebe": {
        "betriebe": [r_leer], "gewinn_pro_person": {"P1": 0.0, "P2": 0.0}}})
    assert any("Noch keine Einnahmen/Ausgaben" in f["text"] for f in findings3)
    print("✅ checks.py meldet Betrieb ohne Einnahmen/Ausgaben")


if __name__ == "__main__":
    test_afa_zeitanteilig()
    test_euer_gewinn()
    test_gewinn_in_veranlagung()
    test_elster_export_und_checks()
    print("🎉 Alle Betriebsmodul-Tests bestanden.")
