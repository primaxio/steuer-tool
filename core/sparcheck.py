"""
Spar-Check: interaktive Checkliste aller absetzbaren Posten für das Profil
(Ehepaar, zwei Arbeitsverhältnisse inkl. Bundeswehr, Aktien, Krypto).
Beträge fließen in den Erstattungsrechner und die ELSTER-Hilfe ein.
"""

import streamlit as st

# bucket: wk (je Person) | sa | h35a_handwerker | h35a_haushalt |
#         h35a_minijob | agb | parteispenden
ITEMS = [
    # ---------------- Werbungskosten (JE PERSON eigener 1.230€-Pauschbetrag)
    dict(id="arbeitsmittel", bucket="wk", pro_person=True,
         titel="Arbeitsmittel (Laptop, Monitor, Schreibtisch, Stuhl, Handy-Anteil)",
         tipp="Bis 952 € brutto pro Gerät sofort voll absetzbar. Auch privat "
              "mitgenutzte Geräte anteilig (oft 50 %)."),
    dict(id="telefon_internet", bucket="wk", pro_person=True,
         titel="Telefon & Internet (beruflicher Anteil)",
         tipp="Ohne Einzelnachweis: pauschal 20 % der Kosten, max. 20 €/Monat "
              "= bis 240 €/Jahr. Einfach eintragen – wird fast immer anerkannt."),
    dict(id="kontofuehrung", bucket="wk", pro_person=True,
         titel="Kontoführungspauschale",
         tipp="16 € pauschal, ganz ohne Beleg. Einfach mitnehmen.",
         standard=16.0),
    dict(id="fortbildung", bucket="wk", pro_person=True,
         titel="Fortbildungen, Seminare, Fachliteratur, Zertifikate",
         tipp="Bundeswehr-Tipp: Kosten rund um BFD-Maßnahmen (Fahrten, "
              "Material, Eigenanteile), die der Berufsförderungsdienst NICHT "
              "erstattet, sind Werbungskosten!"),
    dict(id="berufskleidung", bucket="wk", pro_person=True,
         titel="Typische Berufskleidung + Reinigung",
         tipp="Nur 'typische' Kleidung (Uniform, Sicherheitsschuhe, Kittel) – "
              "kein normaler Anzug."),
    dict(id="gewerkschaft", bucket="wk", pro_person=True,
         titel="Gewerkschaft / Berufsverband",
         tipp="Mitgliedsbeiträge zählen voll."),
    dict(id="bewerbung", bucket="wk", pro_person=True,
         titel="Bewerbungskosten",
         tipp="Auch ohne Belege werden oft Pauschalen (~2,50 € online, "
              "~8,50 € mit Mappe) anerkannt."),
    dict(id="dienstreisen", bucket="wk", pro_person=True,
         titel="Dienstreisen & Verpflegungsmehraufwand",
         tipp="Bei Auswärtstätigkeit: 14 € (ab 8 Std.) / 28 € (ganztags) pro "
              "Tag, sofern der Arbeitgeber nichts erstattet hat – z. B. "
              "Lehrgänge, Wettkämpfe, Montage."),
    dict(id="umzug", bucket="wk", pro_person=True,
         titel="Beruflich veranlasster Umzug",
         tipp="Umzugskostenpauschale plus tatsächliche Kosten (Spedition, "
              "doppelte Miete). Beruflich = z. B. Arbeitsweg deutlich kürzer."),
    dict(id="doppelte_hh", bucket="wk", pro_person=True,
         titel="Doppelte Haushaltsführung",
         tipp="Zweitwohnung am Arbeitsort: Miete bis 1.000 €/Monat + eine "
              "Heimfahrt/Woche + 3 Monate Verpflegungspauschalen."),
    dict(id="unfall_arbeitsweg", bucket="wk", pro_person=True,
         titel="Unfallkosten auf dem Arbeitsweg",
         tipp="Reparatur/Selbstbeteiligung nach Unfall auf dem Weg zur "
              "Arbeit – zusätzlich zur Entfernungspauschale."),
    # ---------------- Sonderausgaben (gemeinsam)
    dict(id="spenden", bucket="sa", pro_person=False,
         titel="Spenden (Geld & Sachspenden)",
         tipp="Bis 300 € je Spende reicht der Kontoauszug als Nachweis – "
              "auch Vereinsbeiträge gemeinnütziger Vereine zählen oft."),
    dict(id="ruerup_basisrente", bucket="vorsorge_basis", pro_person=False,
         titel="Rürup-/Basisrente-Beiträge",
         tipp="Seit 2023 zu 100 % abzugsfähig wie die gesetzliche "
              "Rentenversicherung – kein 1.900-€-Deckel. Riester läuft "
              "separat über den eigenen Fragebogen-Bereich (Anlage AV, "
              "Günstigerprüfung Zulage vs. Sonderausgabenabzug)."),
    dict(id="kinderbetreuung", bucket="sa", pro_person=False,
         titel="Kinderbetreuung (Kita, Hort, Tagesmutter, Au-pair)",
         tipp="Abziehbar je Kind bis 14 J. – Rechnung + Überweisung nötig, "
              "Barzahlung zählt nicht. Essensgeld herausrechnen."),
    dict(id="schulgeld", bucket="sa", pro_person=False,
         titel="Schulgeld (Privatschule)",
         tipp="30 % abziehbar, max. 5.000 €/Kind."),
    dict(id="erststudium", bucket="sa", pro_person=False,
         titel="Erstausbildung/-studium eines Ehegatten",
         tipp="Als Sonderausgaben bis 6.000 €/Jahr (Zweitausbildung wäre "
              "sogar Werbungskosten)."),
    # ---------------- § 34g (direkt von der Steuer!)
    dict(id="parteispenden", bucket="parteispenden", pro_person=False,
         titel="Partei- & Wählervereinigungs-Spenden/Beiträge",
         tipp="50 % werden DIREKT von der Steuer abgezogen (bis 1.650 € "
              "Zuwendung bei Zusammenveranlagung = 825 € geschenkt)."),
    # ---------------- § 35a (direkt von der Steuer!)
    dict(id="nk_abrechnung", bucket="h35a_haushalt", pro_person=False,
         titel="Nebenkostenabrechnung: Hausmeister, Treppenreinigung, "
               "Gartenpflege, Winterdienst, Aufzugswartung",
         tipp="DER meistvergessene Posten bei Mietern! Die Lohnanteile "
              "stehen in eurer NK-Abrechnung (oft gibt es eine "
              "§ 35a-Bescheinigung vom Vermieter – anfordern!)."),
    dict(id="schornsteinfeger", bucket="h35a_handwerker", pro_person=False,
         titel="Schornsteinfeger, Heizungswartung, kleine Reparaturen",
         tipp="Arbeitskosten zu 20 % direkt von der Steuer – auch aus der "
              "NK-Abrechnung."),
    dict(id="putzhilfe", bucket="h35a_haushalt", pro_person=False,
         titel="Putzhilfe / Haushaltshilfe (auf Rechnung)",
         tipp="20 % direkt von der Steuer, Überweisung Pflicht."),
    dict(id="minijob_haushalt", bucket="h35a_minijob", pro_person=False,
         titel="Haushaltshilfe als Minijob (Haushaltsscheck)",
         tipp="20 % der Kosten, max. 510 € Ermäßigung."),
    # ---------------- Außergewöhnliche Belastungen
    dict(id="krankheit", bucket="agb", pro_person=False,
         titel="Brille, Zahnersatz, Zuzahlungen, Medikamente, Physiotherapie",
         tipp="Wirkt erst über der zumutbaren Eigenbelastung – Kosten "
              "deshalb möglichst in EINEM Jahr bündeln (z. B. Zahn-OP + "
              "Brille zusammen)."),
]
# Behinderten-/Pflege-Pauschbetrag und § 33a-Unterhalt sind KEINE
# Betrags-Schätzungen mehr, sondern echte Berechnungen mit eigenen
# Fragebogen-Feldern (GdB-Stufe, Pflegegrad, Unterhaltsempfänger) – siehe
# app.py-Expander "Behinderung, Pflege & Unterhalt" und
# veranlagung.py::_agb_pauschbetraege_ohne_zumutbare_grenze().

