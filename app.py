"""
Steuer-Assistent – Einkommensteuererklärung (Bonn, NRW)
Start:  streamlit run app.py
"""

import os

import streamlit as st

from core.betrieb_ui import render_betrieb_tab
from core.checks import run_checks
from core.dokumente_ui import render_dokumente_tab
from core.elster_export import build_summary, export_json, render_elster_help
from core.tax_config import DEFAULT_YEAR, TAX_YEARS, VISION_MODEL, get_config
from core.crypto_ui import render_crypto_tab, _st_init
from core.erklaerungen import GLOSSAR, STEUER_101, frag_steuerberater
from core.jahr_zuordnung import docs_im_jahr, jahres_uebersicht
from core.persist import load_state, save_state
from core.sparcheck import render_sparcheck
from core.veranlagung import berechne_veranlagung
from core.wizard import render_wizard

st.set_page_config(page_title="Steuer-Assistent", page_icon="🧾", layout="wide")

# ---------------------------------------------------------------- State
if "docs" not in st.session_state:
    st.session_state.docs = []            # analysierte Dokumente
if "analyzed_files" not in st.session_state:
    st.session_state.analyzed_files = set()
if "interview" not in st.session_state:
    st.session_state.interview = {}

# Nach "Projekt laden" (persist.load_state): Widget-State auf die geladenen
# Daten setzen, sonst überschreibt alter Widget-State Namen und Zuordnungen.
# MUSS vor der ersten Widget-Instanziierung laufen (sonst APIException).
if st.session_state.pop("_widget_sync", False):
    _iv = st.session_state.interview
    st.session_state["w_veranlagung"] = (
        "Zusammenveranlagung (verheiratet)"
        if _iv.get("zusammenveranlagung", True) else "Einzelveranlagung")
    _pers = _iv.get("personen", {})
    st.session_state["w_name_p1"] = _pers.get("P1", "Andre")
    st.session_state["w_name_p2"] = _pers.get("P2", "Ehepartnerin")
    _prefixe = ("inh_", "cat_", "amt_", "jahr_", "pjahr_", "sp_", "km_",
                "at_", "ho_", "tg_", "tv_", "bz_", "sid_", "rel_")
    for _k in [k for k in st.session_state.keys()
               if isinstance(k, str) and k.startswith(_prefixe)]:
        del st.session_state[_k]

