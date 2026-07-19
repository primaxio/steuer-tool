# Tests für die zweite Audit-Runde ("alles aufräumen und fixen"):
# M1 Verlustvortrag-Verrechnung, M4 eToro-Zahlenparsing, M8 Übergangs-
# beihilfe-Lohnsteuer, M2 Vorsorgeaufwand-Höchstbetrag, Fünftelregelung,
# Günstigerprüfung KAP. Aufruf: python tests/test_audit_nachbesserungen.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.crypto_parsers import _clean_num, _clean_num_signed
from core.elster_export import build_summary
from core.tax_config import get_config
from core.veranlagung import berechne_veranlagung

CFG24 = get_config(2024)


def test_clean_num_unveraendert_fuer_bestehende_aufrufer():
    # _clean_num MUSS exakt wie vorher abs()-Werte liefern – parse_etoro/
    # parse_coinbase verlassen sich für Menge/Gebühren/Investitionsbetrag
    # darauf, das darf durch den M4-Fix nicht brechen.
    assert _clean_num("1.234,56") == 1234.56   # de: Punkt=Tausender
    assert _clean_num("1,234.56") == 1234.56   # en: Komma=Tausender
    assert _clean_num("-45,67") == 45.67       # weiterhin abs()
    assert _clean_num(None) == 0.0
    print("✅ _clean_num() unverändert (abs, de+en Format)")


def test_clean_num_signed_erhaelt_vorzeichen():
    assert _clean_num_signed("-45,67") == -45.67
    assert _clean_num_signed("45,67") == 45.67
    assert _clean_num_signed("-1,234.56") == -1234.56   # en Tausender, Verlust
    assert _clean_num_signed("-1.234,56") == -1234.56   # de Tausender, Verlust
    assert _clean_num_signed(-906.49) == -906.49        # schon float
    assert _clean_num_signed(906.49) == 906.49
    print("✅ _clean_num_signed() erhält das Vorzeichen (Verluste bleiben negativ)")


def _step(v, needle):
    return next(s for s in v["schritte"] if needle in s["text"])


def test_verlustvortrag_23_wird_verrechnet():
    docs = [{
        "dateiname": "lsb.pdf", "kategorie": "lohnsteuerbescheinigung_zivil",
        "inhaber": "P1",
        "extrahierte_daten": {"bruttoarbeitslohn": 40000, "lohnsteuer": 6000},
    }]
    interview = {
        "zusammenveranlagung": False, "verlustvortrag_23": 300.0,
        "_crypto": {"pro_person": {"P1": {
            "steuerpflichtiger_betrag": 2000.0,
            "rewards_steuerpflichtig": 0.0}}},
    }
    v = berechne_veranlagung(docs, CFG24, interview)
    brutto_step = _step(v, "Krypto-Gewinn § 23 (vor Verlustvortrag)")
    assert brutto_step["wert"] == 2000.0, brutto_step
    vortrag_step = _step(v, "Verlustvortrag § 23 aus Vorjahren verrechnet")
    assert vortrag_step["wert"] == -300.0, vortrag_step
    summe_step = _step(v, "= Summe der Einkünfte")
    # 40000 - 1230 (WK-Pauschbetrag) + (2000 - 300)
    erwartet = 40000 - CFG24["arbeitnehmer_pauschbetrag"] + 1700
    assert summe_step["wert"] == erwartet, summe_step
    print("✅ Verlustvortrag § 23 mindert den steuerpflichtigen "
          "Krypto-Gewinn korrekt (2000 € − 300 € = 1700 €)")


def test_verlustvortrag_23_deckelt_bei_null_kein_negativer_gewinn():
    interview = {
        "zusammenveranlagung": False, "verlustvortrag_23": 5000.0,
        "_crypto": {"pro_person": {"P1": {
            "steuerpflichtiger_betrag": 2000.0,
            "rewards_steuerpflichtig": 0.0}}},
    }
    v = berechne_veranlagung([], CFG24, interview)
    vortrag_step = _step(v, "Verlustvortrag § 23 aus Vorjahren verrechnet")
    assert vortrag_step["wert"] == -2000.0, \
        "Verlustvortrag darf den Gewinn nur bis 0 mindern, nicht negativ machen"
    assert any("bleiben nach Verrechnung für Folgejahre vortragsfähig" in w
              for w in v["warnhinweise"])
    print("✅ Verlustvortrag wird bei Überschuss korrekt gedeckelt und "
          "Restbetrag als weiterhin vortragsfähig gemeldet")