GRUPPEN = [
    ("wk", "👜 Werbungskosten – je Person (eigener 1.230 €-Pauschbetrag!)"),
    ("sa", "🎁 Sonderausgaben (gemeinsam)"),
    ("vorsorge_basis", "🩺 Rürup/Basisrente (voll abzugsfähig)"),
    ("parteispenden", "🏛️ Parteispenden – 50 % direkt von der Steuer"),
    ("h35a_handwerker", "🔧 Handwerker (§ 35a – 20 % direkt von der Steuer)"),
    ("h35a_haushalt", "🏠 Haushaltsnahe Dienstleistungen (§ 35a)"),
    ("h35a_minijob", "🧾 Haushalts-Minijob (§ 35a)"),
    ("agb", "🏥 Außergewöhnliche Belastungen (Krankheitskosten)"),
]

# Spar-Check-Posten, die inhaltlich mit automatisch aus hochgeladenen
# Belegen extrahierten Beträgen überlappen (siehe veranlagung.py/
# elster_export.py, wo dieselben Belege bereits automatisch verrechnet
# werden) – hier droht bei zusätzlichem manuellem Eintrag eine
# Doppelerfassung. Jeder Eintrag: Liste von (Kategorie, Feld)-Paaren, die
# zusammen die "bereits automatisch erfasst"-Summe für den Posten ergeben.
# Feld=None -> der generische betrag_eur des Belegs.
_AUTOMATIK_UEBERLAPPT = {
    "nk_abrechnung": [("nebenkostenabrechnung", "summe_haushaltsnah")],
    # Schornsteinfeger/Heizungswartung tauchen sowohl in NK-Abrechnungen
    # (vision.py: "posten_handwerker") als auch als eigenständige
    # Handwerkerrechnung auf – veranlagung.py summiert beide Quellen in
    # denselben § 35a-Handwerker-Topf.
    "schornsteinfeger": [("nebenkostenabrechnung", "summe_handwerker"),
                         ("handwerker_haushaltsnah", "arbeitskosten")],
    "spenden": [("spende", None)],
    "krankheit": [("krankheitskosten", None)],
}


