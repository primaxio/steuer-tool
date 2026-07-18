"""
Krypto-Engine: FIFO-Berechnung (walletbezogen, BMF-Schreiben v. 06.03.2025),
Haltefrist-Logik (§ 23 EStG), Optimizer für offene Positionen und
Steuerschätzung nach § 32a EStG (inkl. Splitting-Verfahren).
"""

from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta
from collections import deque

EPS = 1e-9


@dataclass
class NormTx:
    """Normalisierte Transaktion – Zielformat aller Parser."""
    ts: datetime
    asset: str
    typ: str            # kauf | verkauf | reward | transfer_in | transfer_out
    menge: float
    wert_eur: float     # Gesamtwert in EUR (Kauf: Kosten, Verkauf: Erlös)
    gebuehr_eur: float = 0.0
    depot: str = "Standard"      # Börse/Wallet (walletbezogene FIFO!)
    inhaber: str = "P1"          # P1 = Ehegatte 1, P2 = Ehegatte 2
    notiz: str = ""


@dataclass
class Disposal:
    """Abgeschlossene Veräußerung (ein FIFO-Lot-Anteil oder eToro-Position)."""
    asset: str
    menge: float
    kauf_ts: datetime
    verkauf_ts: datetime
    kosten_eur: float        # Anschaffungskosten inkl. Kaufgebühren (anteilig)
    erloes_eur: float        # Erlös abzgl. Verkaufsgebühren (anteilig)
    gebuehren_eur: float
    depot: str
    inhaber: str
    hinweis: str = ""

    @property
    def gewinn(self) -> float:
        return round(self.erloes_eur - self.kosten_eur, 2)

    @property
    def haltetage(self) -> int:
        return (self.verkauf_ts.date() - self.kauf_ts.date()).days

    @property
    def steuerfrei(self) -> bool:
        return self.verkauf_ts.date() > _jahrestag(self.kauf_ts.date())


@dataclass
class OpenLot:
    """Noch gehaltener Bestand mit Steuerfrei-Datum."""
    asset: str
    menge: float
    kauf_ts: datetime
    kosten_eur: float
    depot: str
    inhaber: str

    @property
    def steuerfrei_ab(self) -> date:
        return _jahrestag(self.kauf_ts.date()) + timedelta(days=1)

    @property
    def resttage(self) -> int:
        return max(0, (self.steuerfrei_ab - date.today()).days)

    @property
    def ist_steuerfrei(self) -> bool:
        return self.resttage == 0


def _jahrestag(d: date) -> date:
    """Anschaffungstag + 1 Jahr (Fristende § 187/188 BGB); 29.02. → 28.02."""
    try:
        return d.replace(year=d.year + 1)
    except ValueError:
        return d.replace(year=d.year + 1, month=2, day=28)


