"""
Import-Parser für Krypto-Exporte:
- Coinbase Transaktions-CSV (auch Base-Onchain via Coinbase Wallet Export)
- eToro Kontoauszug XLSX ("Closed Positions") inkl. CFD-Erkennung
- Generische CSV/XLSX mit Claude-gestützter Spaltenzuordnung (zukunftssicher
  gegen Formatänderungen der Anbieter)
- EZB-Wechselkurse (eurofxref-hist.csv) für USD→EUR je Handelstag
"""

import io
import json
import re
from datetime import datetime, timedelta

import pandas as pd

from .crypto import NormTx
from .vision import _parse_json  # robuster JSON-Extraktor wiederverwenden

KNOWN_COINS = {"BTC", "ETH", "SOL", "ADA", "XRP", "DOGE", "DOT", "LTC", "LINK",
               "AVAX", "MATIC", "POL", "ATOM", "UNI", "AAVE", "OP", "ARB",
               "USDC", "USDT", "SHIB", "PEPE", "NEAR", "SUI", "TON", "BNB"}


# ------------------------------------------------------------------ FX (EZB)
class FxTable:
    """USD/EUR-Referenzkurse der EZB (eurofxref-hist.csv)."""

    def __init__(self, df: pd.DataFrame | None = None):
        self.rates: dict = {}
        if df is not None:
            df.columns = [c.strip() for c in df.columns]
            for _, row in df.iterrows():
                try:
                    d = pd.to_datetime(row["Date"]).date()
                    self.rates[d] = float(row["USD"])
                except (KeyError, ValueError, TypeError):
                    continue

    @classmethod
    def from_file(cls, file) -> "FxTable":
        return cls(pd.read_csv(file))

    ECB_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.zip"

    @classmethod
    def from_ecb_online(cls, cache_pfad: str = "/tmp/ezb_kurse.csv",
                        max_alter_stunden: float = 24.0) -> "FxTable":
        import io as _io
        import os
        import time
        import zipfile
        import requests
        if os.path.exists(cache_pfad) and \
                time.time() - os.path.getmtime(cache_pfad) < \
                max_alter_stunden * 3600:
            return cls(pd.read_csv(cache_pfad))
        r = requests.get(cls.ECB_URL, timeout=30)
        r.raise_for_status()
        zf = zipfile.ZipFile(_io.BytesIO(r.content))
        name = next(n for n in zf.namelist() if n.endswith(".csv"))
        df = pd.read_csv(zf.open(name))
        df.to_csv(cache_pfad, index=False)
        return cls(df)

    def usd_to_eur(self, amount: float, when: datetime,
                   fallback_rate: float | None = None) -> float:
        d = when.date() if isinstance(when, datetime) else when
        for _ in range(7):  # Wochenende/Feiertag → letzter Bankarbeitstag
            if d in self.rates:
                return amount / self.rates[d]
            d -= timedelta(days=1)
        if fallback_rate:
            return amount / fallback_rate
        raise ValueError(f"Kein USD-Kurs für {when:%d.%m.%Y} – EZB-Datei "
                         "hochladen oder Durchschnittskurs setzen.")


def convert(amount: float, ccy: str, when: datetime,
            fx: FxTable | None, fallback_rate: float | None) -> float:
    if not amount:
        return 0.0
    if ccy.upper() in ("EUR", "€", ""):
        return float(amount)
    if ccy.upper() == "USD":
        if fx:
            return fx.usd_to_eur(float(amount), when, fallback_rate)
        if fallback_rate:
            return float(amount) / fallback_rate
        raise ValueError("USD-Beträge erkannt – bitte EZB-Kursdatei laden "
                         "oder USD/EUR-Kurs angeben.")
    raise ValueError(f"Währung {ccy} nicht unterstützt.")


def _clean_num(v) -> float:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return 0.0
    s = re.sub(r"[^\d,.\-]", "", str(v))
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") \
            else s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return abs(float(s))
    except ValueError:
        return 0.0


# ------------------------------------------------------------------ Detection
def detect_format(filename: str, df: pd.DataFrame | None) -> str:
    name = filename.lower()
    cols = " ".join(str(c).lower() for c in (df.columns if df is not None else []))
    if "etoro" in name or "closed positions" in cols or (
            "position id" in cols and "open date" in cols):
        return "etoro"
    if "coinbase" in name or ("transaction type" in cols
                              and "quantity transacted" in cols):
        return "coinbase"
    if "txhash" in cols and ("value_in" in cols or "value_out" in cols):
        return "basescan"
    return "unbekannt"


