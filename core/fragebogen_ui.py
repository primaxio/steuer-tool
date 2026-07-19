"""
Gemeinsame Fragebogen-Bausteine für Experten-Tab (app.py) UND den
Einfachen-Modus-Wizard (wizard.py) – dieselbe Logik, damit keine
Duplikate entstehen (Muster wie core/dokumente_ui.py)."""

import streamlit as st

from .checks import _num


def render_stammdaten(interview: dict, personen: dict, aktive: tuple,
                      key_prefix: str = ""):
    """Finanzamt/Steuernummer/IBAN/Steuer-ID/Religion – Pflichtangaben für
    den ELSTER-Hauptvordruck."""
    sd = interview.setdefault("stammdaten", {})
    c1, c2 = st.columns(2)
    with c1:
        sd["finanzamt"] = st.text_input(
            "Finanzamt", sd.get("finanzamt", "Finanzamt Bonn-Innenstadt"),
            key=f"{key_prefix}fa")
        sd["steuernummer"] = st.text_input(
            "Gemeinsame Steuernummer (Format NRW: 5FF/BBB/UUUUP)",
            sd.get("steuernummer", ""), key=f"{key_prefix}stnr")
        sd["iban"] = st.text_input("IBAN für Erstattung",
                                   sd.get("iban", ""), key=f"{key_prefix}iban")
    with c2:
        for p in aktive:
            sd[f"steuer_id_{p}"] = st.text_input(
                f"Steuer-ID {personen[p]} (11-stellig)",
                sd.get(f"steuer_id_{p}", ""), key=f"{key_prefix}sid_{p}")
            sd[f"religion_{p}"] = st.selectbox(
                f"Religion {personen[p]}",
                ["keine/andere (VD)", "ev", "rk"],
                ["keine/andere (VD)", "ev", "rk"].index(
                    sd.get(f"religion_{p}", "keine/andere (VD)")),
                key=f"{key_prefix}rel_{p}")


def render_fahrtkosten_homeoffice(interview: dict, personen: dict,
                                  aktive: tuple, key_prefix: str = ""):
    """Entfernungspauschale + Homeoffice-Pauschale je Person."""
    cols = st.columns(len(aktive))
    for col, p in zip(cols, aktive):
        with col:
            st.markdown(f"**{personen[p]}**")
            interview[f"entfernung_km_{p}"] = st.number_input(
                "Einfache Entfernung zur Arbeit (km)", 0.0, 300.0,
                float(interview.get(f"entfernung_km_{p}") or 0.0), step=1.0,
                key=f"{key_prefix}km_{p}",
                help="0,30 €/km bis 20 km, ab km 21: 0,38 €/km – pro "
                     "Arbeitstag mit Fahrt zur ersten Tätigkeitsstätte.")
            interview[f"arbeitstage_{p}"] = st.number_input(
                "Tage mit Fahrt zur Arbeit", 0, 366,
                int(interview.get(f"arbeitstage_{p}") or 0),
                key=f"{key_prefix}at_{p}")
            interview[f"homeoffice_tage_{p}"] = st.number_input(
                "Homeoffice-Tage", 0, 366,
                int(interview.get(f"homeoffice_tage_{p}") or 0),
                key=f"{key_prefix}ho_{p}",
                help="6 €/Tag, max. 1.260 €/Jahr – für denselben Tag NICHT "
                     "zusätzlich zur Fahrt-Pauschale.")