# ---------------------------------------------------------------- Sidebar
with st.sidebar:
    st.title("🧾 Steuer-Assistent")
    st.caption("Einkommensteuer · Bonn, NRW")

    modus = st.radio(
        "Wie möchtest du arbeiten?",
        ["🧙 Einfach (Schritt für Schritt)", "🛠️ Experte (alle Tabs)"],
        help="Der einfache Modus führt dich in 4 Schritten durch – "
             "der Experten-Modus zeigt alle Tabs und Detailfelder auf "
             "einmal.")
    einfacher_modus = modus.startswith("🧙")

    with st.expander("🛠️ Für Fortgeschrittene (Jahr, Pauschbeträge)",
                     expanded=not einfacher_modus):
        year_options = sorted(TAX_YEARS.keys(), reverse=True)
        extra_year = st.checkbox("Anderes Jahr eingeben")
        if extra_year:
            year = st.number_input("Steuerjahr", 2020, 2035, DEFAULT_YEAR,
                                   step=1)
        else:
            year = st.selectbox("Steuerjahr", year_options,
                                index=year_options.index(DEFAULT_YEAR))
    cfg = get_config(int(year))

    try:
        _secret_key = st.secrets.get("ANTHROPIC_API_KEY")
    except Exception:  # noqa: BLE001 – keine secrets.toml vorhanden
        _secret_key = None
    _vorkonfigurierter_key = os.environ.get("ANTHROPIC_API_KEY") or _secret_key
    if _vorkonfigurierter_key:
        api_key = _vorkonfigurierter_key
        st.caption("✅ Anthropic API-Key ist konfiguriert.")
    else:
        api_key = st.text_input(
            "Anthropic API-Key", type="password",
            help="Wird nur lokal verwendet. Alternativ Umgebungsvariable "
                 "ANTHROPIC_API_KEY setzen.")
    if not einfacher_modus:
        model = st.text_input("Vision-Modell", VISION_MODEL)
    else:
        model = VISION_MODEL

    st.divider()
    erklaermodus = st.toggle("🎓 Erklär-Modus (für Steuer-Einsteiger)",
                             value=True,
                             help="Zeigt überall verständliche Erklärungen "
                                  "in Alltagssprache an.")
    st.session_state.setdefault("w_veranlagung",
                                "Zusammenveranlagung (verheiratet)")
    veranlagung = st.radio("Veranlagung", ["Zusammenveranlagung (verheiratet)",
                                           "Einzelveranlagung"],
                           key="w_veranlagung")
    st.session_state.interview["zusammenveranlagung"] = \
        veranlagung.startswith("Zusammen")
    _pers_default = st.session_state.interview.get("personen", {})
    st.session_state.setdefault("w_name_p1", _pers_default.get("P1", "Andre"))
    st.session_state.setdefault("w_name_p2",
                                _pers_default.get("P2", "Ehepartnerin"))
    name_p1 = st.text_input("Person 1", key="w_name_p1")
    name_p2 = st.text_input("Person 2 (Ehepartner/in)", key="w_name_p2",
                            disabled=not veranlagung.startswith("Zusammen"))
    personen = {"P1": name_p1 or "Person 1", "P2": name_p2 or "Person 2"}
    st.session_state.interview["personen"] = personen

    _uebersicht = jahres_uebersicht(st.session_state.docs)
    if _uebersicht:
        st.caption("📦 Belege: " + " · ".join(
            f"{j}: {n}" for j, n in sorted(_uebersicht.items()) if j))
    st.divider()
    _st_init()
    with st.expander("💾 Projektstand speichern/laden & Pauschbeträge",
                     expanded=not einfacher_modus):
        st.markdown("**💾 Projektstand**")
        st.download_button(
            "Speichern (JSON)",
            save_state(st.session_state, int(year), personen),
            file_name=f"steuerprojekt_{int(year)}.json",
            mime="application/json", use_container_width=True)
        geladen = st.file_uploader("Projekt laden", type=["json"],
                                   key="proj_load")
        if geladen and st.button("📂 Stand wiederherstellen",
                                 use_container_width=True):
            meta = load_state(st.session_state, geladen.getvalue())
            st.success(f"Stand vom {meta.get('gespeichert', '?')} geladen "
                       f"(Jahr {meta.get('jahr')}).")
            st.rerun()

        st.divider()
        st.markdown(
            f"**Pauschbeträge {cfg['jahr']}**\n\n"
            f"- Grundfreibetrag: {cfg['grundfreibetrag']:,} €\n"
            f"- AN-Pauschbetrag: {cfg['arbeitnehmer_pauschbetrag']:,} €\n"
            f"- Sparer-Pauschbetrag: {cfg['sparer_pauschbetrag']:,} €\n"
            f"- § 23-Freigrenze: {cfg['freigrenze_private_veraeusserung']:,} €\n"
            f"- Abgabefrist: {cfg['abgabefrist_hinweis']}".replace(",", "."))
        if not cfg.get("_geprueft", True):
            st.warning(f"Werte basieren auf {cfg['_basisjahr']} – bitte in "
                       "`core/tax_config.py` für dieses Jahr pflegen.")
    st.divider()
    st.caption("⚠️ Dieses Tool ersetzt keine Steuerberatung (§ 5 StBerG). "
               "Alle Werte vor Abgabe in ELSTER gegenprüfen.")

def _docs_im_jahr():
    return docs_im_jahr(st.session_state.docs, cfg["jahr"])


if einfacher_modus:
    render_wizard(cfg, api_key, model, st.session_state.interview, personen,
                 erklaermodus)
    st.stop()

(tab_docs, tab_crypto, tab_betrieb, tab_check, tab_spar, tab_elster,
 tab_basics) = st.tabs(
    ["📄 1 · Dokumente", "₿ 2 · Krypto", "🏭 3 · Betrieb",
     "❓ 4 · Fragebogen & Prüfung", "💰 5 · Spar-Check",
     "🧮 6 · Ergebnis & ELSTER", "📖 7 · Verstehen & Fragen"])

with tab_spar:
    render_sparcheck(st.session_state.interview, personen)

with tab_crypto:
    render_crypto_tab(cfg, api_key, model, st.session_state.interview,
                      personen)

with tab_betrieb:
    render_betrieb_tab(cfg, st.session_state.interview, personen)

