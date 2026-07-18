"""
Historische EUR-Tageskurse via CoinGecko (kostenlose API).
Mit Datei-Cache (preise_cache.json), damit Kurse nur einmal geladen werden
und das Rate-Limit (~10–30 Anfragen/Minute) nicht stört.
"""

import json
import time
from datetime import date, datetime
from pathlib import Path

import requests

CACHE_DATEI = Path(__file__).resolve().parent.parent.parent / "preise_cache.json"

# Symbol → CoinGecko-ID (gängige Coins; bei Bedarf erweitern)
SYMBOL_IDS = {
    "BTC": "bitcoin", "ETH": "ethereum", "WETH": "weth", "SOL": "solana",
    "ADA": "cardano", "XRP": "ripple", "DOGE": "dogecoin", "DOT": "polkadot",
    "LTC": "litecoin", "LINK": "chainlink", "AVAX": "avalanche-2",
    "MATIC": "matic-network", "POL": "polygon-ecosystem-token",
    "ATOM": "cosmos", "UNI": "uniswap", "AAVE": "aave", "OP": "optimism",
    "ARB": "arbitrum", "USDC": "usd-coin", "USDT": "tether",
    "DAI": "dai", "SHIB": "shiba-inu", "PEPE": "pepe", "NEAR": "near",
    "SUI": "sui", "TON": "the-open-network", "BNB": "binancecoin",
    "CBETH": "coinbase-wrapped-staked-eth", "AERO": "aerodrome-finance",
}


class PreisDienst:
    def __init__(self, pause_sekunden: float = 1.6):
        self.pause = pause_sekunden
        self.cache: dict[str, float] = {}
        if CACHE_DATEI.exists():
            try:
                self.cache = json.loads(CACHE_DATEI.read_text())
            except json.JSONDecodeError:
                pass
        self.fehlend: set[str] = set()

    def _speichern(self):
        CACHE_DATEI.write_text(json.dumps(self.cache))

    def eur_kurs(self, symbol: str, wann: datetime | date) -> float | None:
        """EUR-Tageskurs (CoinGecko-History). None, wenn nicht ermittelbar."""
        sym = symbol.upper()
        d = wann.date() if isinstance(wann, datetime) else wann
        key = f"{sym}:{d.isoformat()}"
        if key in self.cache:
            return self.cache[key]
        cid = SYMBOL_IDS.get(sym)
        if not cid:
            self.fehlend.add(sym)
            return None
        url = (f"https://api.coingecko.com/api/v3/coins/{cid}/history"
               f"?date={d:%d-%m-%Y}&localization=false")
        try:
            time.sleep(self.pause)
            r = requests.get(url, timeout=20)
            if r.status_code == 429:          # Rate-Limit → einmal warten
                time.sleep(30)
                r = requests.get(url, timeout=20)
            r.raise_for_status()
            preis = (r.json().get("market_data", {})
                     .get("current_price", {}).get("eur"))
            if preis is None:
                self.fehlend.add(sym)
                return None
            self.cache[key] = float(preis)
            self._speichern()
            return float(preis)
        except requests.RequestException:
            self.fehlend.add(sym)
            return None

    def bewerte(self, symbol: str, menge: float,
                wann: datetime) -> float | None:
        kurs = self.eur_kurs(symbol, wann)
        return None if kurs is None else round(menge * kurs, 2)
