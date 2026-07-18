"""
Steuer-Assistent – Einkommensteuererklärung (Bonn, NRW)
Start:  streamlit run app.py
"""

import os

import streamlit as st

from core import categories as cat
from core.checks import run_checks
from core.elster_export import build_summary, export_json, render_elster_help
from core.tax_config import DEFAULT_YEAR, TAX_YEARS, VISION_MODEL, get_config
from core.crypto_ui import render_crypto_tab, _st_init
from core.erklaerungen import (GLOSSAR, KATEGORIE_ERKLAERUNG, STEUER_101,
                               frag_steuerberater)
from core.jahr_zuordnung import bestimme_steuerjahr, jahres_uebersicht
from core.persist import load_state, save_state
from core.sparcheck import render_sparcheck
from core.veranlagung import berechne_veranlagung
from core.vision import SUPPORTED_IMAGE_TYPES, analyze_document

st.set_page_config(page_title="Steuer-Assistent", page_icon="🧾", layout="wide")

# ---------------------------------------------------------------- State
if "docs" not in st.session_state:
    st.session_state.docs = []            # analysierte Dokumente
if "analyzed_files" not in st.session_state:
    st.session_state.analyzed_files = set()
if "interview" not in st.session_state:
    st.session_state.interview = {}

# ---------------------------------------------------------------- Sidebar
with st.sidebar:
    st.title("🧾 Steuer-Assistent")
    st.caption("Einkommensteuer · Bonn, NRW")

    year_options = sorted(TAX_YEARS.keys(), reverse=True) 
    extra_year = st.checkbox("Anderes Jahr eingeben")
    if extra_year:
        year = st.number_input("Steuerjahr", 2020, 2035, DEFAULT_YEAR, step=1)
    else:
        year = st.selectbox("Steuerjahr", year_options,
                            index=year_options.index(DEFAULT_YEAR))
    cfg = get_config(int(year))

    api_key = st.text_input(
        "Anthropic API-Key", type="password",
        value=os.environ.get("ANTHROPIC_API_KEY", ""),
        help="Wird nur lokal verwendet. Alternativ Umgebungsvariable "
             "ANTHROPIC_API_KEY setzen.")
    model = st.text_input("Vision-Modell", VISION_MODEL)

    st.divider()
    erklaermodus = st.toggle("🎓 Erklär-Modus (für Steuer-Einsteiger)",
                             value=True,
                             help="Zeigt überall verständliche Erklärungen "
                                  "in Alltagssprache an.")
    veranlagung = st.radio("Veranlagung", ["Zusammenveranlagung (verheiratet)",
                                           "Einzelveranlagung"], index=0)
    st.session_state.interview["zusammenveranlagung"] = \
        veranlagung.startswith("Zusammen")
    name_p1 = st.text_input("Person 1", "Andre")
    name_p2 = st.text_input("Person 2 (Ehepartner/in)", "Ehepartnerin",
                            disabled=not veranlagung.startswith("Zusammen"))
    personen = {"P1": name_p1 or "Person 1", "P2": name_p2 or "Person 2"}
    st.session_state.interview["personen"] = personen

    _uebersicht = jahres_uebersicht(st.session_state.docs)
    if _uebersicht:
        st.caption("📦 Belege: " + " · ".join(
            f"{j}: {n}" for j, n in sorted(_uebersicht.items()) if j))
    st.divider()
    st.markdown("**💾 Projektstand**")
    _st_init()
    st.download_button(
        "Speichern (JSON)",
        save_state(st.session_state, int(year), personen),
        file_name=f"steuerprojekt_{int(year)}.json", mime="application/json",
        use_container_width=True)
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

tab_docs, tab_crypto, tab_check, tab_spar, tab_elster, tab_basics = st.tabs(
    ["📄 1 · Dokumente", "₿ 2 · Krypto", "❓ 3 · Fragebogen & Prüfung",
     "💰 4 · Spar-Check", "🧮 5 · Ergebnis & ELSTER",
     "📖 6 · Verstehen & Fragen"])

def _docs_im_jahr():
    return [d for d in st.session_state.docs
            if int(d.get("steuerjahr_zuordnung", cfg["jahr"]) or cfg["jahr"])
            == cfg["jahr"]]


with tab_spar:
    render_sparcheck(st.session_state.interview, personen)

with tab_crypto:
    render_crypto_tab(cfg, api_key, model, st.session_state.interview,
                      personen)