# ---------------------------------------------------------------- Tab 1
with tab_docs:
    render_dokumente_tab(cfg, api_key, model, personen, erklaermodus)

# ---------------------------------------------------------------- Tab 2
with tab_check:
    iv = st.session_state.interview
    zusammen = iv.get("zusammenveranlagung", True)
    aktive = ("P1", "P2") if zusammen else ("P1",)

    with st.expander("🪪 Stammdaten (für ELSTER-Hauptvordruck)",
                     expanded=not iv.get("stammdaten")):
        sd = iv.setdefault("stammdaten", {})
        c1, c2 = st.columns(2)
        with c1:
            sd["finanzamt"] = st.text_input(
                "Finanzamt", sd.get("finanzamt", "Finanzamt Bonn-Innenstadt"))
            sd["steuernummer"] = st.text_input(
                "Gemeinsame Steuernummer (Format NRW: 5FF/BBB/UUUUP)",
                sd.get("steuernummer", ""))
            sd["iban"] = st.text_input("IBAN für Erstattung",
                                       sd.get("iban", ""))
        with c2:
            for p_key in aktive:
                sd[f"steuer_id_{p_key}"] = st.text_input(
                    f"Steuer-ID {personen[p_key]} (11-stellig)",
                    sd.get(f"steuer_id_{p_key}", ""), key=f"sid_{p_key}")
                sd[f"religion_{p_key}"] = st.selectbox(
                    f"Religion {personen[p_key]}",
                    ["keine/andere (VD)", "ev", "rk"],
                    ["keine/andere (VD)", "ev", "rk"].index(
                        sd.get(f"religion_{p_key}", "keine/andere (VD)")),
                    key=f"rel_{p_key}")

    st.subheader("Fragebogen – Wege zur Arbeit (je Person)")
    cols = st.columns(len(aktive))
    for col, p_key in zip(cols, aktive):
        with col:
            st.markdown(f"**{personen[p_key]}**")
            iv[f"entfernung_km_{p_key}"] = st.number_input(
                "Einfache Entfernung (km)", 0.0, 300.0,
                float(iv.get(f"entfernung_km_{p_key}") or 0.0), step=1.0,
                key=f"km_{p_key}")
            iv[f"arbeitstage_{p_key}"] = st.number_input(
                "Tage mit Fahrt zur Arbeit", 0, 366,
                int(iv.get(f"arbeitstage_{p_key}") or 0), key=f"at_{p_key}")
            iv[f"homeoffice_tage_{p_key}"] = st.number_input(
                "Homeoffice-Tage", 0, 366,
                int(iv.get(f"homeoffice_tage_{p_key}") or 0),
                key=f"ho_{p_key}")

    st.subheader("Weitere Angaben")
    c1, c2, c3 = st.columns(3)
    with c1:
        kirche = st.radio("Kirchensteuerpflichtig?", ["Nein", "Ja"],
                          index=1 if iv.get("kirchensteuerpflichtig") else 0,
                          horizontal=True)
        iv["kirchensteuerpflichtig"] = kirche == "Ja"
        iv["kirchensteuerpflichtig_beantwortet"] = True
        kinder = st.radio("Kinder?", ["Nein", "Ja"],
                          index=1 if iv.get("hat_kinder") else 0,
                          horizontal=True)
        iv["hat_kinder"] = kinder == "Ja"
        if iv["hat_kinder"]:
            iv["kinder_anzahl"] = st.number_input(
                "Anzahl Kinder (Kindergeld-Anspruch)", 0, 15,
                int(iv.get("kinder_anzahl") or 0),
                help="Wirkt auf die zumutbare Belastung (§ 33 Abs. 3 EStG) "
                     "und die Riester-Kinderzulage.")
    with c2:
        iv["hat_bundeswehr"] = st.checkbox(
            "Übergangsgebührnisse Bundeswehr (2. Arbeitsverhältnis)?",
            value=bool(iv.get("hat_bundeswehr", True)),
            help="Abwählen, wenn das Tool für jemanden ohne "
                 "Bundeswehr-Bezüge genutzt wird.")
        iv["hat_krypto_verkauft"] = st.checkbox(
            f"In {cfg['jahr']} Krypto verkauft/getauscht?",
            value=bool(iv.get("hat_krypto_verkauft")))
        iv["hat_etf"] = st.checkbox(
            "ETFs/Fonds im Depot", value=bool(iv.get("hat_etf")))
        iv["guenstigerpruefung"] = st.checkbox(
            "Günstigerprüfung (KAP) beantragen",
            value=bool(iv.get("guenstigerpruefung", True)))
    with c3:
        iv["auslandsbezug"] = st.checkbox(
            "Wohnsitz/Einkünfte im Ausland (z. B. Österreich)?",
            value=bool(iv.get("auslandsbezug")))

    st.markdown("**Habt ihr Einnahmen aus einem Betrieb, Nebengewerbe, "
               "Photovoltaik/Energieverkauf oder freiberuflicher Tätigkeit?**")
    cols_betrieb = st.columns(len(aktive))
    for col, p_key in zip(cols_betrieb, aktive):
        iv[f"hat_betrieb_{p_key}"] = col.checkbox(
            personen[p_key], value=bool(iv.get(f"hat_betrieb_{p_key}")),
            key=f"hb_{p_key}")
    if any(iv.get(f"hat_betrieb_{p}") for p in aktive):
        st.caption("➡️ Betrieb im Tab 🏭 3 · Betrieb anlegen und Belege dort "
                  "(bzw. in Tab 1) zuordnen.")

    with st.expander("📉 Verlustvorträge aus Vorjahren (lt. Feststellungs-/"
                     "Steuerbescheid)"):
        v1, v2, v3 = st.columns(3)
        iv["verlustvortrag_23"] = v1.number_input(
            "§ 23 / Krypto (€)", 0.0, 10_000_000.0,
            float(iv.get("verlustvortrag_23") or 0.0), step=100.0)
        iv["verlustvortrag_kap_aktien"] = v2.number_input(
            "KAP Aktienverluste (€)", 0.0, 10_000_000.0,
            float(iv.get("verlustvortrag_kap_aktien") or 0.0), step=100.0)
        iv["verlustvortrag_kap_sonstige"] = v3.number_input(
            "KAP sonstige Verluste (€)", 0.0, 10_000_000.0,
            float(iv.get("verlustvortrag_kap_sonstige") or 0.0), step=100.0)

    with st.expander("🦽 Behinderung, Pflege & Unterhalt (§ 33b, § 33a EStG "
                     "– Pauschbeträge OHNE zumutbare Belastung)"):
        st.caption("Diese Beträge wirken sofort und ungekürzt – anders als "
                   "normale Krankheitskosten im Spar-Check.")
        bcols = st.columns(len(aktive))
        gdb_stufen = [0, 20, 30, 40, 50, 60, 70, 80, 90, 100]
        for col, p_key in zip(bcols, aktive):
            with col:
                st.markdown(f"**{personen[p_key]}**")
                iv[f"gdb_{p_key}"] = st.selectbox(
                    "Grad der Behinderung (GdB)", gdb_stufen,
                    gdb_stufen.index(int(iv.get(f"gdb_{p_key}") or 0))
                    if int(iv.get(f"gdb_{p_key}") or 0) in gdb_stufen else 0,
                    key=f"gdb_sel_{p_key}",
                    help="Ab GdB 20 gibt es einen Pauschbetrag ohne "
                         "Einzelnachweis (§ 33b EStG).")
                if iv[f"gdb_{p_key}"] >= 20:
                    iv[f"gdb_hilflos_blind_{p_key}"] = st.checkbox(
                        "Merkzeichen H/Bl/TBl (hilflos/blind)?",
                        value=bool(iv.get(f"gdb_hilflos_blind_{p_key}")),
                        key=f"hb_gdb_{p_key}",
                        help="Ersetzt den GdB-Pauschbetrag durch den "
                             "erhöhten Pauschbetrag von 7.400 €.")
        st.markdown("**Pflege eines Angehörigen (unentgeltlich, häuslich)**")
        pflege_stufen = [0, 2, 3, 4, 5]
        iv["pflegegrad_angehoeriger"] = st.selectbox(
            "Pflegegrad der gepflegten Person", pflege_stufen,
            pflege_stufen.index(int(iv.get("pflegegrad_angehoeriger") or 0))
            if int(iv.get("pflegegrad_angehoeriger") or 0) in pflege_stufen
            else 0, help="0 = keine Pflege. Ab Pflegegrad 2 gibt es einen "
                         "Pauschbetrag (§ 33b Abs. 6 EStG).")
        st.markdown("**Unterhaltsleistungen an bedürftige Personen "
                   "(§ 33a EStG)**")
        u1, u2 = st.columns(2)
        iv["unterhalt_betrag"] = u1.number_input(
            "Gezahlter Unterhalt (€/Jahr)", 0.0, 100_000.0,
            float(iv.get("unterhalt_betrag") or 0.0), step=100.0)
        iv["unterhalt_eigene_einkuenfte"] = u2.number_input(
            "Eigene Einkünfte/Bezüge der unterstützten Person (€/Jahr)",
            0.0, 100_000.0,
            float(iv.get("unterhalt_eigene_einkuenfte") or 0.0), step=100.0,
            help="Übersteigen diese 624 €/Jahr, wird der übersteigende "
                 "Betrag vom Höchstbetrag abgezogen.")

    with st.expander("💰 Riester-Rente (Anlage AV, § 10a EStG – "
                     "Günstigerprüfung Zulage vs. Sonderausgabenabzug)"):
        rcols = st.columns(len(aktive))
        for col, p_key in zip(rcols, aktive):
            iv[f"riester_beitrag_{p_key}"] = col.number_input(
                f"Eigenbeitrag {personen[p_key]} (€/Jahr, inkl. Zulage)",
                0.0, 10_000.0,
                float(iv.get(f"riester_beitrag_{p_key}") or 0.0), step=10.0,
                key=f"riester_b_{p_key}")
        rk1, rk2 = st.columns(2)
        iv["riester_kinder_ab_2008"] = rk1.number_input(
            "Kinder mit Kinderzulage, geboren AB 2008", 0, 15,
            int(iv.get("riester_kinder_ab_2008") or 0))
        iv["riester_kinder_vor_2008"] = rk2.number_input(
            "Kinder mit Kinderzulage, geboren VOR 2008", 0, 15,
            int(iv.get("riester_kinder_vor_2008") or 0))
        st.caption("Das Finanzamt vergleicht automatisch die Steuerersparnis "
                  "durch den Sonderausgabenabzug mit der bereits "
                  "gutgeschriebenen Zulage und zahlt nur den übersteigenden "
                  "Betrag zusätzlich aus (Ergebnis im Rechenweg, Tab "
                  "'Ergebnis & ELSTER').")

    st.divider()
    st.subheader("Automatische Prüfung")
    findings = run_checks(_docs_im_jahr(), cfg, iv)
    st.session_state.findings = findings

    if not st.session_state.docs:
        st.info("Noch keine Dokumente analysiert – die Prüfung wird "
                "aussagekräftiger, sobald Belege vorliegen.")
    order = {"fehler": 0, "warnung": 1, "frage": 2, "hinweis": 3}
    icons = {"fehler": "🛑", "warnung": "⚠️", "frage": "❓", "hinweis": "💡"}
    for f in sorted(findings, key=lambda x: order.get(x["level"], 9)):
        fn = {"fehler": st.error, "warnung": st.warning,
              "frage": st.info, "hinweis": st.success}[f["level"]]
        fn(f"{icons[f['level']]} {f['text']}")