def _automatik_werte(docs: list) -> dict:
    """Summiert je überlappendem Spar-Check-Posten, was aus hochgeladenen
    Belegen bereits automatisch in die Rechnung eingeflossen ist."""
    out = {item_id: 0.0 for item_id in _AUTOMATIK_UEBERLAPPT}
    for d in docs or []:
        kategorie = d.get("kategorie")
        ed = d.get("extrahierte_daten", {})
        for item_id, quellen in _AUTOMATIK_UEBERLAPPT.items():
            for quell_kat, feld in quellen:
                if kategorie != quell_kat:
                    continue
                wert = ed.get(feld) if feld else d.get("betrag_eur")
                out[item_id] += float(wert or 0)
    return out


def _werbungskosten_belege_summe(docs: list, person: str) -> float:
    """Summe hochgeladener 'werbungskosten'-Belege einer Person – fließt
    bereits automatisch in die Werbungskosten ein (veranlagung.py Schritt
    1). Nicht auf einzelne Spar-Check-Posten (Arbeitsmittel vs.
    Fortbildung …) herunterbrechbar, da die Kategorie das nicht
    unterscheidet – deshalb nur EIN gruppenweiter Hinweis statt je Posten."""
    return sum(float(d.get("betrag_eur") or 0) for d in (docs or [])
              if d.get("kategorie") == "werbungskosten"
              and d.get("inhaber", "P1") == person)


