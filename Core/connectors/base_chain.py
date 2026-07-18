"""
Base-Onchain-Connector via Basescan-API (Etherscan-kompatibel).
Liest ETH- und Token-Transfers einer Adresse, erkennt Swaps (gleicher
Tx-Hash mit Token raus + Token rein), bewertet in EUR über den
PreisDienst und rechnet Gas-Gebühren an.

Kostenloser API-Key: basescan.org → My API Keys.
Heuristik-Grenzen (ehrlich): komplexe DeFi-Interaktionen (LPs, Lending,
Multi-Hop) werden als Warnung markiert statt geraten.
"""

from collections import defaultdict
from datetime import datetime

import requests

from ..crypto import NormTx

API = "https://api.basescan.org/api"


def _hole(params: dict, api_key: str) -> list[dict]:
    params = {**params, "apikey": api_key}
    r = requests.get(API, params=params, timeout=30)
    r.raise_for_status()
    j = r.json()
    if str(j.get("status")) != "1" and j.get("message") != "No transactions found":
        raise ValueError(f"Basescan: {j.get('message')} {j.get('result')}")
    return j.get("result") or []


def sync_base(adresse: str, api_key: str, inhaber: str, preisdienst
              ) -> tuple[list[NormTx], list[str]]:
    adresse = adresse.lower().strip()
    warn: list[str] = []

    eth_txs = _hole({"module": "account", "action": "txlist",
                     "address": adresse, "sort": "asc"}, api_key)
    token_txs = _hole({"module": "account", "action": "tokentx",
                       "address": adresse, "sort": "asc"}, api_key)

    # Ereignisse je Tx-Hash bündeln (für Swap-Erkennung)
    je_hash: dict[str, dict] = defaultdict(
        lambda: {"rein": [], "raus": [], "gas_eth": 0.0, "ts": None})

    for tx in eth_txs:
        h = tx["hash"]
        ts = datetime.utcfromtimestamp(int(tx["timeStamp"]))
        je_hash[h]["ts"] = ts
        wert_eth = int(tx.get("value", 0)) / 1e18
        if tx["from"].lower() == adresse:
            je_hash[h]["gas_eth"] = (int(tx.get("gasUsed", 0))
                                     * int(tx.get("gasPrice", 0))) / 1e18
            if wert_eth > 0:
                je_hash[h]["raus"].append(("ETH", wert_eth))
        elif wert_eth > 0:
            je_hash[h]["rein"].append(("ETH", wert_eth))

    for tx in token_txs:
        h = tx["hash"]
        ts = datetime.utcfromtimestamp(int(tx["timeStamp"]))
        je_hash[h]["ts"] = je_hash[h]["ts"] or ts
        menge = int(tx.get("value", 0)) / 10 ** int(tx.get("tokenDecimal", 18))
        sym = (tx.get("tokenSymbol") or "?").upper()
        if menge <= 0:
            continue
        richtung = "raus" if tx["from"].lower() == adresse else "rein"
        je_hash[h][richtung].append((sym, menge))

    txs: list[NormTx] = []
    for h, ev in je_hash.items():
        ts = ev["ts"]
        if ts is None:
            continue
        gas_eur = preisdienst.bewerte("ETH", ev["gas_eth"], ts) or 0.0 \
            if ev["gas_eth"] else 0.0

        def wert(paare):
            summe, ok = 0.0, True
            for sym, menge in paare:
                w = preisdienst.bewerte(sym, menge, ts)
                if w is None:
                    ok = False
                else:
                    summe += w
            return summe, ok

        if ev["raus"] and ev["rein"]:                       # SWAP
            wert_raus, ok1 = wert(ev["raus"])
            wert_rein, ok2 = wert(ev["rein"])
            # Marktwert der Gegenleistung als Erlös/Kosten (konservativ:
            # beide Seiten gleich bewerten, bevorzugt die bewertbare Seite)
            wert_tausch = wert_raus if ok1 else wert_rein
            if not (ok1 or ok2):
                warn.append(f"Swap {h[:10]}… am {ts:%d.%m.%Y}: keine Kurse – "
                            "manuell bewerten!")
            for sym, menge in ev["raus"]:
                txs.append(NormTx(ts, sym, "verkauf", menge,
                                  wert_tausch / max(1, len(ev["raus"])),
                                  gas_eur, "Base", inhaber, f"Swap {h[:10]}"))
                gas_eur = 0.0                               # Gas nur einmal
            for sym, menge in ev["rein"]:
                txs.append(NormTx(ts, sym, "kauf", menge,
                                  wert_tausch / max(1, len(ev["rein"])),
                                  0.0, "Base", inhaber, f"Swap {h[:10]}"))
            if len(ev["raus"]) > 1 or len(ev["rein"]) > 1:
                warn.append(f"Mehrbein-Swap {h[:10]}… ({ts:%d.%m.%Y}): "
                            "vermutlich DeFi (LP?) – bitte prüfen!")
        elif ev["rein"]:                                    # Eingang
            for sym, menge in ev["rein"]:
                w = preisdienst.bewerte(sym, menge, ts) or 0.0
                txs.append(NormTx(ts, sym, "transfer_in", menge, w, 0.0,
                                  "Base", inhaber, f"Eingang {h[:10]}"))
            warn.append(f"Eingang {h[:10]}… ({ts:%d.%m.%Y}): Herkunft "
                        "klären – eigener Transfer (Haltefrist läuft "
                        "weiter) oder Airdrop/Zahlung (steuerlich relevant)?")
        elif ev["raus"]:                                    # Ausgang
            for sym, menge in ev["raus"]:
                w = preisdienst.bewerte(sym, menge, ts) or 0.0
                txs.append(NormTx(ts, sym, "transfer_out", menge, w, gas_eur,
                                  "Base", inhaber, f"Ausgang {h[:10]}"))
                gas_eur = 0.0
    if preisdienst.fehlend:
        warn.append("Ohne Kursdaten (SYMBOL_IDS in connectors/preise.py "
                    "erweitern): " + ", ".join(sorted(preisdienst.fehlend)))
    warn.append(f"Base-Sync: {len(je_hash)} Transaktionen verarbeitet. "
                "DeFi-Spezialfälle (Lending, LPs, NFTs) werden nur markiert, "
                "nicht steuerlich interpretiert.")
    return txs, warn