# ---------------------------------------------------------------- Tab 3
with tab_elster:
    e_fmt = lambda v: f"{v:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")
    from datetime import date as _date
    frist = _date.fromisoformat(cfg["abgabefrist_datum"]) \
        if cfg.get("abgabefrist_datum") else None
    v = berechne_veranlagung(_docs_im_jahr(), cfg,
                             st.session_state.interview)
    c1, c2, c3 = st.columns(3)
    if frist:
        rest = (frist - _date.today()).days
        c1.metric("⏰ Abgabefrist", frist.strftime("%d.%m.%Y"),
                  f"noch {rest} Tage" if rest >= 0
                  else f"{-rest} Tage überfällig!",
                  delta_color="normal" if rest > 45 else "inverse")
    if v["hat_lsb"]:
        erg = v["ergebnis"]
        c2.metric("💶 Geschätztes Ergebnis", e_fmt(abs(erg)),
                  "Erstattung 🎉" if erg >= 0 else "Nachzahlung",
                  delta_color="normal" if erg >= 0 else "inverse")
        c3.metric("zvE (geschätzt)", e_fmt(v["zve"]),
                  help="Zu versteuerndes Einkommen nach allen Abzügen.")
        with st.expander("🧮 Rechenweg der Schätzung anzeigen"):
            for schritt in v["schritte"]:
                st.markdown(f"- {schritt['text']}: **{e_fmt(schritt['wert'])}**")
            for w in v["warnhinweise"]:
                st.caption("⚠️ " + w)
            st.caption("Schätzung ohne Gewähr – der Steuerbescheid des "
                       "Finanzamts ist maßgeblich. Kirchensteuer/Soli "
                       "vereinfacht, Kinderfreibeträge nicht simuliert "
                       "(Kindergeld ist meist günstiger).")
    else:
        c2.info("Für die Erstattungsschätzung zuerst die "
                "Lohnsteuerbescheinigungen hochladen (Tab 1).")
    st.divider()
    st.subheader("Zusammenfassung & ELSTER-Eingabehilfe")
    if not _docs_im_jahr() and not st.session_state.interview.get("_crypto"):
        st.info("Lade zuerst Dokumente hoch (Tab 1) oder importiere "
                "Krypto-Daten (Tab 2).")
    else:
        summary = build_summary(_docs_im_jahr(), cfg,
                                st.session_state.interview)
        help_md = render_elster_help(summary, erklaeren=erklaermodus)
        st.markdown(help_md)
        st.divider()
        c1, c2 = st.columns(2)
        with c1:
            st.download_button(
                "⬇️ ELSTER-Hilfe (Markdown)", help_md,
                file_name=f"elster_hilfe_{cfg['jahr']}.md",
                mime="text/markdown", use_container_width=True)
        with c2:
            st.download_button(
                "⬇️ Rohdaten (JSON)",
                export_json(summary, st.session_state.docs,
                            st.session_state.get("findings", [])),
                file_name=f"steuerdaten_{cfg['jahr']}.json",
                mime="application/json", use_container_width=True)
        st.caption("Nächster Schritt: In **elster.de** anmelden, Belegabruf "
                   "aktivieren, Werte übertragen und abgleichen, absenden.")