def _eur(v: float) -> str:
    return f"{v:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def render_sparcheck(interview: dict, personen: dict, docs: list = None):
    st.subheader("💰 Spar-Check – das Maximum rausholen")
    st.caption("Hake an, was auf euch zutrifft, und trag (geschätzte) Beträge "
               "ein. Alles fließt sofort in den Erstattungsrechner ein. "
               "Belege später in Tab 1 nachladen – aufbewahren reicht.")
    spar = interview.setdefault("spar", {})
    zusammen = interview.get("zusammenveranlagung", True)
    aktive = ("P1", "P2") if zusammen else ("P1",)
    auto_werte = _automatik_werte(docs)
    # Stand VOR den Widgets dieses Durchlaufs (aus dem letzten Rerun) – für
    # die Zwischensummen an den Gruppen-Überschriften, damit man auch ohne
    # Aufklappen sieht, was schon erfasst ist.
    stand = summen(interview)
    stand["wk"] = stand["wk_P1"] + stand["wk_P2"]

    for bucket, ueberschrift in GRUPPEN:
        items = [i for i in ITEMS if i["bucket"] == bucket]
        bucket_summe = stand.get(bucket, 0.0)
        label = ueberschrift + (f"  —  ✅ {bucket_summe:,.0f} € erfasst"
                                .replace(",", ".") if bucket_summe else "")
        with st.expander(label,
                         expanded=any(spar.get(i["id"], {}).get("aktiv")
                                      for i in items)):
            if bucket == "wk":
                for p in aktive:
                    wk_belege = _werbungskosten_belege_summe(docs, p)
                    if wk_belege:
                        st.info(
                            f"✅ **{_eur(wk_belege)}** an hochgeladenen "
                            f"Werbungskosten-Belegen für {personen[p]} "
                            "fließen bereits automatisch mit ein (Tab 1 · "
                            "Dokumente) – hier nur ZUSÄTZLICHE Ausgaben "
                            "ohne eigenen Beleg eintragen.")
            for item in items:
                eintrag = spar.setdefault(item["id"], {})
                aktiv = st.checkbox(item["titel"],
                                    value=bool(eintrag.get("aktiv")),
                                    key=f"sp_{item['id']}")
                eintrag["aktiv"] = aktiv
                st.caption("💡 " + item["tipp"])

                auto_wert = auto_werte.get(item["id"], 0.0)
                if auto_wert:
                    auto_wert_str = _eur(auto_wert)
                    if aktiv:
                        st.warning(
                            "⚠️ **Doppelerfassung-Risiko**: Aus deinen "
                            "hochgeladenen Belegen wurden dafür bereits "
                            f"**{auto_wert_str}** automatisch übernommen "
                            "(Tab 1 · Dokumente). Häkchen hier nur setzen, "
                            "wenn du ZUSÄTZLICHE, davon unabhängige Kosten "
                            "eintragen willst – sonst bitte entfernen.")
                    else:
                        st.info(
                            f"✅ **{auto_wert_str}** wurden bereits "
                            "automatisch aus deinen hochgeladenen Belegen "
                            "übernommen (Tab 1 · Dokumente) – hier "
                            "normalerweise nichts zusätzlich eintragen.")

                if aktiv:
                    if item["pro_person"]:
                        cols = st.columns(len(aktive))
                        for col, p in zip(cols, aktive):
                            eintrag[p] = col.number_input(
                                f"{personen[p]} (€/Jahr)", 0.0, 100_000.0,
                                float(eintrag.get(p,
                                      item.get("standard", 0.0))),
                                step=10.0, key=f"sp_{item['id']}_{p}")
                    else:
                        eintrag["betrag"] = st.number_input(
                            "Betrag (€/Jahr)", 0.0, 100_000.0,
                            float(eintrag.get("betrag",
                                  item.get("standard", 0.0))),
                            step=10.0, key=f"sp_{item['id']}_b")
                st.markdown("")

    s = summen(interview)
    st.divider()
    st.markdown("**📊 Übersicht: bisher erfasst**")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric(f"👜 WK {personen['P1']}", f"{s['wk_P1']:,.0f} €".replace(",", "."))
    m2.metric(f"👜 WK {personen['P2']}" if zusammen else "🎁 Sonderausgaben",
             f"{(s['wk_P2'] if zusammen else s['sa']):,.0f} €".replace(",", "."))
    m3.metric("🔧🏠 § 35a-Arbeitskosten",
             f"{s['h35a_handwerker'] + s['h35a_haushalt']:,.0f} €"
             .replace(",", "."),
             help="20 % davon werden direkt von der Steuer abgezogen.")
    m4.metric("🏥 Außergew. Belastungen",
             f"{s['agb']:,.0f} €".replace(",", "."))


def summen(interview: dict) -> dict:
    """Aggregiert die Spar-Check-Beträge je Topf."""
    spar = interview.get("spar", {})
    out = {"wk_P1": 0.0, "wk_P2": 0.0, "sa": 0.0, "parteispenden": 0.0,
           "h35a_handwerker": 0.0, "h35a_haushalt": 0.0,
           "h35a_minijob": 0.0, "agb": 0.0, "vorsorge_basis": 0.0}
    for item in ITEMS:
        e = spar.get(item["id"], {})
        if not e.get("aktiv"):
            continue
        if item["pro_person"]:
            out["wk_P1"] += float(e.get("P1", 0) or 0)
            out["wk_P2"] += float(e.get("P2", 0) or 0)
        else:
            out[item["bucket"]] += float(e.get("betrag", 0) or 0)
    return out
