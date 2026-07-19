"""Streamlit-Tab '₿ Krypto' – Import, FIFO-Ergebnis, Optimizer, Steuerschätzung."""

import io

import pandas as pd
import streamlit as st

from .crypto import (aggregate, optimizer_hinweise, run_fifo, serialize,
                     steuer_auf_krypto)
from .crypto_parsers import (FxTable, claude_suggest_mapping, detect_format,
                             parse_coinbase, parse_etoro, parse_generic)


def _st_init():
    ss = st.session_state
    ss.setdefault("crypto_txs", [])
    ss.setdefault("crypto_matched", [])      # eToro-Disposals
    ss.setdefault("crypto_cfd_hinweise", [])
    ss.setdefault("crypto_import_warn", [])
    ss.setdefault("crypto_files", set())
    ss.setdefault("crypto_results", None)


def _read_table(upload) -> pd.DataFrame | None:
    try:
        if upload.name.lower().endswith((".xlsx", ".xls")):
            return pd.read_excel(io.BytesIO(upload.getvalue()))
        return pd.read_csv(io.BytesIO(upload.getvalue()),
                           sep=None, engine="python")
    except Exception:
        return None


def _broker_automatik_werte(docs: list) -> dict:
    """Summiert Zeile 19/21/24-Werte aus hochgeladenen broker_steuerbericht-
    Dokumenten – fließt bereits automatisch additiv in veranlagung.py/
    elster_export.py ein (mit Warnhinweis gegen Doppel-Eingabe im
    manuellen Termingeschäfte-Feld unten)."""
    out = {"kap_zeile19_zinsen": 0.0, "kap_zeile21_termingewinne": 0.0,
          "kap_zeile24_terminverluste": 0.0}
    for d in docs or []:
        if d.get("kategorie") != "broker_steuerbericht":
            continue
        ed = d.get("extrahierte_daten", {})
        for feld in out:
            out[feld] += float(ed.get(feld) or 0)
    return out