# ------------------------------------------------------------------ Coinbase
def parse_coinbase(df: pd.DataFrame, inhaber: str, depot: str,
                   fx: FxTable | None, fallback_rate: float | None
                   ) -> tuple[list[NormTx], list[str]]:
    """Coinbase-Transaktionsbericht (CSV). Convert = Verkauf + Kauf."""
    txs, warn = [], []
    col = {str(c).strip().lower(): c for c in df.columns}

    def get(row, *names, default=""):
        for n in names:
            if n in col:                      # exakter Treffer zuerst
                return row[col[n]]
            matches = [k for k in col if n in k]
            if matches:                       # sonst kürzester (spezifischster)
                return row[col[min(matches, key=len)]]
        return default

    for _, row in df.iterrows():
        typ_raw = str(get(row, "transaction type", "type")).strip().lower()
        asset = str(get(row, "asset")).strip().upper()
        if not asset or asset == "NAN":
            continue
        ts = pd.to_datetime(get(row, "timestamp", "date"), utc=True,
                            errors="coerce")
        if pd.isna(ts):
            continue
        ts = ts.tz_convert(None).to_pydatetime()
        menge = _clean_num(get(row, "quantity transacted", "quantity"))
        ccy = str(get(row, "price currency", "currency",
                      default="EUR")).strip() or "EUR"
        total = convert(_clean_num(get(row, "total (inclusive", "total")),
                        ccy, ts, fx, fallback_rate)
        subtotal = convert(_clean_num(get(row, "subtotal")),
                           ccy, ts, fx, fallback_rate)
        if not subtotal and not total:
            # Marktwert-Fallback (BMF: Einzahlung = fiktive Anschaffung
            # zum Marktwert) über Stückpreis der Transaktion
            preis = _clean_num(get(row, "price at transaction", "spot price at"))
            if preis and menge:
                subtotal = convert(preis * menge, ccy, ts, fx, fallback_rate)
        fee = convert(_clean_num(get(row, "fees and/or spread", "fee")),
                      ccy, ts, fx, fallback_rate)
        notes = str(get(row, "notes"))

        if "buy" in typ_raw:
            txs.append(NormTx(ts, asset, "kauf", menge,
                              subtotal or max(total - fee, 0), fee,
                              depot, inhaber, notes))
        elif "sell" in typ_raw:
            txs.append(NormTx(ts, asset, "verkauf", menge,
                              subtotal or (total + fee), fee,
                              depot, inhaber, notes))
        elif "convert" in typ_raw:
            wert = subtotal or total
            txs.append(NormTx(ts, asset, "verkauf", menge, wert, fee,
                              depot, inhaber, f"Tausch: {notes}"))
            m = re.search(r"to\s+([\d.,]+)\s+([A-Z0-9]{2,10})", notes)
            if m:
                ziel_menge, ziel_asset = _clean_num(m.group(1)), m.group(2)
                txs.append(NormTx(ts, ziel_asset, "kauf", ziel_menge, wert,
                                  0.0, depot, inhaber, f"aus Tausch {asset}"))
            else:
                warn.append(f"Convert am {ts:%d.%m.%Y} ({asset}): Ziel-Coin "
                            "nicht erkennbar – Kauf-Seite manuell ergänzen!")
        elif "transfer" in typ_raw or "deprecation" in typ_raw:
            continue  # interne Umbuchungen (z. B. ETH↔ETH2) – steuerneutral
        elif any(k in typ_raw for k in ("reward", "staking", "income", "learn")):
            txs.append(NormTx(ts, asset, "reward", menge,
                              subtotal or total, 0.0, depot, inhaber, typ_raw))
        elif "receive" in typ_raw:
            txs.append(NormTx(ts, asset, "transfer_in", menge, subtotal or total,
                              0.0, depot, inhaber, notes))
        elif "send" in typ_raw or "withdraw" in typ_raw:
            txs.append(NormTx(ts, asset, "transfer_out", menge, subtotal or total,
                              fee, depot, inhaber, notes))
    return txs, warn