def test_verlustvortrag_23_verrechnet_nicht_mit_rewards():
    interview = {
        "zusammenveranlagung": False, "verlustvortrag_23": 1000.0,
        "_crypto": {"pro_person": {"P1": {
            "steuerpflichtiger_betrag": 0.0,
            "rewards_steuerpflichtig": 500.0}}},
    }
    v = berechne_veranlagung([], CFG24, interview)
    rewards_step = _step(v, "Rewards/Staking (§ 22 Nr. 3)")
    assert rewards_step["wert"] == 500.0, \
        "§ 23-Verlustvortrag darf NICHT gegen § 22 Nr. 3-Rewards verrechnet werden"
    print("✅ Verlustvortrag § 23 bleibt auf § 23-Gewinne beschränkt "
          "(keine Verrechnung mit Rewards)")


def test_verlustvortrag_kap_mindert_erstattung():
    docs = [{
        "dateiname": "bank.pdf", "kategorie": "steuerbescheinigung_bank",
        "inhaber": "P1",
        "extrahierte_daten": {
            "kapitalertraege_zeile7": 1500.0,
            "in_anspruch_genommener_freistellungsauftrag": 0.0},
    }]
    ohne_vortrag = berechne_veranlagung(
        docs, CFG24, {"zusammenveranlagung": False})
    mit_vortrag = berechne_veranlagung(docs, CFG24, {
        "zusammenveranlagung": False, "verlustvortrag_kap_aktien": 1500.0})
    erstattung_ohne = next(
        (s["wert"] for s in ohne_vortrag["schritte"]
         if "Rückholbare Abgeltungsteuer" in s["text"]), 0.0)
    erstattung_mit = next(
        (s["wert"] for s in mit_vortrag["schritte"]
         if "Rückholbare Abgeltungsteuer" in s["text"]), 0.0)
    assert erstattung_ohne > 0, "Ohne Vortrag sollte es Erstattung geben"
    assert erstattung_mit == 0, \
        f"Voller Verlustvortrag sollte Erstattungspotenzial auf 0 senken: {erstattung_mit}"
    print(f"✅ Verlustvortrag KAP mindert Erstattungspotenzial "
          f"({erstattung_ohne} € → {erstattung_mit} €)")


def test_uebergangsbeihilfe_lohnsteuer_wird_angerechnet():
    docs = [{
        "dateiname": "beihilfe.pdf", "kategorie": "uebergangsbeihilfe",
        "inhaber": "P1", "betrag_eur": 15000.0,
        "extrahierte_daten": {"lohnsteuer": 4000.0, "soli": 100.0,
                              "kirchensteuer": 50.0},
    }]
    interview = {"zusammenveranlagung": False}
    v = berechne_veranlagung(docs, CFG24, interview)
    gezahlt_step = _step(v, "Bereits gezahlte Lohnsteuer")
    assert gezahlt_step["wert"] == 4000.0, gezahlt_step
    assert v["gezahlt_gesamt"] >= 4000.0 + 100.0 + 50.0

    summary = build_summary(docs, CFG24, interview)
    ub = summary["anlagen"]["N"]["uebergangsbeihilfe"][0]
    assert ub["lohnsteuer"] == 4000.0 and ub["soli"] == 100.0
    print("✅ Übergangsbeihilfe: einbehaltene Lohnsteuer/Soli/KiSt fließen "
          "in 'bereits gezahlt' ein und erscheinen im Export")


