"""
Projektstand speichern/laden (JSON) – Streamlit-Session ist flüchtig,
darum kompletter Zustand als Datei: Dokumente, Fragebogen, Stammdaten,
Krypto-Transaktionen und eToro-Positionen.
"""

import json
from dataclasses import asdict
from datetime import datetime

from .crypto import Disposal, NormTx

VERSION = 2


def save_state(ss, jahr: int, personen: dict) -> str:
    iv = {k: v for k, v in ss.interview.items() if k != "_crypto"}
    data = {
        "version": VERSION,
        "gespeichert": datetime.now().isoformat(timespec="seconds"),
        "jahr": jahr,
        "personen": personen,
        "docs": ss.docs,
        "interview": iv,
        "crypto_txs": [
            {**asdict(t), "ts": t.ts.isoformat()} for t in ss.crypto_txs],
        "crypto_matched": [
            {**asdict(d), "kauf_ts": d.kauf_ts.isoformat(),
             "verkauf_ts": d.verkauf_ts.isoformat()}
            for d in ss.crypto_matched],
        "crypto_files": sorted(ss.crypto_files),
        "crypto_cfd_hinweise": ss.crypto_cfd_hinweise,
        "crypto_import_warn": ss.crypto_import_warn,
        "analyzed_files": sorted(ss.analyzed_files),
    }
    return json.dumps(data, ensure_ascii=False, indent=2)


def load_state(ss, raw: bytes | str) -> dict:
    data = json.loads(raw)
    ss.docs = data.get("docs", [])
    ss.interview = data.get("interview", {})
    ss.analyzed_files = set(data.get("analyzed_files", []))
    ss.crypto_files = set(data.get("crypto_files", []))
    ss.crypto_cfd_hinweise = data.get("crypto_cfd_hinweise", [])
    ss.crypto_import_warn = data.get("crypto_import_warn", [])
    ss.crypto_txs = [
        NormTx(**{**t, "ts": datetime.fromisoformat(t["ts"])})
        for t in data.get("crypto_txs", [])]
    ss.crypto_matched = [
        Disposal(**{**d, "kauf_ts": datetime.fromisoformat(d["kauf_ts"]),
                    "verkauf_ts": datetime.fromisoformat(d["verkauf_ts"])})
        for d in data.get("crypto_matched", [])]
    ss.crypto_results = None
    # Beim nächsten Rerun Widget-State an die geladenen Daten angleichen
    # (Sidebar-Namen, "Gehört zu"-Auswahl usw.) – siehe Sync-Block in app.py.
    ss["_widget_sync"] = True
    return data