# ---------------------------------------------------------------- Tab 1
with tab_docs:
    st.subheader("Belege hochladen & automatisch zuordnen")
    st.markdown(
        "Lade **PDFs oder Fotos** hoch – z. B. Lohnsteuerbescheinigungen "
        "(zivil + Bundeswehr), Bank-Steuerbescheinigungen, Krypto-Reports, "
        "Spendenquittungen, Handwerkerrechnungen. Claude erkennt Typ, Beträge "
        "und ordnet sie der richtigen Anlage zu.")

    uploads = st.file_uploader(
        "Dateien auswählen", type=["pdf", "png", "jpg", "jpeg", "webp"],
        accept_multiple_files=True)

    new_files = [u for u in uploads or []
                 if u.name not in st.session_state.analyzed_files]

    if new_files and st.button(
            f"🔍 {len(new_files)} neue(s) Dokument(e) analysieren",
            type="primary", disabled=not api_key):
        progress = st.progress(0.0)
        for i, up in enumerate(new_files):
            mime = up.type if up.type in SUPPORTED_IMAGE_TYPES | \
                {"application/pdf"} else "application/pdf"
            try:
                result = analyze_document(
                    up.getvalue(), mime, up.name, api_key, cfg["jahr"], model)
                zuordnung = bestimme_steuerjahr(result)
                if zuordnung is None:
                    zuordnung = cfg["jahr"]
                    result["rueckfragen"].append(
                        "Kein Datum erkennbar – Beleg wurde dem aktuellen "
                        f"Steuerjahr {cfg['jahr']} zugeordnet, bitte prüfen.")
                result["steuerjahr_zuordnung"] = zuordnung
                st.session_state.docs.append(result)
                st.session_state.analyzed_files.add(up.name)
            except Exception as exc:  # noqa: BLE001
                st.error(f"Fehler bei '{up.name}': {exc}")
            progress.progress((i + 1) / len(new_files))
        st.rerun()
    if new_files and not api_key:
        st.info("Bitte zuerst den API-Key in der Seitenleiste eintragen.")

    if st.session_state.docs:
        st.divider()
        docs_aktuell = _docs_im_jahr()
        docs_andere = [d for d in st.session_state.docs
                       if d not in docs_aktuell]
        st.subheader(f"Belege für Steuerjahr {cfg['jahr']} "
                     f"({len(docs_aktuell)})")
        if docs_andere:
            uebersicht = jahres_uebersicht(docs_andere)
            st.info("📦 Automatisch sortiert: " + " · ".join(
                f"{n} Beleg(e) → {j}" for j, n in sorted(uebersicht.items())
                if j) + " – in der Seitenleiste das Steuerjahr wechseln, "
                "um sie zu bearbeiten. Gespeichert bleiben alle.")
        for i, d in enumerate(st.session_state.docs):
            im_jahr = d in docs_aktuell
            if not im_jahr:
                continue
            conf = d.get("confidence") or 0
            icon = "🟢" if conf >= 0.85 else ("🟡" if conf >= 0.7 else "🔴")
            with st.expander(
                    f"{icon} {d['dateiname']} → "
                    f"{cat.label_of(d['kategorie'])} "
                    f"({conf:.0%})"):
                c1, c2 = st.columns([2, 1])
                with c1:
                    st.markdown(
                        f"**Typ:** {d.get('dokumenttyp', '–')}  \n"
                        f"**Aussteller:** {d.get('aussteller') or '–'}  \n"
                        f"**Datum:** {d.get('datum') or '–'} · "
                        f"**Jahr:** {d.get('steuerjahr') or '–'}  \n"
                        f"**Hauptbetrag:** "
                        f"{d.get('betrag_eur') if d.get('betrag_eur') is not None else '–'} €  \n"
                        f"**Anlage:** {cat.anlage_of(d['kategorie'])}")
                    if erklaermodus:
                        st.caption("🎓 " + KATEGORIE_ERKLAERUNG.get(
                            d["kategorie"], ""))
                    if d.get("extrahierte_daten"):
                        st.json(d["extrahierte_daten"], expanded=False)
                    for h in d.get("hinweise", []):
                        st.warning(h)
                    for q in d.get("rueckfragen", []):
                        st.info(f"❓ {q}")
                with c2:
                    inh = st.selectbox(
                        "Gehört zu", ["P1", "P2"],
                        index=0 if d.get("inhaber", "P1") == "P1" else 1,
                        format_func=lambda k: personen.get(k, k),
                        key=f"inh_{i}")
                    d["inhaber"] = inh
                    keys = cat.category_options()
                    new_cat = st.selectbox(
                        "Kategorie korrigieren", keys,
                        index=keys.index(d["kategorie"]),
                        format_func=cat.label_of, key=f"cat_{i}")
                    if new_cat != d["kategorie"]:
                        d["kategorie"] = new_cat
                        d["confidence"] = 1.0
                        st.rerun()
                    d["steuerjahr_zuordnung"] = st.number_input(
                        "Steuerjahr", 2020, 2035,
                        int(d.get("steuerjahr_zuordnung", cfg["jahr"])),
                        key=f"jahr_{i}",
                        help="Automatisch nach Zahlungsdatum sortiert "
                             "(Abflussprinzip) – hier korrigierbar.")
                    new_betrag = st.number_input(
                        "Betrag (€) korrigieren",
                        value=float(d.get("betrag_eur") or 0.0),
                        key=f"amt_{i}")
                    if new_betrag != (d.get("betrag_eur") or 0.0):
                        d["betrag_eur"] = new_betrag
                    if st.button("🗑️ Entfernen", key=f"del_{i}"):
                        st.session_state.analyzed_files.discard(d["dateiname"])
                        st.session_state.docs.pop(i)
                        st.rerun()

        if docs_andere:
            with st.expander(f"📦 Geparkte Belege anderer Jahre "
                             f"({len(docs_andere)})"):
                for i, d in enumerate(st.session_state.docs):
                    if d in docs_andere:
                        c1, c2 = st.columns([3, 1])
                        c1.markdown(
                            f"`{d['dateiname']}` – "
                            f"{cat.label_of(d['kategorie'])}, "
                            f"{d.get('datum') or '–'}")
                        d["steuerjahr_zuordnung"] = c2.number_input(
                            "Jahr", 2020, 2035,
                            int(d.get("steuerjahr_zuordnung",
                                      cfg["jahr"])),
                            key=f"pjahr_{i}", label_visibility="collapsed")

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