def test_fuenftelregelung_wird_in_veranlagung_automatisch_gewaehlt():
    docs = [{
        "dateiname": "lsb.pdf", "kategorie": "lohnsteuerbescheinigung_zivil",
        "inhaber": "P1",
        "extrahierte_daten": {"bruttoarbeitslohn": 20000, "lohnsteuer": 2000},
    }, {
        "dateiname": "beihilfe.pdf", "kategorie": "uebergangsbeihilfe",
        "inhaber": "P1", "betrag_eur": 15000.0,
    }]
    interview = {"zusammenveranlagung": False}
    v = berechne_veranlagung(docs, CFG24, interview)
    tarif_step = _step(v, "Tarifliche Einkommensteuer")
    assert "Fünftelregelung" in tarif_step["text"], tarif_step
    assert any("Fünftelregelung auf die Übergangsbeihilfe angewendet" in w
              for w in v["warnhinweise"])

    # Ohne Beihilfe darf natürlich keine Fünftelregelung-Zeile auftauchen.
    v_ohne = berechne_veranlagung(docs[:1], CFG24, interview)
    tarif_step_ohne = _step(v_ohne, "Tarifliche Einkommensteuer")
    assert "Fünftelregelung" not in tarif_step_ohne["text"]
    print("✅ berechne_veranlagung wendet die Fünftelregelung automatisch "
          "an, wenn eine Übergangsbeihilfe vorliegt und es günstiger ist")


def test_vorsorge_hoechstbetrag_kv_pv_ueber_deckel_keine_zusatzwirkung():
    docs = [{
        "dateiname": "lsb.pdf", "kategorie": "lohnsteuerbescheinigung_zivil",
        "inhaber": "P1",
        "extrahierte_daten": {"bruttoarbeitslohn": 40000, "lohnsteuer": 6000,
                              "kv_beitraege": 3000.0, "pv_beitraege": 400.0},
    }, {
        "dateiname": "haftpflicht.pdf", "kategorie": "vorsorge_versicherung",
        "inhaber": "P1", "betrag_eur": 200.0,
    }]
    interview = {"zusammenveranlagung": False}
    v = berechne_veranlagung(docs, CFG24, interview)
    # KV+PV = 3400 € > Höchstbetrag 1.900 € -> sonstige Vorsorge (Haftpflicht)
    # wirkt sich NICHT zusätzlich aus (Normalfall bei gesetzl. KV).
    assert not any("zusätzlich wirksame sonstige" in s["text"]
                  for s in v["schritte"])
    assert any("bereits ausgeschöpft" in w for w in v["warnhinweise"])
    print("✅ Vorsorge-Höchstbetrag: KV/PV über Deckel -> Zusatzversicherung "
          "wirkt sich korrekt NICHT aus")


def test_vorsorge_hoechstbetrag_niedrige_kv_pv_zusatzwirkung():
    docs = [{
        "dateiname": "lsb.pdf", "kategorie": "lohnsteuerbescheinigung_zivil",
        "inhaber": "P1",
        "extrahierte_daten": {"bruttoarbeitslohn": 20000, "lohnsteuer": 2000,
                              "kv_beitraege": 800.0, "pv_beitraege": 100.0},
    }, {
        "dateiname": "haftpflicht.pdf", "kategorie": "vorsorge_versicherung",
        "inhaber": "P1", "betrag_eur": 500.0,
    }]
    interview = {"zusammenveranlagung": False}
    v = berechne_veranlagung(docs, CFG24, interview)
    # KV+PV = 900 € < Höchstbetrag 1.900 € -> bis zu 1.000 € Restraum,
    # die volle Zusatzversicherung (500 €) sollte sich damit auswirken.
    sonstige_step = next(
        (s for s in v["schritte"] if "zusätzlich wirksame sonstige" in s["text"]),
        None)
    assert sonstige_step is not None, v["schritte"]
    assert sonstige_step["wert"] == -500.0, sonstige_step
    print("✅ Vorsorge-Höchstbetrag: niedrige KV/PV -> Zusatzversicherung "
          "wirkt sich bis zum Höchstbetrag korrekt aus")


