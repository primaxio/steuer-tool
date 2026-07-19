"""Streamlit-Tab '🏭 Betrieb' – Betriebe anlegen/verwalten, EÜR-Übersicht,
Einnahmen-/Ausgabenliste (aus gescannten Belegen automatisch befüllt,
manuell ergänzbar) und AfA-Tabelle."""

import re
from datetime import date

import pandas as pd
import streamlit as st

from .betrieb import ARTEN, AfaPosition, Betrieb, Position, berechne_euer
from .checks import _num

_DATUM_RE = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4})")


def _st_init():
    st.session_state.setdefault("betriebe", [])


def _datum_aus_doc(d: dict, fallback_jahr: int) -> str:
    """Beleg-Datum (dt. Format) → ISO. Fällt auf 1.1. des Steuerjahres
    zurück, wenn kein eindeutiges Tagesdatum erkennbar ist (Zeitraum o. Ä.)
    – für die AfA-Monatsgenauigkeit im Zweifel manuell korrigieren."""
    m = _DATUM_RE.search(str(d.get("datum") or ""))
    if m:
        tag, monat, jahr = (int(x) for x in m.groups())
        try:
            return date(jahr, monat, tag).isoformat()
        except ValueError:
            pass
    jahr = int(d.get("steuerjahr_zuordnung") or fallback_jahr)
    return date(jahr, 1, 1).isoformat()


def _sync_docs_in_betrieb(betrieb: Betrieb, docs: list, jahr: int):
    """Gescannte betrieb_einnahme/-ausgabe-Belege, die diesem Betrieb
    zugeordnet sind, als Positionen übernehmen (dedupliziert über den
    Dateinamen als Quelle – jeder Beleg landet nur einmal in der EÜR)."""
    vorhandene_quellen = ({p.quelle for p in betrieb.einnahmen if p.quelle}
                          | {p.quelle for p in betrieb.ausgaben if p.quelle}
                          | {a.quelle for a in betrieb.afa_positionen if a.quelle})
    for d in docs:
        if d.get("betrieb") != betrieb.name or d["dateiname"] in vorhandene_quellen:
            continue
        ed = d.get("extrahierte_daten", {})
        betrag = _num(ed.get("brutto", d.get("betrag_eur")))
        if not betrag:
            continue
        datum = _datum_aus_doc(d, jahr)
        bezeichnung = d.get("dokumenttyp") or d["dateiname"]
        if d.get("kategorie") == "betrieb_einnahme":
            betrieb.einnahmen.append(
                Position(datum, bezeichnung, betrag, "beleg", d["dateiname"]))
        elif d.get("kategorie") == "betrieb_ausgabe" and not ed.get("ist_anlagegut"):
            betrieb.ausgaben.append(
                Position(datum, bezeichnung, betrag, "beleg", d["dateiname"]))
        # Anlagegüter (ist_anlagegut=True) NICHT automatisch übernehmen –
        # AfA-Nutzungsdauer ist steuerlich zu wichtig für Stillschweigen,
        # der Nutzer bestätigt sie unten explizit (siehe _anlagegut_vorschlaege).


def _anlagegut_vorschlaege(betrieb: Betrieb, docs: list) -> list:
    """Gescannte Belege, die Vision als Anlagegut markiert hat, aber noch
    nicht als AfA-Position übernommen wurden."""
    vorhandene_quellen = {a.quelle for a in betrieb.afa_positionen if a.quelle}
    vorschlaege = []
    for d in docs:
        if (d.get("betrieb") != betrieb.name
                or d.get("kategorie") != "betrieb_ausgabe"
                or d["dateiname"] in vorhandene_quellen):
            continue
        ed = d.get("extrahierte_daten", {})
        if ed.get("ist_anlagegut"):
            vorschlaege.append(d)
    return vorschlaege