# --------------------------------------------------------------- FIFO
def run_fifo(txs: list[NormTx]) -> tuple[list[Disposal], list[OpenLot],
                                         list[NormTx], list[str]]:
    """Walletbezogene FIFO je (Inhaber, Depot, Asset).
    Rewards zählen als Anschaffung zum Marktwert UND als Einnahme (§ 22 Nr. 3).
    Rückgabe: (Veräußerungen, offene Lots, Reward-Txs, Warnungen)."""
    disposals, open_lots, warnungen = [], [], []
    rewards = [t for t in txs if t.typ == "reward"]

    gruppen: dict[tuple, list[NormTx]] = {}
    for t in txs:
        gruppen.setdefault((t.inhaber, t.depot, t.asset.upper()), []).append(t)

    for (inhaber, depot, asset), group in gruppen.items():
        lots: deque[list] = deque()   # [restmenge, restkosten, kauf_ts]
        for t in sorted(group, key=lambda x: (
                x.ts.date(),
                0 if x.typ in ("kauf", "reward", "transfer_in") else 1,
                x.ts)):  # tagesweise: Zugänge vor Abgängen (Settlement-Timing)
            if t.typ in ("kauf", "reward", "transfer_in"):
                if t.menge <= EPS:
                    continue  # Null-Mengen erzeugen keine Lots
                kosten = t.wert_eur + (t.gebuehr_eur if t.typ == "kauf" else 0)
                if t.typ == "transfer_in" and t.wert_eur <= 0:
                    warnungen.append(
                        f"{asset} ({depot}): Eingehender Transfer am "
                        f"{t.ts:%d.%m.%Y} ohne Anschaffungsdaten – Haltefrist/"
                        "Kosten der Ursprungswallet manuell ergänzen!")
                lots.append([t.menge, kosten, t.ts])
            elif t.typ == "verkauf":
                rest = t.menge
                netto_erloes = t.wert_eur - t.gebuehr_eur
                while rest > EPS and lots:
                    lot = lots[0]
                    if lot[0] <= EPS:
                        lots.popleft()
                        continue
                    nutze = min(rest, lot[0])
                    anteil_lot = nutze / lot[0]
                    anteil_verkauf = nutze / t.menge
                    disposals.append(Disposal(
                        asset=asset, menge=nutze, kauf_ts=lot[2],
                        verkauf_ts=t.ts,
                        kosten_eur=round(lot[1] * anteil_lot, 2),
                        erloes_eur=round(netto_erloes * anteil_verkauf, 2),
                        gebuehren_eur=round(t.gebuehr_eur * anteil_verkauf, 2),
                        depot=depot, inhaber=inhaber, hinweis=t.notiz))
                    lot[1] -= lot[1] * anteil_lot
                    lot[0] -= nutze
                    rest -= nutze
                    if lot[0] <= EPS:
                        lots.popleft()
                if rest > EPS:
                    disposals.append(Disposal(
                        asset=asset, menge=rest, kauf_ts=t.ts, verkauf_ts=t.ts,
                        kosten_eur=0.0,
                        erloes_eur=round(netto_erloes * rest / t.menge, 2),
                        gebuehren_eur=0.0, depot=depot, inhaber=inhaber,
                        hinweis="⚠️ Verkauf ohne bekannten Einkauf"))
                    warnungen.append(
                        f"{asset} ({depot}): Verkauf am {t.ts:%d.%m.%Y} über "
                        f"{rest:.8g} {asset} ohne erfassten Einkauf – "
                        "Anschaffungskosten wurden mit 0 € angesetzt "
                        "(worst case). Bitte Kauf-Historie ergänzen!")
            elif t.typ == "transfer_out":
                # Steuerneutraler Übertrag: Coins verlassen den Topf MIT
                # ihren Anschaffungsdaten (FIFO), ohne Veräußerung.
                rest = t.menge
                while rest > EPS and lots:
                    lot = lots[0]
                    if lot[0] <= EPS:
                        lots.popleft()
                        continue
                    nutze = min(rest, lot[0])
                    lot[1] -= lot[1] * (nutze / lot[0])
                    lot[0] -= nutze
                    rest -= nutze
                    if lot[0] <= EPS:
                        lots.popleft()
                if rest > EPS:
                    warnungen.append(
                        f"{asset} ({depot}): Auszahlung am {t.ts:%d.%m.%Y} "
                        f"übersteigt Bestand um {rest:.8g} – Historie prüfen!")
                warnungen.append(
                    f"{asset} ({depot}): Auszahlung {t.menge:.8g} am "
                    f"{t.ts:%d.%m.%Y} steuerneutral ausgebucht – Zielwallet "
                    "übernimmt Kaufdatum/Kosten (bei Zahlung an Dritte wäre "
                    "es eine Veräußerung!).")
        for lot in lots:
            if lot[0] > EPS:
                open_lots.append(OpenLot(
                    asset=asset, menge=round(lot[0], 10), kauf_ts=lot[2],
                    kosten_eur=round(lot[1], 2), depot=depot, inhaber=inhaber))
    return disposals, open_lots, rewards, warnungen


# --------------------------------------------------------------- Aggregation
def aggregate(disposals: list[Disposal], rewards: list[NormTx],
              jahr: int, cfg: dict) -> dict:
    """Kennzahlen je Ehegatte für das Steuerjahr."""
    ergebnis: dict[str, dict] = {}
    for p in ("P1", "P2"):
        d_jahr = [d for d in disposals
                  if d.verkauf_ts.year == jahr and d.inhaber == p]
        pflichtig = [d for d in d_jahr if not d.steuerfrei]
        gewinne = sum(d.gewinn for d in pflichtig if d.gewinn > 0)
        verluste = sum(-d.gewinn for d in pflichtig if d.gewinn < 0)
        netto = round(gewinne - verluste, 2)
        freigrenze = cfg["freigrenze_private_veraeusserung"]
        rw = round(sum(t.wert_eur for t in rewards
                       if t.ts.year == jahr and t.inhaber == p), 2)
        ergebnis[p] = {
            "veraeusserungen": len(d_jahr),
            "gewinn_brutto": round(gewinne, 2),
            "verluste": round(verluste, 2),
            "netto_gewinn": netto,
            "gewinn_steuerfrei_haltefrist": round(sum(
                d.gewinn for d in d_jahr if d.steuerfrei), 2),
            "gebuehren": round(sum(d.gebuehren_eur for d in d_jahr), 2),
            "freigrenze": freigrenze,
            "unter_freigrenze": 0 <= netto < freigrenze,
            "steuerpflichtiger_betrag": netto if netto >= freigrenze else 0.0,
            "rewards_summe": rw,
            "rewards_steuerpflichtig": rw if rw >= cfg.get(
                "freigrenze_sonstige_leistungen", 256) else 0.0,
        }
    return ergebnis


