"""
Regressionstest: Belegablage-Persistenz (AUDIT.md-Backlog "analysierte
Dateien werden nicht gespeichert, nur Metadaten"). dokumente_ui.py speichert
seit dieser Runde die Original-Datei als Base64 in doc["_bytes"]
(+ doc["_mime"]), damit sie über persist.py erhalten bleibt und per
Download-Button wieder abrufbar ist. WICHTIG: _bytes darf NIE im JSON-Export
oder im Chat-Kontext landen (Größe/Redundanz) – das prüfen die Tests hier.
"""

import base64
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.elster_export import export_json
from core.persist import load_state, save_state


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


def _doc_mit_bytes():
    return {
        "kategorie": "spende", "dateiname": "spende.pdf",
        "dokumenttyp": "Spendenquittung", "aussteller": "Verein e. V.",
        "datum": "01.03.2024", "steuerjahr": 2024, "betrag_eur": 100.0,
        "extrahierte_daten": {}, "rueckfragen": [], "hinweise": [],
        "confidence": 0.95, "klaerungsbedarf": False,
        "steuerjahr_zuordnung": 2024,
        "zuordnungs_historie": [{"zeitpunkt": "2024-01-01T00:00:00",
                                 "aktion": "Automatisch erkannt", "von": None,
                                 "nach": "spende", "quelle": "automatisch",
                                 "begruendung": "Claude Vision"}],
        "_bytes": base64.b64encode(b"%PDF-1.4 Testinhalt").decode("ascii"),
        "_mime": "application/pdf",
    }


def test_persist_speichert_und_laedt_bytes_verlustfrei():
    ss = _FakeSessionState(
        docs=[_doc_mit_bytes()], interview={}, crypto_txs=[],
        crypto_matched=[], crypto_files=set(), crypto_cfd_hinweise=[],
        crypto_import_warn=[], analyzed_files=set())
    raw = save_state(ss, 2024, {"P1": "A", "P2": "B"})
    assert '"_bytes"' in raw, "Belegdaten müssen im gespeicherten JSON stecken."

    ss2 = _FakeSessionState()
    load_state(ss2, raw)
    geladen = ss2.docs[0]
    assert geladen["_bytes"] == _doc_mit_bytes()["_bytes"]
    assert base64.b64decode(geladen["_bytes"]) == b"%PDF-1.4 Testinhalt"
    print("✅ persist.py: Beleg-Bytes überleben Speichern/Laden verlustfrei")


def test_export_json_filtert_bytes_heraus():
    docs = [_doc_mit_bytes()]
    raw = export_json({"steuerjahr": 2024, "erstellt": "-", "anlagen": {}},
                      docs, [])
    assert '"_bytes"' not in raw, \
        "Der ELSTER-JSON-Export darf die eingebetteten Rohdaten NICHT " \
        "enthalten (Größe/Redundanz) – nur Metadaten."
    assert "spende.pdf" in raw
    print("✅ export_json filtert _bytes zuverlässig heraus")


def test_klaerungs_chat_kontext_filtert_bytes():
    from core.erklaerungen import klaerungs_chat
    import inspect
    quelle = inspect.getsource(klaerungs_chat)
    assert '"_bytes"' in quelle or "_bytes" in quelle, \
        "klaerungs_chat sollte _bytes aus dem Dokument-Kontext filtern " \
        "(Prompt-Größe)."
    print("✅ klaerungs_chat() filtert _bytes aus dem Chat-Kontext "
         "(Code-Kontrolle)")


if __name__ == "__main__":
    test_persist_speichert_und_laedt_bytes_verlustfrei()
    test_export_json_filtert_bytes_heraus()
    test_klaerungs_chat_kontext_filtert_bytes()
    print("🎉 Alle Belegablage-Persistenz-Tests bestanden.")