def _e(v: float) -> str:
    return f"{v:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def render_betrieb_tab(cfg: dict, interview: dict, personen: dict):
    _st_init()
    ss = st.session_state
    jahr = cfg["jahr"]

    st.subheader("🏭 Betrieb / Nebengewerbe – Einnahmen-Überschuss-Rechnung")
    st.caption("Für Gewerbebetrieb, freiberufliche Tätigkeit, Photovoltaik-/"
               "Energieverkauf oder Vermietung. Belege mit Kategorie "
               "'Betriebseinnahme'/'-ausgabe' aus Tab 1 werden hier "
               "automatisch berücksichtigt, sobald du sie einem Betrieb "
               "zuordnest.")

    with st.expander("➕ Neuen Betrieb anlegen"):
        c1, c2, c3 = st.columns(3)
        name = c1.text_input("Name", key="nb_name",
                             placeholder="z. B. Fernwärme-Verkauf")
        art = c2.selectbox("Art", list(ARTEN.keys()),
                           format_func=lambda k: ARTEN[k], key="nb_art")
        inhaber = c3.selectbox("Inhaber", ["P1", "P2"],
                               format_func=lambda k: personen.get(k, k),
                               key="nb_inhaber")
        c4, c5 = st.columns(2)
        ku = c4.checkbox("Kleinunternehmer (§ 19 UStG)", value=True,
                         key="nb_ku",
                         help="Keine Umsatzsteuer auf Rechnungen. Abwählen, "
                              "wenn zur Regelbesteuerung optiert wurde.")
        gruendung = c5.date_input("Gründungsdatum (optional)", value=None,
                                  key="nb_gruendung")
        if st.button("Betrieb anlegen", type="primary", disabled=not name):
            ss.betriebe.append(Betrieb(
                name=name, art=art, inhaber=inhaber,
                kleinunternehmer_19ustg=ku,
                gruendung=gruendung.isoformat() if gruendung else ""))
            st.rerun()

    if not ss.betriebe:
        st.info("Noch kein Betrieb angelegt.")
        return

    ergebnisse = []
    for idx, betrieb in enumerate(ss.betriebe):
        _sync_docs_in_betrieb(betrieb, ss.docs, jahr)
        ergebnis = berechne_euer(betrieb, jahr, cfg)
        ergebnisse.append(ergebnis)

        with st.expander(f"🏭 {betrieb.name} – {ARTEN.get(betrieb.art, betrieb.art)} "
                         f"({personen.get(betrieb.inhaber, betrieb.inhaber)})",
                         expanded=True):
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Einnahmen", _e(ergebnis["einnahmen"]))
            k2.metric("Ausgaben", _e(ergebnis["ausgaben"]))
            k3.metric("AfA", _e(ergebnis["afa"]))
            k4.metric("Gewinn", _e(ergebnis["gewinn"]))

            vorschlaege = _anlagegut_vorschlaege(betrieb, ss.docs)
            for d in vorschlaege:
                ed = d.get("extrahierte_daten", {})
                betrag = _num(ed.get("brutto", d.get("betrag_eur")))
                nutzungsdauer_vorschlag = int(_num(
                    ed.get("geschaetzte_nutzungsdauer"), 10) or 10)
                st.warning(
                    f"🔧 '{d['dateiname']}' sieht nach einem Anlagegut aus "
                    f"({_e(betrag)}) – als Abschreibung (AfA) statt "
                    "Sofortausgabe erfassen?")
                c1, c2, c3 = st.columns([2, 1, 1])
                datum = c1.date_input(
                    "Anschaffungsdatum",
                    value=date.fromisoformat(_datum_aus_doc(d, jahr)),
                    key=f"afa_datum_{idx}_{d['dateiname']}")
                nutzungsdauer = c2.number_input(
                    "Nutzungsdauer (Jahre)", 1, 50, nutzungsdauer_vorschlag,
                    key=f"afa_nd_{idx}_{d['dateiname']}")
                if c3.button("✅ Als AfA übernehmen",
                             key=f"afa_go_{idx}_{d['dateiname']}"):
                    betrieb.afa_positionen.append(AfaPosition(
                        bezeichnung=d.get("dokumenttyp") or d["dateiname"],
                        anschaffungskosten=betrag,
                        anschaffungsdatum=datum.isoformat(),
                        nutzungsdauer_jahre=int(nutzungsdauer),
                        quelle=d["dateiname"]))
                    st.rerun()
                if st.button("Stattdessen als normale Ausgabe verbuchen",
                             key=f"afa_skip_{idx}_{d['dateiname']}"):
                    betrieb.ausgaben.append(Position(
                        _datum_aus_doc(d, jahr),
                        d.get("dokumenttyp") or d["dateiname"], betrag,
                        "beleg", d["dateiname"]))
                    st.rerun()

            for h in ergebnis["hinweise"]:
                st.info(h) if "⚠️" not in h else st.warning(h)

            st.markdown("**Einnahmen**")
            if ergebnis["einnahmen_positionen"]:
                st.dataframe(pd.DataFrame([
                    {"Datum": p.datum, "Bezeichnung": p.bezeichnung,
                     "Betrag €": p.betrag, "Quelle": p.quelle or "manuell"}
                    for p in ergebnis["einnahmen_positionen"]]),
                    use_container_width=True, hide_index=True)
            with st.form(f"form_einnahme_{idx}", clear_on_submit=True):
                c1, c2, c3 = st.columns([1, 2, 1])
                e_datum = c1.date_input("Datum", value=date(jahr, 1, 1))
                e_bez = c2.text_input("Bezeichnung")
                e_betrag = c3.number_input("Betrag (€)", 0.0, 10_000_000.0,
                                           0.0, step=10.0)
                if st.form_submit_button("➕ Einnahme hinzufügen") and e_bez:
                    betrieb.einnahmen.append(
                        Position(e_datum.isoformat(), e_bez, e_betrag))
                    st.rerun()

            st.markdown("**Ausgaben**")
            if ergebnis["ausgaben_positionen"]:
                st.dataframe(pd.DataFrame([
                    {"Datum": p.datum, "Bezeichnung": p.bezeichnung,
                     "Betrag €": p.betrag, "Quelle": p.quelle or "manuell"}
                    for p in ergebnis["ausgaben_positionen"]]),
                    use_container_width=True, hide_index=True)
            with st.form(f"form_ausgabe_{idx}", clear_on_submit=True):
                c1, c2, c3 = st.columns([1, 2, 1])
                a_datum = c1.date_input("Datum ", value=date(jahr, 1, 1))
                a_bez = c2.text_input("Bezeichnung ")
                a_betrag = c3.number_input("Betrag (€) ", 0.0, 10_000_000.0,
                                           0.0, step=10.0)
                if st.form_submit_button("➕ Ausgabe hinzufügen") and a_bez:
                    betrieb.ausgaben.append(
                        Position(a_datum.isoformat(), a_bez, a_betrag))
                    st.rerun()

            st.markdown("**AfA-Tabelle (Anlagegüter)**")
            if ergebnis["afa_positionen"]:
                st.dataframe(pd.DataFrame(ergebnis["afa_positionen"]),
                            use_container_width=True, hide_index=True)
            with st.form(f"form_afa_{idx}", clear_on_submit=True):
                c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
                g_bez = c1.text_input("Bezeichnung  ")
                g_kosten = c2.number_input("Anschaffungskosten (€)", 0.0,
                                           10_000_000.0, 0.0, step=100.0)
                g_datum = c3.date_input("Anschaffungsdatum ", value=date(jahr, 1, 1))
                g_nd = c4.number_input("Nutzungsdauer (Jahre)", 1, 50, 10)
                if st.form_submit_button("➕ Anlagegut hinzufügen") and g_bez:
                    betrieb.afa_positionen.append(AfaPosition(
                        g_bez, g_kosten, g_datum.isoformat(), int(g_nd)))
                    st.rerun()

            if st.button("🗑️ Betrieb löschen", key=f"del_betrieb_{idx}"):
                ss.betriebe.pop(idx)
                st.rerun()

    gewinn_pro_person = {"P1": 0.0, "P2": 0.0}
    for r in ergebnisse:
        gewinn_pro_person[r["inhaber"]] = round(
            gewinn_pro_person.get(r["inhaber"], 0.0) + r["gewinn"], 2)
    interview["_betriebe"] = {
        "jahr": jahr, "betriebe": ergebnisse,
        "gewinn_pro_person": gewinn_pro_person,
    }
