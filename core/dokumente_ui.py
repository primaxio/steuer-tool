"""Streamlit-Tab 'Dokumente' – Upload, Claude-Analyse, Zuordnung/Korrektur.
Ausgelagert aus app.py, damit sowohl der Experten-Tab als auch der
Einfache-Modus-Wizard dieselbe Logik nutzen (keine Duplikate)."""

from datetime import datetime

import streamlit as st

from . import categories as cat
from .erklaerungen import KATEGORIE_ERKLAERUNG, klaerungs_chat
from .jahr_zuordnung import (bestimme_steuerjahr, docs_im_jahr,
                             ist_im_jahr, jahres_uebersicht)
from .vision import SUPPORTED_IMAGE_TYPES, analyze_document


def _historie_eintrag(d: dict, aktion: str, von, nach, quelle: str,
                      begruendung: str = ""):
    d.setdefault("zuordnungs_historie", []).append({
        "zeitpunkt": datetime.now().isoformat(timespec="seconds"),
        "aktion": aktion, "von": von, "nach": nach, "quelle": quelle,
        "begruendung": begruendung,
    })


def _uebernehme_chat_vorschlag(d: dict, v: dict):
    """Wendet den Klärungs-Chat-Vorschlag an, protokolliert die
    Zuordnungs-Historie und deaktiviert den Klärungsbedarf."""
    alte_kategorie = d.get("kategorie")
    begruendung = v.get("begruendung") or "Per Chat geklärt."
    if v.get("kategorie") and v["kategorie"] in cat.category_options():
        d["kategorie"] = v["kategorie"]
        d["confidence"] = 1.0
    if v.get("inhaber") in ("P1", "P2"):
        d["inhaber"] = v["inhaber"]
    if v.get("betrieb"):
        d["betrieb"] = v["betrieb"]
    if v.get("steuerjahr"):
        try:
            d["steuerjahr_zuordnung"] = int(v["steuerjahr"])
        except (TypeError, ValueError):
            pass
    if v.get("betrag_eur") is not None:
        d["betrag_eur"] = v["betrag_eur"]
    d["klaerungsbedarf"] = False
    _historie_eintrag(d, "Chat-Klärung", alte_kategorie, d.get("kategorie"),
                      "chat", begruendung)
    d.setdefault("hinweise", []).append(
        f"Zuordnung per Chat bestätigt: {begruendung}")


def _render_klaerung_bereich(api_key: str, model: str, personen: dict):
    unklare = [d for d in st.session_state.docs if d.get("klaerungsbedarf")]
    if not unklare:
        return
    st.subheader(f"❓ Klärung nötig ({len(unklare)})")
    st.caption("Diese Belege konnten nicht sicher automatisch eingeordnet "
               "werden. Chatte kurz mit dem Steuerberater-Assistenten – "
               "danach wird der Beleg automatisch richtig einsortiert.")
    for d in unklare:
        conf = d.get("confidence") or 0
        with st.expander(f"❓ {d['dateiname']} → aktuell "
                         f"{cat.label_of(d['kategorie'])} ({conf:.0%})"):
            st.markdown(
                f"**Typ:** {d.get('dokumenttyp', '–')}  \n"
                f"**Aussteller:** {d.get('aussteller') or '–'}  \n"
                f"**Betrag:** "
                f"{d.get('betrag_eur') if d.get('betrag_eur') is not None else '–'} €")
            for q in d.get("rueckfragen", []):
                st.info(f"❓ {q}")

            verlauf_key = f"klaerchat_{d['dateiname']}"
            st.session_state.setdefault(verlauf_key, [])
            verlauf = st.session_state[verlauf_key]
            for msg in verlauf:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])

            frage = st.chat_input(
                "Antworte hier, um den Beleg zuzuordnen …",
                key=f"ci_{d['dateiname']}", disabled=not api_key)
            if frage:
                verlauf.append({"role": "user", "content": frage})
                with st.spinner("Denke nach …"):
                    try:
                        result = klaerungs_chat(
                            d, frage, verlauf[:-1], api_key, model, personen,
                            st.session_state.get("betriebe", []))
                    except Exception as exc:  # noqa: BLE001
                        result = {"antwort": f"Fehler bei der Anfrage: {exc}",
                                  "sicher": False, "vorschlag": {}}
                verlauf.append({"role": "assistant",
                               "content": result.get("antwort", "")})
                st.session_state[f"{verlauf_key}_vorschlag"] = result
                st.rerun()
            if not api_key:
                st.caption("API-Key in der Seitenleiste eintragen, um zu chatten.")

            letzter = st.session_state.get(f"{verlauf_key}_vorschlag")
            if letzter and letzter.get("sicher"):
                v = letzter.get("vorschlag", {})
                st.success(
                    f"**Vorschlag:** "
                    f"{cat.label_of(v['kategorie']) if v.get('kategorie') else '–'} "
                    f"· {personen.get(v.get('inhaber'), '–')} "
                    f"· Jahr {v.get('steuerjahr') or '–'} "
                    f"· {v.get('betrag_eur') if v.get('betrag_eur') is not None else '–'} €"
                    f"\n\n_{v.get('begruendung', '')}_")
                if st.button("✅ Zuordnung übernehmen",
                             key=f"apply_{d['dateiname']}"):
                    _uebernehme_chat_vorschlag(d, v)
                    st.session_state[f"{verlauf_key}_vorschlag"] = None
                    st.rerun()
    st.divider()


def render_dokumente_tab(cfg: dict, api_key: str, model: str,
                         personen: dict, erklaermodus: bool):
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

    _render_klaerung_bereich(api_key, model, personen)

    if st.session_state.docs:
        st.divider()
        docs_aktuell = docs_im_jahr(st.session_state.docs, cfg["jahr"])
        docs_andere = [d for d in st.session_state.docs
                       if not ist_im_jahr(d, cfg["jahr"])]
        st.subheader(f"Belege für Steuerjahr {cfg['jahr']} "
                     f"({len(docs_aktuell)})")
        if docs_andere:
            uebersicht = jahres_uebersicht(docs_andere)
            st.info("📦 Automatisch sortiert: " + " · ".join(
                f"{n} Beleg(e) → {j}" for j, n in sorted(uebersicht.items())
                if j) + " – in der Seitenleiste das Steuerjahr wechseln, "
                "um sie zu bearbeiten. Gespeichert bleiben alle.")
        for i, d in enumerate(st.session_state.docs):
            if not ist_im_jahr(d, cfg["jahr"]):
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
                        _historie_eintrag(d, "Kategorie manuell korrigiert",
                                         d["kategorie"], new_cat, "manuell")
                        d["kategorie"] = new_cat
                        d["confidence"] = 1.0
                        st.rerun()
                    if d["kategorie"] in ("betrieb_einnahme", "betrieb_ausgabe"):
                        betriebe = st.session_state.get("betriebe", [])
                        if betriebe:
                            namen = [b.name for b in betriebe]
                            aktuell = d.get("betrieb")
                            d["betrieb"] = st.selectbox(
                                "Gehört zu Betrieb", namen,
                                index=namen.index(aktuell)
                                if aktuell in namen else 0,
                                key=f"betr_{i}")
                        else:
                            st.caption("⚠️ Noch kein Betrieb angelegt – "
                                      "im Tab 🏭 Betrieb zuerst anlegen.")
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
                    if not ist_im_jahr(d, cfg["jahr"]):
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