def test_etoro_verlust_mit_tausendertrennzeichen_parst_korrekt():
    # VOR dem Fix: "-1.234,56" (de: Tausenderpunkt) hätte die alte
    # .replace(",", ".")-Logik zu "-1.234.56" verstümmelt -> ValueError,
    # der komplette eToro-Import wäre gecrasht.
    import io as _io
    import pandas as pd
    from core.crypto_parsers import parse_etoro

    df = pd.DataFrame([{
        "Action": "Buy BTC/USD", "Type": "crypto", "Leverage": 1,
        "Open Date": "01/01/2024 10:00:00", "Close Date": "15/03/2024 10:00:00",
        "Amount": "5000", "Profit": "-1.234,56", "Spread": 0, "Rollover": 0,
        "Units": "0.1",
    }])
    buf = _io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Closed Positions", index=False)
    disposals, cfd_hinweise, warn = parse_etoro(
        buf.getvalue(), "P1", fx=None, fallback_rate=1.08)
    assert len(disposals) == 1, disposals
    d = disposals[0]
    assert d.gewinn < 0, f"Verlust muss negativ bleiben, war {d.gewinn}"
    erwarteter_verlust_eur = round(-1234.56 / 1.08, 2)
    assert abs(d.gewinn - erwarteter_verlust_eur) < 0.5, \
        f"Erwartet ≈{erwarteter_verlust_eur} €, war {d.gewinn} €"
    print(f"✅ eToro-Verlust mit Tausendertrennzeichen korrekt geparst "
          f"(Gewinn={d.gewinn} €, negativ wie erwartet)")


def _kap_docs(brutto, kap_ertraege):
    return [{
        "dateiname": "lsb.pdf", "kategorie": "lohnsteuerbescheinigung_zivil",
        "inhaber": "P1",
        "extrahierte_daten": {"bruttoarbeitslohn": brutto, "lohnsteuer": 0},
    }, {
        "dateiname": "bank.pdf", "kategorie": "steuerbescheinigung_bank",
        "inhaber": "P1",
        "extrahierte_daten": {
            "kapitalertraege_zeile7": kap_ertraege,
            "in_anspruch_genommener_freistellungsauftrag": 0.0},
    }]


def test_guenstigerpruefung_kap_niedriges_einkommen():
    docs = _kap_docs(15000, 5000.0)
    v = berechne_veranlagung(docs, CFG24, {"zusammenveranlagung": False})
    guenstiger_step = _step(v, "Günstigerprüfung KAP")
    assert guenstiger_step["wert"] > 0, guenstiger_step
    assert any("Günstigerprüfung lohnt sich" in w for w in v["warnhinweise"])
    print(f"✅ Günstigerprüfung KAP greift bei niedrigem Einkommen "
          f"(+{guenstiger_step['wert']} €)")


def test_guenstigerpruefung_kap_hohes_einkommen_kein_vorteil():
    docs = _kap_docs(90000, 5000.0)
    v = berechne_veranlagung(docs, CFG24, {"zusammenveranlagung": False})
    assert not any("Günstigerprüfung KAP" in s["text"] for s in v["schritte"]), \
        "Bei > 25 % Grenzsteuersatz darf keine Günstigerprüfung-Zeile erscheinen"
    print("✅ Günstigerprüfung KAP bleibt bei hohem Einkommen korrekt aus")


def test_guenstigerpruefung_kap_abschaltbar():
    docs = _kap_docs(15000, 5000.0)
    v = berechne_veranlagung(docs, CFG24, {
        "zusammenveranlagung": False, "guenstigerpruefung": False})
    assert not any("Günstigerprüfung KAP" in s["text"] for s in v["schritte"])
    print("✅ Günstigerprüfung KAP respektiert den Fragebogen-Haken (aus)")


if __name__ == "__main__":
    test_verlustvortrag_23_wird_verrechnet()
    test_verlustvortrag_23_deckelt_bei_null_kein_negativer_gewinn()
    test_verlustvortrag_23_verrechnet_nicht_mit_rewards()
    test_verlustvortrag_kap_mindert_erstattung()
    test_uebergangsbeihilfe_lohnsteuer_wird_angerechnet()
    test_fuenftelregelung_wird_in_veranlagung_automatisch_gewaehlt()
    test_guenstigerpruefung_kap_niedriges_einkommen()
    test_guenstigerpruefung_kap_hohes_einkommen_kein_vorteil()
    test_guenstigerpruefung_kap_abschaltbar()
    test_clean_num_unveraendert_fuer_bestehende_aufrufer()
    test_clean_num_signed_erhaelt_vorzeichen()
    test_vorsorge_hoechstbetrag_kv_pv_ueber_deckel_keine_zusatzwirkung()
    test_vorsorge_hoechstbetrag_niedrige_kv_pv_zusatzwirkung()
    test_etoro_verlust_mit_tausendertrennzeichen_parst_korrekt()
    print("🎉 Bisherige Audit-Nachbesserungs-Tests bestanden.")
