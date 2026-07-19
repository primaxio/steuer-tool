"""
Regressionstests für die FIFO-Engine (core/crypto.py) – "Kernstück" laut
CLAUDE.md, bisher ohne eigene Testdatei. Deckt die Basis-FIFO-Logik ab
(Grundlage, damit der Wallet-Transfer-Umbau nichts kaputt macht) UND die
neue Haltefrist-Verknüpfung bei Transfers zwischen EIGENEN Wallets
(AUDIT.md-Backlog: "Transfers zwischen eigenen Wallets übernehmen
Haltefrist nicht automatisch").
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.crypto import NormTx, run_fifo

D0 = datetime(2023, 1, 10)


def tx(offset_tage, typ, menge, wert_eur, depot="A", asset="BTC",
      gebuehr_eur=0.0, inhaber="P1"):
    return NormTx(ts=D0 + timedelta(days=offset_tage), asset=asset, typ=typ,
                 menge=menge, wert_eur=wert_eur, gebuehr_eur=gebuehr_eur,
                 depot=depot, inhaber=inhaber)


# ---------------------------------------------------------------- Basis-FIFO
def test_einfacher_kauf_verkauf():
    txs = [tx(0, "kauf", 1.0, 20000.0), tx(30, "verkauf", 1.0, 25000.0)]
    disposals, open_lots, rewards, warnungen = run_fifo(txs)
    assert len(disposals) == 1
    d = disposals[0]
    assert d.kosten_eur == 20000.0 and d.erloes_eur == 25000.0
    assert d.gewinn == 5000.0
    assert not open_lots
    print("✅ Einfacher Kauf/Verkauf: FIFO-Kostenbasis und Gewinn korrekt")


def test_fifo_reihenfolge_bei_teilverkauf():
    txs = [tx(0, "kauf", 1.0, 10000.0), tx(10, "kauf", 1.0, 20000.0),
          tx(20, "verkauf", 1.0, 15000.0)]
    disposals, open_lots, _, _ = run_fifo(txs)
    assert len(disposals) == 1 and len(open_lots) == 1
    assert disposals[0].kosten_eur == 10000.0, \
        "FIFO muss das ÄLTESTE Lot zuerst verkaufen."
    assert open_lots[0].kosten_eur == 20000.0
    print("✅ FIFO verkauft älteste Lots zuerst")


def test_verkauf_ohne_bestand_warnt():
    txs = [tx(0, "verkauf", 1.0, 20000.0)]
    disposals, _, _, warnungen = run_fifo(txs)
    assert disposals[0].kosten_eur == 0.0
    assert any("ohne erfassten Einkauf" in w for w in warnungen)
    print("✅ Verkauf ohne Bestand: Kosten 0 € (worst case) + Warnung")


# ---------------------------------------------------------- Wallet-Transfer
def test_transfer_ohne_partner_bleibt_unverknuepft():
    """Kein zweites Depot für denselben Inhaber/Asset -> alte, konservative
    Behandlung (Warnung, keine automatische Verknüpfung)."""
    txs = [tx(0, "kauf", 1.0, 20000.0, depot="A"),
          tx(50, "transfer_out", 1.0, 0.0, depot="A")]
    disposals, open_lots, _, warnungen = run_fifo(txs)
    assert not open_lots and not disposals
    assert any("kein passender Eingang" in w for w in warnungen)
    print("✅ Unverknüpfter Transfer: konservative Warnung ohne Zielwallet")


def test_transfer_mit_partner_uebernimmt_haltefrist():
    """Kauf in Depot A, Transfer nach 100 Tagen in Depot B, Verkauf in
    Depot B nach insgesamt 380 Tagen (< 365 Tage NACH dem Transfer, aber
    > 365 Tage seit dem URSPRÜNGLICHEN Kauf) -> muss steuerfrei sein.
    Vor dem Fix würde die Haltefrist beim Transfer neu beginnen und der
    Verkauf fälschlich als steuerpflichtig gelten."""
    txs = [
        tx(0, "kauf", 1.0, 20000.0, depot="A"),
        tx(100, "transfer_out", 1.0, 0.0, depot="A"),
        tx(100, "transfer_in", 1.0, 0.0, depot="B"),
        tx(380, "verkauf", 1.0, 30000.0, depot="B"),
    ]
    disposals, open_lots, _, warnungen = run_fifo(txs)
    assert len(disposals) == 1, disposals
    d = disposals[0]
    assert d.kauf_ts == D0, \
        f"Kaufdatum muss vom Ursprungs-Lot übernommen werden, ist {d.kauf_ts}"
    assert d.kosten_eur == 20000.0, \
        "Kostenbasis muss vom Ursprungs-Lot übernommen werden."
    assert d.steuerfrei, \
        "380 Tage seit dem URSPRÜNGLICHEN Kauf -> muss steuerfrei sein."
    assert any("automatisch mit dem Empfänger-Wallet verknüpft" in w
              for w in warnungen)
    print("✅ Verknüpfter Wallet-Transfer: Haltefrist + Kostenbasis wandern "
         "korrekt mit, Verkauf nach 380 Tagen ist steuerfrei")


def test_transfer_mit_partner_bleibt_steuerpflichtig_innerhalb_frist():
    """Gegenprobe: Verkauf nach nur 200 Tagen seit dem URSPRÜNGLICHEN Kauf
    -> muss weiterhin steuerpflichtig sein (Haltefrist nicht künstlich
    verlängert, nur korrekt vom echten Kaufdatum aus gerechnet)."""
    txs = [
        tx(0, "kauf", 1.0, 20000.0, depot="A"),
        tx(50, "transfer_out", 1.0, 0.0, depot="A"),
        tx(50, "transfer_in", 1.0, 0.0, depot="B"),
        tx(200, "verkauf", 1.0, 30000.0, depot="B"),
    ]
    disposals, _, _, _ = run_fifo(txs)
    assert len(disposals) == 1
    assert not disposals[0].steuerfrei
    assert disposals[0].gewinn == 10000.0
    print("✅ Verknüpfter Transfer, Verkauf innerhalb 1 Jahr: korrekt "
         "weiterhin steuerpflichtig")


def test_transfer_mit_gebuehr_skaliert_kostenbasis_anteilig():
    """Empfangene Menge < versendete Menge (Netzwerkgebühr) -> Kostenbasis
    wird anteilig mitgenommen, nicht 1:1 übernommen."""
    txs = [
        tx(0, "kauf", 1.0, 20000.0, depot="A"),
        tx(10, "transfer_out", 1.0, 0.0, depot="A"),
        tx(10, "transfer_in", 0.99, 0.0, depot="B"),  # 1% Netzwerkgebühr
        tx(400, "verkauf", 0.99, 30000.0, depot="B"),
    ]
    disposals, _, _, _ = run_fifo(txs)
    assert len(disposals) == 1
    d = disposals[0]
    assert abs(d.menge - 0.99) < 1e-9
    assert abs(d.kosten_eur - 19800.0) < 0.5, d.kosten_eur  # 20000 * 0.99
    print(f"✅ Transfer mit Netzwerkgebühr: Kostenbasis anteilig skaliert "
         f"({d.kosten_eur} € statt voller 20.000 €)")


def test_transfer_ueber_zwei_lots_traegt_beide_daten():
    """Transfer, der ZWEI unterschiedlich alte Lots konsumiert -> im
    Ziel-Depot müssen zwei offene Lots mit den jeweils ORIGINALEN
    Kaufdaten entstehen, nicht ein einzelnes Lot mit Transferdatum."""
    txs = [
        tx(0, "kauf", 1.0, 10000.0, depot="A"),
        tx(50, "kauf", 1.0, 22000.0, depot="A"),
        tx(100, "transfer_out", 2.0, 0.0, depot="A"),
        tx(100, "transfer_in", 2.0, 0.0, depot="B"),
    ]
    _, open_lots, _, _ = run_fifo(txs)
    assert len(open_lots) == 2, open_lots
    daten = sorted(l.kauf_ts for l in open_lots)
    assert daten == [D0, D0 + timedelta(days=50)]
    kosten = sorted(l.kosten_eur for l in open_lots)
    assert kosten == [10000.0, 22000.0]
    print("✅ Transfer über zwei unterschiedlich alte Lots: beide "
         "Originaldaten/Kostenbasen bleiben im Ziel-Depot erhalten")


def test_transfer_verschiedene_inhaber_wird_nicht_verknuepft():
    """Depot-Wechsel zwischen VERSCHIEDENEN Personen ist keine eigene
    Wallet-zu-Wallet-Bewegung -> darf NICHT automatisch verknüpft werden."""
    txs = [
        tx(0, "kauf", 1.0, 20000.0, depot="A", inhaber="P1"),
        tx(50, "transfer_out", 1.0, 0.0, depot="A", inhaber="P1"),
        tx(50, "transfer_in", 1.0, 0.0, depot="B", inhaber="P2"),
    ]
    _, open_lots, _, warnungen = run_fifo(txs)
    # P2 bekommt (wie schon vor dem Umbau) ein frisches Lot am Empfangstag –
    # entscheidend ist NUR, dass es NICHT P1s Originaldaten übernimmt.
    assert len(open_lots) == 1
    assert open_lots[0].kauf_ts == D0 + timedelta(days=50), \
        "P2 darf NICHT P1s ursprüngliches Kaufdatum erben."
    assert open_lots[0].kosten_eur == 0.0, \
        "P2 darf NICHT P1s ursprüngliche Kostenbasis erben."
    assert any("kein passender Eingang" in w for w in warnungen)
    print("✅ Transfer zwischen unterschiedlichen Inhabern bleibt "
         "unverknüpft (kein versehentlicher Datenübertrag über Personen "
         "hinweg)")


if __name__ == "__main__":
    test_einfacher_kauf_verkauf()
    test_fifo_reihenfolge_bei_teilverkauf()
    test_verkauf_ohne_bestand_warnt()
    test_transfer_ohne_partner_bleibt_unverknuepft()
    test_transfer_mit_partner_uebernimmt_haltefrist()
    test_transfer_mit_partner_bleibt_steuerpflichtig_innerhalb_frist()
    test_transfer_mit_gebuehr_skaliert_kostenbasis_anteilig()
    test_transfer_ueber_zwei_lots_traegt_beide_daten()
    test_transfer_verschiedene_inhaber_wird_nicht_verknuepft()
    print("🎉 Alle FIFO-/Wallet-Transfer-Tests bestanden.")