# ------------------------------------------------------------------ eToro
def parse_etoro(file_bytes: bytes, inhaber: str,
                fx: FxTable | None, fallback_rate: float | None):
    """eToro-Kontoauszug (XLSX) → fertig gematchte Veräußerungen aus
    'Closed Positions'. Trennt echte Coins (Anlage SO) von CFDs (→ KAP!)."""
    from .crypto import Disposal
    xls = pd.ExcelFile(io.BytesIO(file_bytes))
    sheet = next((s for s in xls.sheet_names
                  if "closed" in s.lower()), None)
    if not sheet:
        raise ValueError("Blatt 'Closed Positions' nicht gefunden – bitte den "
                         "vollständigen eToro-Kontoauszug (XLSX) exportieren.")
    df = xls.parse(sheet)
    col = {str(c).strip().lower(): c for c in df.columns}

    def g(row, *names, default=None):
        for n in names:
            if n in col:
                return row[col[n]]
            matches = [k for k in col if n in k]
            if matches:
                return row[col[min(matches, key=len)]]
        return default

    disposals, cfd_hinweise, warn = [], [], []
    for _, row in df.iterrows():
        action = str(g(row, "action", default="")).upper()
        typ = str(g(row, "type", default="")).lower()
        asset = next((c for c in KNOWN_COINS if c in action.split()
                      or f" {c}" in f" {action}"), None)
        ist_krypto = "crypto" in typ or asset is not None
        if not ist_krypto:
            continue
        leverage = _clean_num(g(row, "leverage", default=1)) or 1
        ist_short = action.startswith(("SELL", "SHORT"))
        open_ts = pd.to_datetime(g(row, "open date"), dayfirst=True,
                                 errors="coerce")
        close_ts = pd.to_datetime(g(row, "close date"), dayfirst=True,
                                  errors="coerce")
        if pd.isna(open_ts) or pd.isna(close_ts):
            continue
        invest_usd = _clean_num(g(row, "amount"))
        profit_usd = float(str(g(row, "profit", default=0)).replace(",", ".")
                           if not isinstance(g(row, "profit", default=0),
                                             (int, float))
                           else g(row, "profit", default=0) or 0)
        fees_usd = _clean_num(g(row, "spread", default=0)) + \
            _clean_num(g(row, "rollover", default=0))
        units = _clean_num(g(row, "units", default=0))

        if leverage > 1 or ist_short:
            cfd_hinweise.append(
                f"CFD erkannt ({action}, Hebel {leverage:g}×, geschlossen "
                f"{close_ts:%d.%m.%Y}, P/L {profit_usd:+.2f} USD) → gehört in "
                "die Anlage KAP (Termingeschäft), NICHT in die Anlage SO. "
                "Verlustverrechnung für Termingeschäfte beachten!")
            continue

        kosten = convert(invest_usd, "USD", open_ts, fx, fallback_rate)
        erloes = convert(invest_usd + profit_usd - fees_usd, "USD",
                         close_ts, fx, fallback_rate)
        disposals.append(Disposal(
            asset=asset or action.replace("BUY", "").strip(),
            menge=units, kauf_ts=open_ts.to_pydatetime(),
            verkauf_ts=close_ts.to_pydatetime(),
            kosten_eur=round(kosten, 2), erloes_eur=round(erloes, 2),
            gebuehren_eur=round(convert(fees_usd, "USD", close_ts, fx,
                                        fallback_rate), 2),
            depot="eToro", inhaber=inhaber,
            hinweis="eToro Position (USD→EUR je Handelstag)"))
    warn.append("eToro: Offene Positionen sind im Kontoauszug nicht enthalten "
                "– für den Haltefrist-Optimizer das Portfolio separat prüfen.")
    return disposals, cfd_hinweise, warn


# ------------------------------------------------------- Generisch + Claude
MAPPING_PROMPT = """Du bist ein Datenanalyst. Ordne die Spalten dieses
Krypto-Transaktionsexports einem Zielschema zu. Antworte NUR mit JSON:
{
  "spalten": {"timestamp": "<Spaltenname>", "typ": "<Spaltenname>",
              "asset": "<Spaltenname>", "menge": "<Spaltenname>",
              "betrag": "<Spaltenname oder null>",
              "gebuehr": "<Spaltenname oder null>"},
  "waehrung": "EUR oder USD",
  "typ_mapping": {"kauf": ["..."], "verkauf": ["..."], "reward": ["..."],
                  "transfer_in": ["..."], "transfer_out": ["..."],
                  "ignorieren": ["..."]},
  "dayfirst": true/false
}
"betrag" = Gesamtwert in Fiat. Werte in typ_mapping sind die exakten
Ausprägungen aus der Typ-Spalte."""


def claude_suggest_mapping(df: pd.DataFrame, api_key: str, model: str) -> dict:
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    sample = df.head(4).to_csv(index=False)
    resp = client.messages.create(
        model=model, max_tokens=1200, system=MAPPING_PROMPT,
        messages=[{"role": "user",
                   "content": f"Spalten und Beispielzeilen:\n{sample}"}])
    return _parse_json("".join(b.text for b in resp.content
                               if b.type == "text"))


def parse_generic(df: pd.DataFrame, mapping: dict, inhaber: str, depot: str,
                  fx: FxTable | None, fallback_rate: float | None
                  ) -> tuple[list[NormTx], list[str]]:
    sp, warn, txs = mapping["spalten"], [], []
    typmap = {}
    for ziel, werte in mapping.get("typ_mapping", {}).items():
        for w in werte:
            typmap[str(w).strip().lower()] = ziel
    ccy = mapping.get("waehrung", "EUR")
    for _, row in df.iterrows():
        raw_typ = str(row.get(sp["typ"], "")).strip().lower()
        ziel_typ = typmap.get(raw_typ)
        if ziel_typ in (None, "ignorieren"):
            continue
        ts = pd.to_datetime(row[sp["timestamp"]],
                            dayfirst=mapping.get("dayfirst", True),
                            utc=True, errors="coerce")
        if pd.isna(ts):
            warn.append(f"Zeile ohne lesbares Datum übersprungen ({raw_typ}).")
            continue
        ts = ts.tz_convert(None).to_pydatetime()
        betrag = _clean_num(row.get(sp.get("betrag"))) if sp.get("betrag") else 0
        fee = _clean_num(row.get(sp.get("gebuehr"))) if sp.get("gebuehr") else 0
        txs.append(NormTx(
            ts, str(row[sp["asset"]]).strip().upper(), ziel_typ,
            _clean_num(row.get(sp["menge"])),
            convert(betrag, ccy, ts, fx, fallback_rate),
            convert(fee, ccy, ts, fx, fallback_rate),
            depot, inhaber))
    return txs, warn
