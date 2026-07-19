# Mini-Smoketest für die Chat-Dokumenten-Triage (Teil 3):
# klaerungsbedarf-Erkennung, Zuordnungs-Historie, Übernahme eines
# Chat-Vorschlags, "Herkunft der Werte"-Anhang, persist.py-Rundreise.
# Aufruf: python tests/test_klaerung.py (kein Framework nötig).
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class _FakeSessionState(dict):
    """Minimaler Ersatz für st.session_state: erlaubt sowohl
    Attribut- (ss.docs) als auch Item-Zugriff (ss["_widget_sync"])."""
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        self[name] = value

from core.dokumente_ui import _historie_eintrag, _uebernehme_chat_vorschlag
from core.elster_export import build_summary, render_elster_help
from core.persist import load_state, save_state
from core.tax_config import get_config
from core.vision import _berechne_klaerungsbedarf

CFG = get_config(2024)


def _doc(**overrides):
    d = {
        "dateiname": "unklar.pdf", "kategorie": "sonstiges", "confidence": 0.4,
        "dokumenttyp": "Unklares Dokument", "aussteller": None, "datum": None,
        "steuerjahr": None, "betrag_eur": None, "extrahierte_daten": {},
        "rueckfragen": ["Wem gehört dieser Beleg?"], "hinweise": [],
        "klaerungsbedarf": True, "zuordnungs_historie": [{
            "zeitpunkt": "2024-01-01T10:00:00", "aktion": "automatische Kategorisierung",
            "von": None, "nach": "sonstiges", "quelle": "automatisch",
            "begruendung": "Claude Vision, Confidence 40%"}],
    }
    d.update(overrides)
    return d


def test_uebernahme_setzt_alle_felder_und_historie():
    d = _doc()
    vorschlag = {
        "kategorie": "spende", "inhaber": "P2", "betrieb": None,
        "steuerjahr": 2024, "betrag_eur": 75.0,
        "begruendung": "Zuwendungsbestätigung eines eingetragenen Vereins.",
    }
    _uebernehme_chat_vorschlag(d, vorschlag)
    assert d["kategorie"] == "spende"
    assert d["inhaber"] == "P2"
    assert d["steuerjahr_zuordnung"] == 2024
    assert d["betrag_eur"] == 75.0
    assert d["klaerungsbedarf"] is False
    assert any("Zuwendungsbestätigung" in h for h in d["hinweise"])
    assert len(d["zuordnungs_historie"]) == 2
    letzter = d["zuordnungs_historie"][-1]
    assert letzter["quelle"] == "chat"
    assert letzter["von"] == "sonstiges" and letzter["nach"] == "spende"
    print("✅ Chat-Vorschlag setzt Kategorie/Inhaber/Jahr/Betrag, "
          "klaerungsbedarf=False, Hinweis + Historie protokolliert")


def test_manuelle_korrektur_wird_protokolliert():
    d = _doc(kategorie="werbungskosten", zuordnungs_historie=[{
        "zeitpunkt": "t0", "aktion": "automatische Kategorisierung",
        "von": None, "nach": "werbungskosten", "quelle": "automatisch",
        "begruendung": ""}])
    _historie_eintrag(d, "Kategorie manuell korrigiert",
                      "werbungskosten", "spende", "manuell")
    assert len(d["zuordnungs_historie"]) == 2
    assert d["zuordnungs_historie"][-1]["quelle"] == "manuell"
    print("✅ Manuelle Kategorie-Korrektur wird in der Historie protokolliert")


def test_herkunft_der_werte_im_export():
    d1 = _doc(dateiname="geklaert.pdf")
    _uebernehme_chat_vorschlag(d1, {
        "kategorie": "spende", "inhaber": "P1", "steuerjahr": 2024,
        "betrag_eur": 50.0, "begruendung": "Vereinsspende laut Chat."})
    d2 = _doc(dateiname="nie_angefasst.pdf", kategorie="spende",
             confidence=0.95, datum="01.01.2024", betrag_eur=10.0,
             rueckfragen=[], klaerungsbedarf=False)
    # d2 hat nur den initialen Automatik-Eintrag -> darf NICHT im Anhang stehen
    summary = build_summary([d1, d2], CFG, {"zusammenveranlagung": False})
    dateien_im_anhang = [h["dateiname"] for h in summary["dokumente_historie"]]
    assert "geklaert.pdf" in dateien_im_anhang
    assert "nie_angefasst.pdf" not in dateien_im_anhang

    md = render_elster_help(summary)
    assert "Anhang: Herkunft der Werte" in md
    anhang = md.split("Anhang: Herkunft der Werte", 1)[1]
    assert "geklaert.pdf" in anhang
    assert "💬 Chat-Klärung" in anhang
    assert "nie_angefasst.pdf" not in anhang, \
        "nie_angefasst.pdf hat nur den Automatik-Eintrag, gehört NICHT in den Anhang"
    print("✅ 'Herkunft der Werte' zeigt nur Belege mit echter Änderungshistorie")


def test_persist_rundreise_erhaelt_historie():
    d = _doc()
    _uebernehme_chat_vorschlag(d, {
        "kategorie": "krankheitskosten", "inhaber": "P1", "steuerjahr": 2024,
        "betrag_eur": 120.0, "begruendung": "Arztrechnung laut Chat."})
    ss = _FakeSessionState(
        interview={}, docs=[d], crypto_txs=[], crypto_matched=[],
        crypto_files=set(), crypto_cfd_hinweise=[], crypto_import_warn=[],
        analyzed_files={"unklar.pdf"})
    raw = save_state(ss, 2024, {"P1": "Andre", "P2": "Ehepartnerin"})

    ss2 = _FakeSessionState()
    load_state(ss2, raw)
    assert ss2.docs[0]["zuordnungs_historie"][-1]["quelle"] == "chat"
    assert ss2.docs[0]["kategorie"] == "krankheitskosten"
    print("✅ persist.py speichert/lädt zuordnungs_historie verlustfrei "
          "(keine Sonderbehandlung nötig, docs sind bereits reine Dicts)")


def test_klaerungsbedarf_end_to_end_realistisch():
    # Dokument mit gutem Ergebnis -> keine Klärung nötig
    gut = {"confidence": 0.9, "kategorie": "krypto_report", "betrag_eur": 500.0,
          "datum": "01.03.2024", "rueckfragen": []}
    assert _berechne_klaerungsbedarf(gut) is False
    print("✅ Klärungsbedarf end-to-end konsistent mit gutem Analyseergebnis")


if __name__ == "__main__":
    test_uebernahme_setzt_alle_felder_und_historie()
    test_manuelle_korrektur_wird_protokolliert()
    test_herkunft_der_werte_im_export()
    test_persist_rundreise_erhaelt_historie()
    test_klaerungsbedarf_end_to_end_realistisch()
    print("🎉 Alle Klärungs-Chat-Tests bestanden.")
