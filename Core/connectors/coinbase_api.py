"""
Coinbase-API-Connector (CDP-API-Key, JWT ES256).
Liest Konten + Transaktionen (v2-API) und mappt sie auf NormTx.

WICHTIG:
- API-Key in der Coinbase Developer Platform mit NUR-LESE-Rechten
  ("wallet:accounts:read", "wallet:transactions:read") anlegen!
- Gegen die offizielle Doku implementiert – Live-Test per Claude Code
  nötig (Endpunkte/Feldnamen können sich ändern).
"""

import time
from datetime import datetime

import jwt as pyjwt
import requests
from cryptography.hazmat.primitives import serialization

from ..crypto import NormTx

HOST = "api.coinbase.com"


def _bearer(key_name: str, private_key_pem: str, method: str, path: str) -> str:
    key = serialization.load_pem_private_key(
        private_key_pem.encode(), password=None)
    now = int(time.time())
    token = pyjwt.encode(
        {"sub": key_name, "iss": "cdp", "nbf": now, "exp": now + 110,
         "uri": f"{method} {HOST}{path}"},
        key, algorithm="ES256",
        headers={"kid": key_name, "nonce": str(now)})
    return token


def _get(key_name: str, pem: str, path: str) -> dict:
    r = requests.get(
        f"https://{HOST}{path}",
        headers={"Authorization":
                 f"Bearer {_bearer(key_name, pem, 'GET', path.split('?')[0])}"},
        timeout=30)
    r.raise_for_status()
    return r.json()


def _alle_seiten(key_name: str, pem: str, path: str) -> list[dict]:
    daten, next_uri = [], f"{path}?limit=100"
    while next_uri:
        antwort = _get(key_name, pem, next_uri)
        daten += antwort.get("data", [])
        next_uri = (antwort.get("pagination") or {}).get("next_uri")
    return daten


def mappe_transaktion(tx: dict, inhaber: str) -> NormTx | None:
    """Eine Coinbase-v2-Transaktion → NormTx (None = irrelevant)."""
    typ_raw = tx.get("type", "")
    status = tx.get("status", "")
    if status not in ("completed", ""):
        return None
    menge = abs(float(tx.get("amount", {}).get("amount", 0) or 0))
    asset = (tx.get("amount", {}).get("currency") or "").upper()
    nativ = tx.get("native_amount", {})          # Kontowährung (i. d. R. EUR)
    wert = abs(float(nativ.get("amount", 0) or 0))
    if nativ.get("currency") not in ("EUR", None, ""):
        wert = 0.0                               # später über Kurse bewerten
    ts_raw = tx.get("created_at", "")
    try:
        ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00")) \
            .replace(tzinfo=None)
    except ValueError:
        return None
    notiz = (tx.get("details", {}) or {}).get("title", typ_raw)

    if typ_raw in ("buy", "trade") and typ_raw == "buy":
        typ = "kauf"
    elif typ_raw == "sell":
        typ = "verkauf"
    elif typ_raw == "trade":                     # Convert: je Leg eine Tx
        typ = "kauf" if float(tx["amount"]["amount"]) > 0 else "verkauf"
    elif typ_raw in ("staking_reward", "interest", "inflation_reward",
                     "incentives_shared_clawback", "learning_reward"):
        typ = "reward"
    elif typ_raw in ("send",):
        typ = "transfer_out" if float(tx["amount"]["amount"]) < 0 \
            else "transfer_in"
    elif typ_raw in ("receive", "pro_deposit", "exchange_deposit"):
        typ = "transfer_in"
    else:
        return None
    if not asset or menge == 0:
        return None
    return NormTx(ts, asset, typ, menge, wert, 0.0, "Coinbase", inhaber, notiz)


def sync_coinbase(key_name: str, private_key_pem: str, inhaber: str
                  ) -> tuple[list[NormTx], list[str]]:
    """Alle Konten + Transaktionen abrufen → (NormTx-Liste, Warnungen)."""
    warn: list[str] = []
    txs: list[NormTx] = []
    konten = _alle_seiten(key_name, private_key_pem, "/v2/accounts")
    for konto in konten:
        kid = konto.get("id")
        if not kid:
            continue
        for tx in _alle_seiten(key_name, private_key_pem,
                               f"/v2/accounts/{kid}/transactions"):
            n = mappe_transaktion(tx, inhaber)
            if n:
                txs.append(n)
    ohne_wert = [t for t in txs if t.typ in ("kauf", "verkauf", "reward")
                 and t.wert_eur <= 0]
    if ohne_wert:
        warn.append(f"{len(ohne_wert)} Transaktion(en) ohne EUR-Wert – "
                    "werden über historische Kurse (CoinGecko) bewertet.")
    warn.append("Coinbase-Sync: Gebühren stecken bei v2 im EUR-Gesamtwert. "
                "Bitte Stichproben gegen die App prüfen (erster "
                "Claude-Code-Task: Live-Test!).")
    return txs, warn


def bewerte_fehlende(txs: list[NormTx], preisdienst) -> list[str]:
    """EUR-Werte für Txs ohne native EUR-Angabe nachziehen."""
    warn = []
    for t in txs:
        if t.wert_eur <= 0 and t.typ in ("kauf", "verkauf", "reward",
                                         "transfer_in"):
            wert = preisdienst.bewerte(t.asset, t.menge, t.ts)
            if wert is not None:
                t.wert_eur = wert
            elif t.typ != "transfer_in":
                warn.append(f"{t.asset} am {t.ts:%d.%m.%Y}: kein Kurs "
                            "ermittelbar – Wert manuell prüfen!")
    return warn