# ---------------------------------------------------------------- Tab 5
with tab_basics:
    st.markdown(STEUER_101)
    st.divider()

    st.subheader("📚 Glossar – Begriffe einfach erklärt")
    suche = st.text_input("Begriff suchen", "",
                          placeholder="z. B. Freigrenze, FIFO, Pauschbetrag")
    treffer = {k: v for k, v in GLOSSAR.items()
               if not suche or suche.lower() in k.lower()
               or suche.lower() in v.lower()}
    for begriff, text in treffer.items():
        with st.expander(begriff):
            st.write(text)
    if not treffer:
        st.info("Kein Treffer – frag einfach unten im Chat!")

    st.divider()
    st.subheader("💬 Frag nach – dein Steuer-Erklärer")
    st.caption("Stell jede Frage in Alltagssprache. Claude antwortet mit "
               "deinen echten Zahlen als Beispiel. (Bildung, keine "
               "verbindliche Steuerberatung.)")
    st.session_state.setdefault("chat_verlauf", [])
    for msg in st.session_state.chat_verlauf:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
    frage = st.chat_input("z. B.: Warum ist die Freigrenze so gemein? "
                          "Lohnt sich mein Monitor-Beleg?")
    if frage:
        if not api_key:
            st.warning("Bitte zuerst den API-Key in der Seitenleiste "
                       "eintragen.")
        else:
            with st.chat_message("user"):
                st.markdown(frage)
            kontext = ""
            try:
                _sum = build_summary(_docs_im_jahr(), cfg,
                                     st.session_state.interview)
                kontext = export_json(_sum, _docs_im_jahr(),
                                      st.session_state.get("findings", []))
            except Exception:  # noqa: BLE001
                pass
            with st.chat_message("assistant"):
                with st.spinner("Denke nach …"):
                    try:
                        antwort = frag_steuerberater(
                            frage, kontext[:60000],
                            st.session_state.chat_verlauf, api_key, model)
                    except Exception as exc:  # noqa: BLE001
                        antwort = f"Fehler bei der Anfrage: {exc}"
                    st.markdown(antwort)
            st.session_state.chat_verlauf += [
                {"role": "user", "content": frage},
                {"role": "assistant", "content": antwort}]
