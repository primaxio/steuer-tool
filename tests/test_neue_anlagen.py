"""
Regressionstests für die neuen Anlagen aus der zweiten "alles machen"-Runde:
agB Zumutbare Belastung (§ 33 EStG), Behinderten-/Pflege-Pauschbetrag +
§ 33a Unterhalt (§ 33b EStG), Anlage AV (Riester, § 10a EStG),
Anlage R (Renten, § 22 Nr. 1 EStG), Rürup/Basisrente als volle
Vorsorgeaufwendung. Reine assert-Skripte ohne API-Zugriff, siehe
CLAUDE.md-Testkonvention.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.categories import CATEGORIES
from core.elster_export import build_summary, render_elster_help
from core.erklaerungen import KATEGORIE_ERKLAERUNG
from core.rente import besteuerungsanteil_prozent, rentenanteil_steuerpflichtig
from core.tax_config import get_config
from core.veranlagung import (_behinderten_pflege_unterhalt,
                              _zumutbare_belastung, berechne_veranlagung)

CFG24 = get_config(2024)


def _lsb(brutto, inhaber="P1", **extra):
    daten = {"bruttoarbeitslohn": brutto, "lohnsteuer": 0, "soli": 0,
             "kirchensteuer": 0, "rv_arbeitnehmer": 0, "kv_beitraege": 0,
             "pv_beitraege": 0}
    daten.update(extra)
    return {"kategorie": "lohnsteuerbescheinigung_zivil", "inhaber": inhaber,
            "dateiname": f"lsb_{inhaber}.pdf", "zuordnungs_historie": [{}],
            "extrahierte_daten": daten}


def _step(v, needle):
    for s in v["schritte"]:
        if needle in s["text"]:
            return s["wert"]
    return None


# ---------------------------------------------------------------- Kategorien
def test_kategorie_sync():
    for key in CATEGORIES:
        assert key in KATEGORIE_ERKLAERUNG, \
            f"'{key}' fehlt in KATEGORIE_ERKLAERUNG (CLAUDE.md-Invariante)."
    print("✅ categories.py und erklaerungen.py bleiben synchron "
         f"({len(CATEGORIES)} Kategorien)")


# ---------------------------------------------------------------- agB
def test_zumutbare_belastung_dreistufig():
    # Ledig, keine Kinder, 60.000 € Gesamtbetrag der Einkünfte:
    # 15.340*5% + (51.130-15.340)*6% + (60.000-51.130)*7%
    erwartet = round(15340 * 0.05 + (51130 - 15340) * 0.06
                     + (60000 - 51130) * 0.07, 2)
    ergebnis = _zumutbare_belastung(60000, False, 0, CFG24)
    assert ergebnis == erwartet, f"{ergebnis} != {erwartet}"

    # Verheiratet, 3 Kinder: niedrigste Satzspalte
    erwartet2 = round(15340 * 0.01 + (51130 - 15340) * 0.01
                      + (60000 - 51130) * 0.02, 2)
    ergebnis2 = _zumutbare_belastung(60000, True, 3, CFG24)
    assert ergebnis2 == erwartet2, f"{ergebnis2} != {erwartet2}"
    assert ergebnis2 < ergebnis, "Familien mit Kindern müssen weniger " \
        "zumutbare Belastung tragen als Kinderlose."
    print(f"✅ Zumutbare Belastung (§ 33 Abs. 3 EStG) dreistufig korrekt: "
         f"ledig={ergebnis} €, verheiratet+3 Kinder={ergebnis2} €")


def test_agb_krankheitskosten_nutzt_echte_zumutbare_belastung():
    docs = [_lsb(60000)]
    iv = {"zusammenveranlagung": False,
         "spar": {"krankheit": {"aktiv": True, "betrag": 2000.0}}}
    v = berechne_veranlagung(docs, CFG24, iv)
    zumutbar_erwartet = _zumutbare_belastung(
        _step(v, "Summe der Einkünfte"), False, 0, CFG24)
    agb_wirksam = -_step(v, "Außergew. Belastungen")
    assert agb_wirksam == round(max(0.0, 2000.0 - zumutbar_erwartet), 2)
    print(f"✅ agB-Krankheitskosten nutzen die echte Stufentabelle "
         f"(wirksam: {agb_wirksam} €)")


# ---------------------------------------------------------------- § 33b/33a
def test_behinderten_pauschbetrag_stufen():
    iv = {"gdb_P1": 45}  # zwischen 40 und 50 -> niedrigere Stufe (40) gilt
    summe, hinweise = _behinderten_pflege_unterhalt(iv, CFG24)
    assert summe == CFG24["behinderten_pauschbetrag"][40], summe
    assert any("GdB 45" in h for h in hinweise)


def test_behinderten_pauschbetrag_hilflos_blind():
    iv = {"gdb_P1": 50, "gdb_hilflos_blind_P1": True}
    summe, _ = _behinderten_pflege_unterhalt(iv, CFG24)
    assert summe == CFG24["behinderten_pauschbetrag_hilflos_blind"] == 7400


def test_pflege_pauschbetrag():
    for grad, erwartet in [(2, 600), (3, 1100), (4, 1800), (5, 1800)]:
        iv = {"pflegegrad_angehoeriger": grad}
        summe, _ = _behinderten_pflege_unterhalt(iv, CFG24)
        assert summe == erwartet, f"Pflegegrad {grad}: {summe} != {erwartet}"
    print("✅ Behinderten-Pauschbetrag (Stufe + hilflos/blind) und "
         "Pflege-Pauschbetrag korrekt")


def test_unterhalt_33a_kuerzung_durch_eigene_einkuenfte():
    iv = {"unterhalt_betrag": 5000, "unterhalt_eigene_einkuenfte": 1000}
    summe, hinweise = _behinderten_pflege_unterhalt(iv, CFG24)
    # Kürzung: eigene Einkünfte 1000 - 624 anrechnungsfrei = 376
    assert summe == round(5000 - 376, 2) == 4624.0
    assert any("33a" in h for h in hinweise)
    # Höchstbetrag = Grundfreibetrag deckelt auch ohne Kürzung
    iv2 = {"unterhalt_betrag": 50000}
    summe2, _ = _behinderten_pflege_unterhalt(iv2, CFG24)
    assert summe2 == CFG24["grundfreibetrag"]
    print("✅ § 33a-Unterhalt: Kürzung um eigene Einkünfte und "
         "Grundfreibetrag-Deckel korrekt")


def test_pauschbetraege_wirken_ohne_kuerzung_um_zumutbare_belastung():
    """Kernunterschied zu Krankheitskosten: volle Wirkung, keine Schwelle."""
    docs = [_lsb(60000)]
    iv_ohne = {"zusammenveranlagung": False}
    iv_mit = {"zusammenveranlagung": False, "gdb_P1": 50}
    v_ohne = berechne_veranlagung(docs, CFG24, iv_ohne)
    v_mit = berechne_veranlagung(docs, CFG24, iv_mit)
    diff = v_mit["ergebnis"] - v_ohne["ergebnis"]
    # Der Pauschbetrag (1.140 €) muss VOLL das zvE mindern -> Steuerersparnis
    # entspricht ungefähr Grenzsteuersatz * 1.140, jedenfalls > 0.
    assert diff > 0, "Behinderten-Pauschbetrag muss die Erstattung erhöhen."
    step_wert = _step(v_mit, "Behinderten-/Pflege-Pauschbetrag")
    assert step_wert == -CFG24["behinderten_pauschbetrag"][50]
    print(f"✅ Behinderten-Pauschbetrag wirkt ungekürzt im Rechenweg "
         f"({step_wert} €), Erstattung steigt um {diff:.2f} €")


# ---------------------------------------------------------------- Riester
def test_riester_zusatzvorteil_bei_hohem_grenzsteuersatz():
    docs = [_lsb(70000, rv_arbeitnehmer=6510, kv_beitraege=5460, pv_beitraege=1260)]
    iv = {"zusammenveranlagung": False, "riester_beitrag_P1": 2100}
    v = berechne_veranlagung(docs, CFG24, iv)
    zusatzvorteil = _step(v, "Riester-Günstigerprüfung")
    assert zusatzvorteil is not None and zusatzvorteil < 0, \
        "Bei hohem Einkommen muss der Sonderausgabenabzug mehr bringen als die Zulage."
    print(f"✅ Riester-Günstigerprüfung greift bei hohem Grenzsteuersatz "
         f"({zusatzvorteil} €)")


def test_riester_bleibt_bei_zulage_wenn_guenstiger():
    # Sehr niedriges Einkommen -> Grenzsteuersatz nahe 0, Zulage übersteigt
    # die Steuerersparnis durch den Abzug.
    docs = [_lsb(13000)]
    iv = {"zusammenveranlagung": False, "riester_beitrag_P1": 2100}
    v = berechne_veranlagung(docs, CFG24, iv)
    zusatzvorteil = _step(v, "Riester-Günstigerprüfung")
    assert zusatzvorteil is None, \
        "Bei sehr niedrigem Einkommen darf kein Zusatzvorteil-Schritt auftauchen."
    assert any("Zulage" in w and "mindestens so hoch" in w
              for w in v["warnhinweise"])
    print("✅ Riester: bei niedrigem Einkommen bleibt es bei der Zulage "
         "(kein Bescheid-Zusatzeffekt)")


def test_riester_kinderzulage_fliesst_ein():
    docs = [_lsb(70000, rv_arbeitnehmer=6510, kv_beitraege=5460, pv_beitraege=1260)]
    iv_ohne_kind = {"zusammenveranlagung": False, "riester_beitrag_P1": 2100}
    iv_mit_kind = {"zusammenveranlagung": False, "riester_beitrag_P1": 2100,
                  "riester_kinder_ab_2008": 2}
    v_ohne = berechne_veranlagung(docs, CFG24, iv_ohne_kind)
    v_mit = berechne_veranlagung(docs, CFG24, iv_mit_kind)
    # Mehr Zulage -> kleinerer (weniger negativer) Zusatzvorteil
    zv_ohne = _step(v_ohne, "Riester-Günstigerprüfung")
    zv_mit = _step(v_mit, "Riester-Günstigerprüfung")
    assert zv_mit > zv_ohne, (zv_mit, zv_ohne)
    print(f"✅ Riester-Kinderzulage senkt den steuerlichen Zusatzvorteil "
         f"korrekt ({zv_ohne} € -> {zv_mit} €)")


# ---------------------------------------------------------------- Rürup
def test_ruerup_basisrente_voll_abzugsfaehig():
    docs = [_lsb(50000, rv_arbeitnehmer=0, kv_beitraege=0, pv_beitraege=0)]
    iv = {"zusammenveranlagung": False,
         "spar": {"ruerup_basisrente": {"aktiv": True, "betrag": 3000.0}}}
    v = berechne_veranlagung(docs, CFG24, iv)
    basis_wert = _step(v, "Vorsorgeaufwendungen Basis")
    assert basis_wert == -3000.0, basis_wert
    assert "Rürup" in [s["text"] for s in v["schritte"]
                       if "Vorsorgeaufwendungen Basis" in s["text"]][0]
    print(f"✅ Rürup/Basisrente fließt voll (ohne 1.900-€-Deckel) in die "
         f"Basis-Vorsorgeaufwendungen ein ({basis_wert} €)")


# ---------------------------------------------------------------- Rente
def test_besteuerungsanteil_kohorten():
    assert besteuerungsanteil_prozent(2005, CFG24) == 50.0
    assert besteuerungsanteil_prozent(2020, CFG24) == 80.0
    assert besteuerungsanteil_prozent(2024, CFG24) == 83.0
    assert besteuerungsanteil_prozent(2025, CFG24) == 83.5
    assert besteuerungsanteil_prozent(2058, CFG24) == 100.0
    assert besteuerungsanteil_prozent(2100, CFG24) == 100.0  # Deckel
    print("✅ Besteuerungsanteil-Kohortentabelle korrekt (2005=50%, "
         "2020=80%, 2024=83%, 2025=83,5%, 2058=100%)")


def test_rentenanteil_steuerpflichtig_berechnung():
    r = rentenanteil_steuerpflichtig(24000, 2024, CFG24)
    assert r["steuerpflichtiger_anteil"] == round(24000 * 0.83, 2)
    assert r["steuerfreier_anteil"] == round(24000 * 0.17, 2)


def test_rente_fliesst_in_veranlagung_ein():
    docs = [_lsb(50000),
           {"kategorie": "rentenbezugsmitteilung", "inhaber": "P1",
            "dateiname": "rente.pdf", "betrag_eur": 12000,
            "zuordnungs_historie": [{}],
            "extrahierte_daten": {"jahresbetrag_rente": 12000,
                                 "rentenbeginn_jahr": 2020}}]
    iv = {"zusammenveranlagung": False}
    v = berechne_veranlagung(docs, CFG24, iv)
    rente_wert = _step(v, "+ Rente P1")
    assert rente_wert == round(12000 * 0.80, 2) == 9600.0, rente_wert
    print(f"✅ Rentenbezugsmitteilung fließt mit dem korrekten "
         f"Besteuerungsanteil in die Veranlagung ein ({rente_wert} €)")


def test_rente_ohne_rentenbeginn_jahr_konservativ_100_prozent():
    docs = [_lsb(50000),
           {"kategorie": "rentenbezugsmitteilung", "inhaber": "P1",
            "dateiname": "rente_unklar.pdf", "betrag_eur": 10000,
            "zuordnungs_historie": [{}],
            "extrahierte_daten": {"jahresbetrag_rente": 10000}}]
    iv = {"zusammenveranlagung": False}
    v = berechne_veranlagung(docs, CFG24, iv)
    rente_wert = _step(v, "+ Rente P1")
    assert rente_wert == 10000.0, rente_wert
    assert any("Rentenbeginn-Jahr" in w for w in v["warnhinweise"])
    print("✅ Fehlendes Rentenbeginn-Jahr führt konservativ zu 100 % "
         "Besteuerungsanteil + Warnhinweis (keine Unterschätzung)")


# ---------------------------------------------------------------- Export
def test_export_enthaelt_neue_bloecke():
    docs = [_lsb(50000),
           {"kategorie": "rentenbezugsmitteilung", "inhaber": "P1",
            "dateiname": "rente.pdf", "betrag_eur": 12000,
            "zuordnungs_historie": [{}],
            "extrahierte_daten": {"jahresbetrag_rente": 12000,
                                 "rentenbeginn_jahr": 2020}}]
    iv = {"zusammenveranlagung": False, "gdb_P1": 50,
         "pflegegrad_angehoeriger": 3, "riester_beitrag_P1": 2100,
         "riester_kinder_ab_2008": 1,
         "personen": {"P1": "Test", "P2": "Partner"}}
    s = build_summary(docs, CFG24, iv)
    assert "R" in s["anlagen"]
    assert "AV" in s["anlagen"]
    assert "Behinderung, Pflege & Unterhalt" in s["anlagen"]
    md = render_elster_help(s, erklaeren=True)
    for marker in ("Anlage R", "Anlage AV", "Behinderung, Pflege & Unterhalt",
                  "Besteuerungsanteil", "Günstigerprüfung"):
        assert marker in md, f"'{marker}' fehlt im Markdown-Export"
    print("✅ ELSTER-Export (JSON + Markdown) enthält Anlage R, Anlage AV "
         "und den Behinderten-/Pflege-/Unterhalt-Block")


if __name__ == "__main__":
    test_kategorie_sync()
    test_zumutbare_belastung_dreistufig()
    test_agb_krankheitskosten_nutzt_echte_zumutbare_belastung()
    test_behinderten_pauschbetrag_stufen()
    test_behinderten_pauschbetrag_hilflos_blind()
    test_pflege_pauschbetrag()
    test_unterhalt_33a_kuerzung_durch_eigene_einkuenfte()
    test_pauschbetraege_wirken_ohne_kuerzung_um_zumutbare_belastung()
    test_riester_zusatzvorteil_bei_hohem_grenzsteuersatz()
    test_riester_bleibt_bei_zulage_wenn_guenstiger()
    test_riester_kinderzulage_fliesst_ein()
    test_ruerup_basisrente_voll_abzugsfaehig()
    test_besteuerungsanteil_kohorten()
    test_rentenanteil_steuerpflichtig_berechnung()
    test_rente_fliesst_in_veranlagung_ein()
    test_rente_ohne_rentenbeginn_jahr_konservativ_100_prozent()
    test_export_enthaelt_neue_bloecke()
    print("🎉 Alle Tests für die neuen Anlagen (agB, § 33b/33a, AV, R, "
         "Rürup) bestanden.")