def render_crypto_tab(cfg: dict, api_key: str, model: str,
                      interview: dict, personen: dict, docs: list = None):
    _st_init()
    ss = st.session_state
    e = lambda v: f"{v:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")

    st.subheader("Krypto-Import (eToro · Coinbase · Base · generisch)")
    c1, c2 = st.columns([1, 2])
    with c1:
        inhaber = st.selectbox("Depot-Inhaber", ["P1", "P2"],
                               format_func=lambda k: personen.get(k, k))
    with c2:
        if "_fx" not in ss:
            try:
                with st.spinner("Lade EZB-Tageskurse …"):
                    ss["_fx"] = FxTable.from_ecb_online()
            except Exception as exc:  # noqa: BLE001
                ss["_fx"] = None
                ss["_fx_fehler"] = str(exc)
        fx = ss.get("_fx")
        if fx and fx.rates:
            neuester = max(fx.rates)
            st.success(f"💱 EZB-Tageskurse automatisch geladen "
                       f"({len(fx.rates):,} Handelstage, aktuellster: "
                       f"{neuester:%d.%m.%Y}) – USD wird tagesgenau "
                       "umgerechnet.".replace(",", "."))
        else:
            st.warning("EZB-Kurse konnten nicht automatisch geladen werden"
                       + (f" ({ss.get('_fx_fehler', '')[:60]})"
                          if ss.get("_fx_fehler") else "") +
                       " – Datei manuell laden oder Notfall-Kurs nutzen.")
    fallback_rate = 1.08
    if not (ss.get("_fx") and ss["_fx"].rates):
        f1, f2 = st.columns(2)
        fx_file = f1.file_uploader("eurofxref-hist.csv (manuell)", type=None)
        fallback_rate = f2.number_input("Notfall USD/EUR-Kurs", 0.5, 2.0,
                                        1.08, 0.01)
        if fx_file:
            ss["_fx"] = FxTable.from_file(fx_file)
            st.rerun()
    fx = ss.get("_fx")

    with st.expander("🔄 Automatischer Abruf per API (Coinbase & Base) – "
                     "Blockpit-Style"):
        st.caption("⚠️ Nur LESE-Rechte vergeben! Coinbase: CDP-API-Key mit "
                   "wallet:accounts:read + wallet:transactions:read. "
                   "Basescan-Key ist kostenlos (basescan.org).")
        ca, cb = st.columns(2)
        with ca:
            st.markdown("**Coinbase**")
            cb_key = st.text_input("API-Key-Name (organizations/…)",
                                   key="cb_key")
            cb_pem = st.text_area("Private Key (PEM, EC)", key="cb_pem",
                                  height=90)
            if st.button("Coinbase abrufen", disabled=not (cb_key and cb_pem)):
                from .connectors.coinbase_api import (bewerte_fehlende,
                                                      sync_coinbase)
                from .connectors.preise import PreisDienst
                try:
                    with st.spinner("Rufe Coinbase-Konten ab …"):
                        neu, warn = sync_coinbase(cb_key.strip(), cb_pem,
                                                  inhaber)
                        warn += bewerte_fehlende(neu, PreisDienst())
                    ss.crypto_txs += neu
                    ss.crypto_import_warn += warn
                    st.success(f"{len(neu)} Transaktionen importiert.")
                    st.rerun()
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Coinbase-Sync fehlgeschlagen: {exc}")
        with cb:
            st.markdown("**Base (on-chain)**")
            adresse = st.text_input("Wallet-Adresse (0x…)", key="base_addr")
            bs_key = st.text_input("Basescan-API-Key", key="bs_key",
                                   type="password")
            if st.button("Base abrufen", disabled=not (adresse and bs_key)):
                from .connectors.base_chain import sync_base
                from .connectors.preise import PreisDienst
                try:
                    with st.spinner("Lese Blockchain & Kurse (kann bei "
                                    "vielen Txs dauern) …"):
                        neu, warn = sync_base(adresse, bs_key.strip(),
                                              inhaber, PreisDienst())
                    ss.crypto_txs += neu
                    ss.crypto_import_warn += warn
                    st.success(f"{len(neu)} On-Chain-Ereignisse importiert.")
                    st.rerun()
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Base-Sync fehlgeschlagen: {exc}")

    uploads = st.file_uploader(
        "Transaktions-Exporte (CSV/XLSX) – PDFs bitte in Tab 1 hochladen",
        type=["csv", "xlsx", "xls"], accept_multiple_files=True,
        key="crypto_uploader")

    for up in uploads or []:
        file_key = f"{up.name}|{inhaber}"
        if file_key in ss.crypto_files:
            continue
        df = _read_table(up)
        fmt = detect_format(up.name, df)
        st.markdown(f"**`{up.name}`** → erkannt als **{fmt}**")
        try:
            if fmt == "etoro":
                disp, cfd, warn = parse_etoro(up.getvalue(), inhaber,
                                              fx, fallback_rate)
                if st.button(f"✅ {len(disp)} eToro-Positionen übernehmen "
                             f"({personen[inhaber]})", key=f"imp_{file_key}"):
                    ss.crypto_matched += disp
                    ss.crypto_cfd_hinweise += cfd
                    ss.crypto_import_warn += warn
                    ss.crypto_files.add(file_key)
                    st.rerun()
                if cfd:
                    st.warning(f"{len(cfd)} CFD-Position(en) erkannt → werden "
                               "NICHT in Anlage SO übernommen (KAP!). Details "
                               "nach Import unten.")
            elif fmt == "coinbase" and df is not None:
                txs, warn = parse_coinbase(df, inhaber, "Coinbase",
                                           fx, fallback_rate)
                if st.button(f"✅ {len(txs)} Coinbase-Transaktionen übernehmen "
                             f"({personen[inhaber]})", key=f"imp_{file_key}"):
                    ss.crypto_txs += txs
                    ss.crypto_import_warn += warn
                    ss.crypto_files.add(file_key)
                    st.rerun()
            elif df is not None:
                st.info("Unbekanntes Format (z. B. Base/Wallet-Export) – "
                        "Claude analysiert die Spalten.")
                mkey = f"map_{file_key}"
                if mkey not in ss and st.button(
                        "🤖 Spalten automatisch zuordnen",
                        key=f"btn_{file_key}", disabled=not api_key):
                    ss[mkey] = claude_suggest_mapping(df, api_key, model)
                    st.rerun()
                if mkey in ss:
                    st.json(ss[mkey], expanded=False)
                    depot = st.text_input("Depot-/Wallet-Name", "Base",
                                          key=f"dep_{file_key}")
                    if st.button("✅ Mit dieser Zuordnung importieren",
                                 key=f"go_{file_key}"):
                        txs, warn = parse_generic(df, ss[mkey], inhaber,
                                                  depot, fx, fallback_rate)
                        ss.crypto_txs += txs
                        ss.crypto_import_warn += warn
                        ss.crypto_files.add(file_key)
                        st.rerun()
            else:
                st.error("Datei konnte nicht gelesen werden.")
        except Exception as exc:  # noqa: BLE001
            st.error(f"Import-Fehler: {exc}")

    with st.expander("📉 Termingeschäfte & Broker-Zinsen (Phemex-Perps, "
                     "eToro-CFDs → Anlage KAP)"):
        st.caption("Werte aus den offiziellen Broker-Steuerberichten übernehmen "
                   "(z. B. eToro: 'Gewinne aus Termingeschäften' / Phemex: "
                   "Derivative P/L). Auslandsbroker behalten KEINE Steuer ein – "
                   "die ~26,4 % setzt das Finanzamt per Bescheid fest.")
        broker_auto = _broker_automatik_werte(docs)
        if any(broker_auto.values()):
            manuell_gesetzt = any(
                interview.get(f"termin_gewinne_{p}")
                or interview.get(f"termin_verluste_{p}")
                or interview.get(f"broker_zinsen_{p}")
                for p in ("P1", "P2"))
            hinweis = (
                f"Zinsen {e(broker_auto['kap_zeile19_zinsen'])} · "
                f"Termingewinne {e(broker_auto['kap_zeile21_termingewinne'])} · "
                f"Terminverluste {e(broker_auto['kap_zeile24_terminverluste'])}")
            if manuell_gesetzt:
                st.warning(
                    "⚠️ **Doppelerfassung-Risiko**: Aus deinem hochgeladenen "
                    f"Broker-Steuerbericht wurden bereits **{hinweis}** "
                    "automatisch übernommen (Tab 1 · Dokumente) UND "
                    "zusätzlich sind unten manuelle Werte eingetragen – "
                    "beide werden addiert! Nur eintragen, wenn es "
                    "ZUSÄTZLICHE, unabhängige Beträge sind (z. B. ein "
                    "zweiter Broker ohne Steuerbericht).")
            else:
                st.info(
                    f"✅ Aus deinem hochgeladenen Broker-Steuerbericht "
                    f"bereits automatisch übernommen: **{hinweis}**. Die "
                    "Felder unten nur für WEITERE, davon unabhängige "
                    "Broker/Beträge nutzen.")
        aktive_kap = ("P1", "P2") if interview.get("zusammenveranlagung") \
            else ("P1",)
        for p_key in aktive_kap:
            st.markdown(f"**{personen.get(p_key, p_key)}**")
            k1, k2, k3 = st.columns(3)
            interview[f"termin_gewinne_{p_key}"] = k1.number_input(
                "Gewinne Termingeschäfte (Z. 21)", 0.0, 10_000_000.0,
                float(interview.get(f"termin_gewinne_{p_key}") or 0.0),
                step=100.0, key=f"tg_{p_key}")
            interview[f"termin_verluste_{p_key}"] = k2.number_input(
                "Verluste Termingeschäfte (Z. 24)", 0.0, 10_000_000.0,
                float(interview.get(f"termin_verluste_{p_key}") or 0.0),
                step=100.0, key=f"tv_{p_key}",
                help="Seit JStG 2024 wieder UNBEGRENZT mit Gewinnen "
                     "verrechenbar (20.000 €-Deckel rückwirkend gestrichen).")
            interview[f"broker_zinsen_{p_key}"] = k3.number_input(
                "Broker-Zinsen Ausland (Z. 19)", 0.0, 1_000_000.0,
                float(interview.get(f"broker_zinsen_{p_key}") or 0.0),
                step=10.0, key=f"bz_{p_key}")

    if not (ss.crypto_txs or ss.crypto_matched):
        return

    # ------------------------------------------------------------ Berechnung
    st.divider()
    disposals, open_lots, rewards, warn = run_fifo(ss.crypto_txs)
    disposals += ss.crypto_matched
    agg = aggregate(disposals, rewards, cfg["jahr"], cfg)
    ss.crypto_results = serialize(disposals, open_lots, rewards, agg,
                                  warn + ss.crypto_import_warn)
    interview["_crypto"] = ss.crypto_results

    st.subheader(f"Ergebnis Steuerjahr {cfg['jahr']}")
    aktive = [p for p in ("P1", "P2")
              if agg[p]["veraeusserungen"] or agg[p]["rewards_summe"]]
    for p in aktive or ["P1"]:
        a = agg[p]
        st.markdown(f"#### {personen.get(p, p)} – Anlage SO")
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Netto-Gewinn (< 1 J.)", e(a["netto_gewinn"]))
        k2.metric("Steuerfrei (> 1 J.)", e(a["gewinn_steuerfrei_haltefrist"]))
        k3.metric("Gebühren (abgezogen)", e(a["gebuehren"]))
        k4.metric("Steuerpflichtig", e(a["steuerpflichtiger_betrag"]))
        if a["unter_freigrenze"] and a["netto_gewinn"] > 0:
            st.success(f"✅ Unter der Freigrenze von {e(a['freigrenze'])} – "
                       "komplett steuerfrei (Freigrenze gilt pro Ehegatte!).")
        elif a["netto_gewinn"] >= a["freigrenze"]:
            st.warning(f"⚠️ Freigrenze überschritten → voller Betrag von "
                       f"{e(a['netto_gewinn'])} steuerpflichtig.")
        if a["rewards_summe"] > 0:
            txt = (f"Rewards/Staking: {e(a['rewards_summe'])} → "
                   f"{'steuerpflichtig (§ 22 Nr. 3, Freigrenze 256 € überschritten)' if a['rewards_steuerpflichtig'] else 'unter 256 €-Freigrenze, steuerfrei'}")
            st.info(txt)

    for h in ss.crypto_cfd_hinweise:
        st.error(f"📉 {h}")
    for w in ss.crypto_results["warnungen"]:
        st.warning(w)

    # ------------------------------------------------------------ Tabellen
    with st.expander(f"Alle Veräußerungen ({len(disposals)})"):
        st.dataframe(pd.DataFrame([{
            "Inhaber": personen.get(d.inhaber, d.inhaber), "Asset": d.asset,
            "Menge": d.menge, "Kauf": d.kauf_ts.strftime("%d.%m.%Y"),
            "Verkauf": d.verkauf_ts.strftime("%d.%m.%Y"),
            "Haltetage": d.haltetage, "Gewinn €": d.gewinn,
            "Gebühren €": d.gebuehren_eur,
            "Steuerfrei": "✅" if d.steuerfrei else "❌",
            "Depot": d.depot} for d in disposals]),
            use_container_width=True)

    # ------------------------------------------------------------ Optimizer
    st.subheader("⏳ Haltefrist-Optimizer (offene Bestände)")
    tipps = optimizer_hinweise(open_lots)
    if tipps:
        for t in tipps:
            st.info(t)
        st.dataframe(pd.DataFrame([{
            "Inhaber": personen.get(l.inhaber, l.inhaber), "Asset": l.asset,
            "Menge": l.menge, "Gekauft": l.kauf_ts.strftime("%d.%m.%Y"),
            "Kosten €": l.kosten_eur,
            "Steuerfrei ab": l.steuerfrei_ab.strftime("%d.%m.%Y"),
            "Resttage": l.resttage, "Depot": l.depot} for l in open_lots]),
            use_container_width=True)
    else:
        st.caption("Keine offenen Lots aus den importierten Daten erkennbar "
                   "(eToro liefert nur geschlossene Positionen).")

    # ------------------------------------------------------------ Steuer
    st.subheader("💶 Steuerschätzung (§ 32a EStG)")
    splitting = interview.get("zusammenveranlagung", True)
    zve = st.number_input(
        "Zu versteuerndes Einkommen OHNE Krypto (gemeinsam, geschätzt)",
        0.0, 1_000_000.0, float(interview.get("zve_schaetzung") or 60000.0),
        step=1000.0,
        help="Grob: Bruttolöhne beider Ehegatten − Werbungskosten − "
             "Vorsorgeaufwand. Genauer Wert steht später im Steuerbescheid.")
    interview["zve_schaetzung"] = zve
    stpfl_gesamt = sum(agg[p]["steuerpflichtiger_betrag"] +
                       agg[p]["rewards_steuerpflichtig"] for p in ("P1", "P2"))
    if stpfl_gesamt > 0:
        est = steuer_auf_krypto(zve, stpfl_gesamt, cfg, splitting)
        c1, c2, c3 = st.columns(3)
        c1.metric("Steuerpflichtige Krypto-Einkünfte", e(stpfl_gesamt))
        c2.metric("Geschätzte Mehrsteuer", e(est["mehrsteuer"]),
                  help="Zzgl. ggf. Kirchensteuer (9 % der ESt-Differenz).")
        c3.metric("Grenzsteuersatz", f"{est['grenzsteuersatz_prozent']} %")
        st.caption(f"Tarif {cfg['jahr']}, "
                   f"{'Splitting' if splitting else 'Einzelveranlagung'} – "
                   "Schätzung ohne Soli/Kirchensteuer/sonstige Abzüge.")
    else:
        st.success("🎉 Nach aktueller Datenlage fällt auf Krypto KEINE "
                   "Steuer an (Haltefristen/Freigrenzen greifen).")

    # ------------------------------------------------------------ Report
    st.divider()
    if st.button("📑 Prüfungsfesten Steuerreport (PDF) erstellen",
                 use_container_width=True):
        import uuid
        from .report import erstelle_report
        # Eindeutiger Dateiname gegen Kollisionen bei mehreren gleichzeitigen
        # Nutzern/Sessions auf demselben Rechner (z. B. lokale Entwicklung) –
        # der Download-Dateiname bleibt für den Nutzer unverändert sauber.
        pfad = f"/tmp/krypto_steuerreport_{cfg['jahr']}_{uuid.uuid4().hex[:8]}.pdf"
        erstelle_report(pfad, cfg["jahr"], personen, agg, disposals,
                        open_lots, ss.crypto_results["warnungen"],
                        interview.get("stammdaten"))
        with open(pfad, "rb") as f:
            st.download_button(
                "⬇️ Report herunterladen (Anlage zur Steuererklärung)",
                f.read(), file_name=f"Krypto-Steuerreport_{cfg['jahr']}.pdf",
                mime="application/pdf", use_container_width=True)
        st.caption("Mit Methodik-Seite (BMF-Schreiben 06.03.2025, "
                   "walletbezogene FIFO), Einzelaufstellung und Beständen – "
                   "dieselbe Struktur, wegen der kommerzielle Reports "
                   "akzeptiert werden.")