def render_behinderung_pflege_unterhalt(interview: dict, personen: dict,
                                        aktive: tuple, key_prefix: str = ""):
    """§ 33b/§ 33a-Pauschbeträge – wirken OHNE Kürzung um die zumutbare
    Belastung, anders als normale Krankheitskosten."""
    st.caption("Diese Beträge wirken sofort und ungekürzt – anders als "
              "normale Krankheitskosten im Spar-Check.")
    bcols = st.columns(len(aktive))
    gdb_stufen = [0, 20, 30, 40, 50, 60, 70, 80, 90, 100]
    for col, p in zip(bcols, aktive):
        with col:
            st.markdown(f"**{personen[p]}**")
            interview[f"gdb_{p}"] = st.selectbox(
                "Grad der Behinderung (GdB)", gdb_stufen,
                gdb_stufen.index(int(interview.get(f"gdb_{p}") or 0))
                if int(interview.get(f"gdb_{p}") or 0) in gdb_stufen else 0,
                key=f"{key_prefix}gdb_sel_{p}",
                help="Ab GdB 20 gibt es einen Pauschbetrag ohne "
                     "Einzelnachweis (§ 33b EStG).")
            if interview[f"gdb_{p}"] >= 20:
                interview[f"gdb_hilflos_blind_{p}"] = st.checkbox(
                    "Merkzeichen H/Bl/TBl (hilflos/blind)?",
                    value=bool(interview.get(f"gdb_hilflos_blind_{p}")),
                    key=f"{key_prefix}hb_gdb_{p}",
                    help="Ersetzt den GdB-Pauschbetrag durch den erhöhten "
                         "Pauschbetrag von 7.400 €.")
    st.markdown("**Pflege eines Angehörigen (unentgeltlich, häuslich)**")
    pflege_stufen = [0, 2, 3, 4, 5]
    interview["pflegegrad_angehoeriger"] = st.selectbox(
        "Pflegegrad der gepflegten Person", pflege_stufen,
        pflege_stufen.index(int(interview.get("pflegegrad_angehoeriger") or 0))
        if int(interview.get("pflegegrad_angehoeriger") or 0) in pflege_stufen
        else 0, key=f"{key_prefix}pflegegrad",
        help="0 = keine Pflege. Ab Pflegegrad 2 gibt es einen Pauschbetrag "
             "(§ 33b Abs. 6 EStG).")
    st.markdown("**Unterhaltsleistungen an bedürftige Personen (§ 33a EStG)**")
    u1, u2 = st.columns(2)
    interview["unterhalt_betrag"] = u1.number_input(
        "Gezahlter Unterhalt (€/Jahr)", 0.0, 100_000.0,
        float(interview.get("unterhalt_betrag") or 0.0), step=100.0,
        key=f"{key_prefix}unterhalt_betrag")
    interview["unterhalt_eigene_einkuenfte"] = u2.number_input(
        "Eigene Einkünfte/Bezüge der unterstützten Person (€/Jahr)",
        0.0, 100_000.0,
        float(interview.get("unterhalt_eigene_einkuenfte") or 0.0),
        step=100.0, key=f"{key_prefix}unterhalt_eig",
        help="Übersteigen diese 624 €/Jahr, wird der übersteigende Betrag "
             "vom Höchstbetrag abgezogen.")


def render_riester(interview: dict, personen: dict, aktive: tuple,
                   key_prefix: str = ""):
    """Anlage AV (§ 10a EStG) – Eigenbeitrag + Kinderzulage-Angaben, echte
    Günstigerprüfung passiert in veranlagung.py."""
    rcols = st.columns(len(aktive))
    for col, p in zip(rcols, aktive):
        interview[f"riester_beitrag_{p}"] = col.number_input(
            f"Eigenbeitrag {personen[p]} (€/Jahr, inkl. Zulage)",
            0.0, 10_000.0,
            float(interview.get(f"riester_beitrag_{p}") or 0.0), step=10.0,
            key=f"{key_prefix}riester_b_{p}")
    rk1, rk2 = st.columns(2)
    interview["riester_kinder_ab_2008"] = rk1.number_input(
        "Kinder mit Kinderzulage, geboren AB 2008", 0, 15,
        int(interview.get("riester_kinder_ab_2008") or 0),
        key=f"{key_prefix}riester_kab")
    interview["riester_kinder_vor_2008"] = rk2.number_input(
        "Kinder mit Kinderzulage, geboren VOR 2008", 0, 15,
        int(interview.get("riester_kinder_vor_2008") or 0),
        key=f"{key_prefix}riester_kvor")
    st.caption("Das Finanzamt vergleicht automatisch die Steuerersparnis "
              "durch den Sonderausgabenabzug mit der bereits "
              "gutgeschriebenen Zulage und zahlt nur den übersteigenden "
              "Betrag zusätzlich aus (Ergebnis im Rechenweg, Tab/Schritt "
              "'Ergebnis').")


def render_verlustvortraege(interview: dict, key_prefix: str = ""):
    v1, v2, v3 = st.columns(3)
    interview["verlustvortrag_23"] = v1.number_input(
        "§ 23 / Krypto (€)", 0.0, 10_000_000.0,
        float(interview.get("verlustvortrag_23") or 0.0), step=100.0,
        key=f"{key_prefix}v23")
    interview["verlustvortrag_kap_aktien"] = v2.number_input(
        "KAP Aktienverluste (€)", 0.0, 10_000_000.0,
        float(interview.get("verlustvortrag_kap_aktien") or 0.0), step=100.0,
        key=f"{key_prefix}vkapa")
    interview["verlustvortrag_kap_sonstige"] = v3.number_input(
        "KAP sonstige Verluste (€)", 0.0, 10_000_000.0,
        float(interview.get("verlustvortrag_kap_sonstige") or 0.0),
        step=100.0, key=f"{key_prefix}vkaps")


def hat_behinderung_pflege_unterhalt(interview: dict) -> bool:
    return (any(interview.get(f"gdb_{p}") for p in ("P1", "P2"))
           or bool(interview.get("pflegegrad_angehoeriger"))
           or bool(_num(interview.get("unterhalt_betrag"))))


def hat_verlustvortrag(interview: dict) -> bool:
    return any(_num(interview.get(k)) for k in
              ("verlustvortrag_23", "verlustvortrag_kap_aktien",
               "verlustvortrag_kap_sonstige"))


def hat_riester(interview: dict, aktive: tuple) -> bool:
    return any(_num(interview.get(f"riester_beitrag_{p}")) for p in aktive)