# --------------------------------------------------------------- Optimizer
def optimizer_hinweise(open_lots: list[OpenLot], horizont_tage: int = 200
                       ) -> list[str]:
    """Konkrete Halte-Empfehlungen für offene Lots."""
    tipps = []
    for lot in sorted(open_lots, key=lambda l: l.steuerfrei_ab):
        if lot.ist_steuerfrei:
            tipps.append(
                f"✅ {lot.menge:g} {lot.asset} ({lot.depot}, gekauft "
                f"{lot.kauf_ts:%d.%m.%Y}) ist bereits STEUERFREI verkaufbar.")
        elif lot.resttage <= horizont_tage:
            tipps.append(
                f"⏳ {lot.menge:g} {lot.asset} ({lot.depot}, gekauft "
                f"{lot.kauf_ts:%d.%m.%Y}): noch {lot.resttage} Tage halten – "
                f"steuerfrei ab {lot.steuerfrei_ab:%d.%m.%Y}. Ein Verkauf "
                "vorher wäre voll steuerpflichtig!")
    if not tipps and open_lots:
        naechstes = min(open_lots, key=lambda l: l.resttage)
        tipps.append(
            f"Nächstes Lot wird erst in {naechstes.resttage} Tagen steuerfrei "
            f"({naechstes.asset}, ab {naechstes.steuerfrei_ab:%d.%m.%Y}).")
    return tipps


# --------------------------------------------------------------- § 32a Tarif
def est_nach_tarif(zve: float, cfg: dict) -> float:
    """Tarifliche ESt nach § 32a EStG (Werte aus tax_config, Schätzung)."""
    t = cfg.get("tarif")
    if not t or zve <= 0:
        return 0.0
    x = int(zve)  # Abrundung auf vollen Euro
    if x <= t["gfb"]:
        return 0.0
    if x <= t["z2_ende"]:
        y = (x - t["gfb"]) / 10000
        est = (t["z2"][0] * y + t["z2"][1]) * y
    elif x <= t["z3_ende"]:
        z = (x - t["z2_ende"]) / 10000
        est = (t["z3"][0] * z + t["z3"][1]) * z + t["z3"][2]
    elif x <= t["z4_ende"]:
        est = t["z4"][0] * x - t["z4"][1]
    else:
        est = t["z5"][0] * x - t["z5"][1]
    return float(int(est))


def steuer_auf_krypto(zve_ohne_krypto: float, krypto_betrag: float,
                      cfg: dict, splitting: bool) -> dict:
    """Mehrsteuer durch den steuerpflichtigen Kryptogewinn (Grenzbetrachtung)."""
    def tarif(z):
        if splitting:
            return 2 * est_nach_tarif(z / 2, cfg)
        return est_nach_tarif(z, cfg)
    ohne = tarif(zve_ohne_krypto)
    mit = tarif(zve_ohne_krypto + max(0.0, krypto_betrag))
    mehr = round(mit - ohne, 2)
    grenzsatz = round(mehr / krypto_betrag * 100, 1) if krypto_betrag > 0 else 0
    return {"est_ohne": ohne, "est_mit": mit, "mehrsteuer": mehr,
            "grenzsteuersatz_prozent": grenzsatz}


def serialize(disposals, open_lots, rewards, agg, warnungen) -> dict:
    return {
        "pro_person": agg,
        "veraeusserungen": [
            {**asdict(d), "gewinn": d.gewinn, "haltetage": d.haltetage,
             "steuerfrei": d.steuerfrei,
             "kauf_ts": d.kauf_ts.isoformat(),
             "verkauf_ts": d.verkauf_ts.isoformat()} for d in disposals],
        "offene_lots": [
            {**asdict(l), "steuerfrei_ab": l.steuerfrei_ab.isoformat(),
             "resttage": l.resttage, "kauf_ts": l.kauf_ts.isoformat()}
            for l in open_lots],
        "rewards": [{"ts": t.ts.isoformat(), "asset": t.asset,
                     "wert_eur": t.wert_eur, "inhaber": t.inhaber}
                    for t in rewards],
        "warnungen": warnungen,
    }
