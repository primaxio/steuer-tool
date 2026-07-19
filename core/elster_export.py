"""
Zusammenfassung und ELSTER-Eingabehilfe.
Erzeugt pro Anlage eine Liste "Feld → Wert", die 1:1 in ELSTER
(www.elster.de) übertragen werden kann, plus JSON-Export.
"""

import json
from datetime import datetime

from .checks import _num, entfernungspauschale


def build_summary(docs: list, cfg: dict, interview: dict) -> dict:
    crypto = interview.get("_crypto")
    """Aggregiert alle Dokumente und Interview-Antworten zu einer
    strukturierten Zusammenfassung pro Anlage."""
    s = {
        "steuerjahr": cfg["jahr"],
        "erstellt": datetime.now().strftime("%d.%m.%Y %H:%M"),
        "anlagen": {},
    }

    def cat(docs_, *keys):
        return [d for d in docs_ if d.get("kategorie") in keys]

    def ed(d, feld, fallback=None):
        return _num(d.get("extrahierte_daten", {}).get(feld, fallback))

    # ---------- Anlage N ----------
    n_eintraege = []
    for idx, key in enumerate(
        ["lohnsteuerbescheinigung_zivil", "lohnsteuerbescheinigung_bundeswehr"], 1
    ):
        for d in cat(docs, key):
            n_eintraege.append({
                "inhaber": d.get("inhaber", "P1"),
                "arbeitgeber": d.get("aussteller") or f"Arbeitgeber {idx}",
                "quelle": d["dateiname"],
                "bruttoarbeitslohn": ed(d, "bruttoarbeitslohn", d.get("betrag_eur")),
                "lohnsteuer": ed(d, "lohnsteuer"),
                "soli": ed(d, "soli"),
                "kirchensteuer": ed(d, "kirchensteuer"),
                "steuerklasse": d.get("extrahierte_daten", {}).get("steuerklasse"),
                "ist_bundeswehr": key == "lohnsteuerbescheinigung_bundeswehr",
            })

    zusammen = bool(interview.get("zusammenveranlagung"))
    personen = interview.get("personen", {"P1": "Person 1", "P2": "Person 2"})
    wk_pro_person = {}
    for p_key in (("P1", "P2") if zusammen else ("P1",)):
        km = _num(interview.get(f"entfernung_km_{p_key}"))
        tage = int(_num(interview.get(f"arbeitstage_{p_key}")))
        ho_tage = int(_num(interview.get(f"homeoffice_tage_{p_key}")))
        ep = entfernungspauschale(km, tage, cfg)
        ho = min(ho_tage * cfg["homeoffice_pauschale_pro_tag"],
                 cfg["homeoffice_max"])
        wk_belege = [d for d in cat(docs, "werbungskosten")
                     if d.get("inhaber", "P1") == p_key]
        belege_summe = round(sum(_num(d.get("betrag_eur"))
                                 for d in wk_belege), 2)
        gesamt = round(ep + ho + belege_summe, 2)
        wk_pro_person[p_key] = {
            "name": personen.get(p_key, p_key),
            "entfernungspauschale": {"km": km, "tage": tage, "betrag": ep},
            "homeoffice_pauschale": {"tage": ho_tage, "betrag": round(ho, 2)},
            "belege_summe": belege_summe,
            "belege": [{"datei": d["dateiname"],
                        "betrag": _num(d.get("betrag_eur")),
                        "beschreibung": d.get("dokumenttyp")}
                       for d in wk_belege],
            "gesamt": gesamt,
            "pauschbetrag": cfg["arbeitnehmer_pauschbetrag"],
            "einzelnachweis_lohnt": gesamt > cfg["arbeitnehmer_pauschbetrag"],
        }
    from .sparcheck import summen as spar_summen
    s["sparcheck"] = spar_summen(interview)
    s["stammdaten"] = interview.get("stammdaten", {})
    s["verlustvortraege"] = {
        "p23": _num(interview.get("verlustvortrag_23")),
        "kap_aktien": _num(interview.get("verlustvortrag_kap_aktien")),
        "kap_sonstige": _num(interview.get("verlustvortrag_kap_sonstige")),
    }
    uebergangsbeihilfe = [{
        "datei": d["dateiname"], "inhaber": d.get("inhaber", "P1"),
        "betrag": _num(d.get("betrag_eur")),
        "lohnsteuer": ed(d, "lohnsteuer"), "soli": ed(d, "soli"),
        "kirchensteuer": ed(d, "kirchensteuer")}
        for d in cat(docs, "uebergangsbeihilfe")]
    s["anlagen"]["N"] = {
        "arbeitsverhaeltnisse": n_eintraege,
        "werbungskosten_pro_person": wk_pro_person,
        "uebergangsbeihilfe": uebergangsbeihilfe,
    }

    # ---------- Anlage KAP ----------
    # Bewusst NICHT nach inhaber gefiltert – wie Sonderausgaben/agB gehört
    # KAP bei Zusammenveranlagung in einen GEMEINSAMEN Topf (anders als
    # Anlage N/SO mit eigenen Pausch-/Freibeträgen pro Person).
    kap_docs = cat(docs, "steuerbescheinigung_bank")
    if kap_docs:
        s["anlagen"]["KAP"] = {
            "kapitalertraege": round(sum(
                ed(d, "kapitalertraege_zeile7", d.get("betrag_eur"))
                for d in kap_docs), 2),
            "kapitalertragsteuer": round(sum(
                ed(d, "kapitalertragsteuer") for d in kap_docs), 2),
            "soli": round(sum(ed(d, "soli") for d in kap_docs), 2),
            "freistellungsauftrag_genutzt": round(sum(
                ed(d, "in_anspruch_genommener_freistellungsauftrag")
                for d in kap_docs), 2),
            "auslaendische_quellensteuer": round(sum(
                ed(d, "auslaendische_quellensteuer") for d in kap_docs), 2),
            "sparer_pauschbetrag": cfg["sparer_pauschbetrag"] *
                (2 if interview.get("zusammenveranlagung") else 1),
            "quellen": [d["dateiname"] for d in kap_docs],
        }

    # ---------- Termingeschäfte / Auslandszinsen (KAP Z. 19/21/24) ----------
    aktive_p = ("P1", "P2") if zusammen else ("P1",)
    berichte = cat(docs, "broker_steuerbericht")
    tg = round(sum(_num(interview.get(f"termin_gewinne_{p}")) for p in aktive_p)
               + sum(ed(d, "kap_zeile21_termingewinne") for d in berichte), 2)
    tv = round(sum(_num(interview.get(f"termin_verluste_{p}")) for p in aktive_p)
               + sum(ed(d, "kap_zeile24_terminverluste") for d in berichte), 2)
    bz = round(sum(_num(interview.get(f"broker_zinsen_{p}")) for p in aktive_p)
               + sum(ed(d, "kap_zeile19_zinsen") for d in berichte), 2)
    if tg or tv or bz:
        kap_block = s["anlagen"].setdefault("KAP", {
            "kapitalertraege": 0.0, "kapitalertragsteuer": 0.0, "soli": 0.0,
            "freistellungsauftrag_genutzt": 0.0,
            "auslaendische_quellensteuer": 0.0,
            "sparer_pauschbetrag": cfg["sparer_pauschbetrag"] *
                (2 if zusammen else 1),
            "quellen": []})
        kap_block["termingeschaefte_gewinne"] = tg
        kap_block["termingeschaefte_verluste"] = tv
        kap_block["auslaendische_zinsen"] = bz

    # ---------- Anlage SO (Krypto) ----------
    if crypto:
        s["anlagen"]["SO"] = {
            "quelle": "FIFO-Engine (Krypto-Tab)",
            "pro_person": crypto["pro_person"],
            "freigrenze_pro_person": cfg["freigrenze_private_veraeusserung"],
        }
    so_docs = cat(docs, "krypto_report")
    if so_docs and not crypto:
        gewinn = round(sum(
            ed(d, "gewinn_steuerpflichtig", d.get("betrag_eur"))
            for d in so_docs), 2)
        s["anlagen"]["SO"] = {
            "gewinn_steuerpflichtig": gewinn,
            "gewinn_steuerfrei_haltefrist": round(sum(
                ed(d, "gewinn_steuerfrei") for d in so_docs), 2),
            "verluste": round(sum(ed(d, "verluste") for d in so_docs), 2),
            "freigrenze": cfg["freigrenze_private_veraeusserung"],
            "steuerpflichtig": gewinn >= cfg["freigrenze_private_veraeusserung"],
            "quellen": [d["dateiname"] for d in so_docs],
        }

    # ---------- Sonderausgaben / Spenden ----------
    spenden = cat(docs, "spende")
    if spenden:
        s["anlagen"]["Sonderausgaben"] = {
            "spenden_summe": round(sum(_num(d.get("betrag_eur")) for d in spenden), 2),
            "belege": [{"datei": d["dateiname"], "organisation": d.get("aussteller"),
                        "betrag": _num(d.get("betrag_eur"))} for d in spenden],
        }

    # ---------- Vorsorgeaufwand ----------
    vorsorge = cat(docs, "vorsorge_versicherung")
    if vorsorge:
        s["anlagen"]["Vorsorgeaufwand"] = {
            "summe_belege": round(sum(_num(d.get("betrag_eur")) for d in vorsorge), 2),
            "belege": [{"datei": d["dateiname"], "versicherung": d.get("aussteller"),
                        "betrag": _num(d.get("betrag_eur"))} for d in vorsorge],
        }

    # ---------- § 35a ----------
    h35a = cat(docs, "handwerker_haushaltsnah")
    nk = cat(docs, "nebenkostenabrechnung")
    if h35a or nk:
        arbeitskosten = round(
            sum(ed(d, "arbeitskosten", d.get("betrag_eur")) for d in h35a)
            + sum(ed(d, "summe_handwerker") + ed(d, "summe_haushaltsnah")
                  for d in nk), 2)
        s["anlagen"]["Haushaltsnahe Aufwendungen"] = {
            "arbeitskosten_gesamt": arbeitskosten,
            "ermaessigung_geschaetzt": round(min(
                arbeitskosten * 0.20, cfg["handwerker_max_ermaessigung"]), 2),
            "belege": [{"datei": d["dateiname"], "firma": d.get("aussteller"),
                        "arbeitskosten": ed(d, "arbeitskosten", d.get("betrag_eur"))}
                       for d in h35a] +
                      [{"datei": d["dateiname"],
                        "firma": "NK-Abrechnung (automatisch)",
                        "arbeitskosten": ed(d, "summe_handwerker")
                        + ed(d, "summe_haushaltsnah")} for d in nk],
        }

    # ---------- Außergewöhnliche Belastungen ----------
    agb = cat(docs, "krankheitskosten")
    if agb:
        s["anlagen"]["Außergewöhnliche Belastungen"] = {
            "summe_belege": round(sum(_num(d.get("betrag_eur")) for d in agb), 2),
            "hinweis": "Wirkt erst oberhalb der zumutbaren Belastung "
                       "(§ 33 Abs. 3 EStG, dreistufig 1–7 % des Gesamtbetrags "
                       "der Einkünfte je nach Familienstand/Kinderzahl – "
                       "genauer Wert im Rechenweg des Tabs 'Ergebnis & "
                       "ELSTER').",
        }

    # ---------- Behinderten-/Pflege-Pauschbetrag, § 33a-Unterhalt ----------
    from .veranlagung import _behinderten_pflege_unterhalt
    pauschale_summe, pauschale_hinweise = _behinderten_pflege_unterhalt(
        interview, cfg)
    if pauschale_summe:
        s["anlagen"]["Behinderung, Pflege & Unterhalt"] = {
            "summe": pauschale_summe, "hinweise": pauschale_hinweise,
        }

    # ---------- Anlage R (Renten) ----------
    renten_docs = cat(docs, "rentenbezugsmitteilung")
    if renten_docs:
        from .rente import rentenanteil_steuerpflichtig
        eintraege = []
        for d in renten_docs:
            jahresbetrag = ed(d, "jahresbetrag_rente", d.get("betrag_eur"))
            beginn = int(ed(d, "rentenbeginn_jahr", 0))
            r = rentenanteil_steuerpflichtig(jahresbetrag, beginn, cfg)
            eintraege.append({
                "inhaber": d.get("inhaber", "P1"), "datei": d["dateiname"],
                "rentenbeginn_jahr": beginn, **r})
        s["anlagen"]["R"] = {"eintraege": eintraege}

    # ---------- Anlage AV (Riester) ----------
    riester_beitrag = {p: _num(interview.get(f"riester_beitrag_{p}"))
                       for p in ("P1", "P2")}
    if any(riester_beitrag.values()):
        s["anlagen"]["AV"] = {
            "beitraege": riester_beitrag,
            "kinder_ab_2008": int(_num(interview.get("riester_kinder_ab_2008"))),
            "kinder_vor_2008": int(_num(interview.get("riester_kinder_vor_2008"))),
            "max_beitrag": cfg["riester_max_beitrag"],
        }

    # ---------- Gewerbe & Selbständigkeit (Anlage G / Anlage EÜR) ----------
    betriebe_daten = interview.get("_betriebe")
    if betriebe_daten and betriebe_daten.get("betriebe"):
        s["anlagen"]["Gewerbe & Selbständigkeit (EÜR)"] = {
            "betriebe": betriebe_daten["betriebe"],
            "gewinn_pro_person": betriebe_daten["gewinn_pro_person"],
        }

    # ---------- Herkunft der Werte (Zuordnungs-Historie) ----------
    # Nur Dokumente, deren Zuordnung über die reine Automatik hinausging
    # (manuell korrigiert oder per Klärungs-Chat) – sonst wäre der Anhang
    # bei jedem Beleg redundant mit "automatisch erkannt".
    s["dokumente_historie"] = [
        {"dateiname": d["dateiname"], "historie": d["zuordnungs_historie"]}
        for d in docs
        if len(d.get("zuordnungs_historie") or []) > 1]

    return s


def render_elster_help(s: dict, erklaeren: bool = True) -> str:
    """Formatiert die Zusammenfassung als Markdown-Eingabehilfe für ELSTER."""
    e = lambda v: f"{v:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")
    out = [
        f"# ELSTER-Eingabehilfe – Steuerjahr {s['steuerjahr']}",
        f"*Erstellt am {s['erstellt']} – alle Werte vor Übertragung mit den "
        "Originalbelegen abgleichen.*",
        "",
        "**Tipp:** In ELSTER zuerst den **Belegabruf (vorausgefüllte "
        "Steuererklärung)** aktivieren – Lohnsteuerbescheinigungen und "
        "KV-Beiträge werden dann automatisch importiert und du musst nur "
        "noch abgleichen.",
        "",
    ]

    st_daten = s.get("stammdaten") or {}
    if st_daten:
        out.append("## Stammdaten (Hauptvordruck)")
        felder = [("finanzamt", "Finanzamt"),
                  ("steuernummer", "Gemeinsame Steuernummer"),
                  ("steuer_id_P1", "Steuer-ID Person 1"),
                  ("steuer_id_P2", "Steuer-ID Person 2"),
                  ("iban", "IBAN (Erstattung)"),
                  ("religion_P1", "Religion Person 1"),
                  ("religion_P2", "Religion Person 2")]
        for key, lbl in felder:
            if st_daten.get(key):
                out.append(f"- {lbl}: {st_daten[key]}")
        out.append("")

    vv = s.get("verlustvortraege") or {}
    if any(vv.values()):
        out.append("## Verlustvorträge aus Vorjahren")
        if vv.get("p23"):
            out.append(f"- § 23 (Krypto/priv. Veräußerung): {e(vv['p23'])} "
                       "→ Anlage SO, Verrechnung mit diesjährigen Gewinnen")
        if vv.get("kap_aktien"):
            out.append(f"- Aktienveräußerungsverluste: {e(vv['kap_aktien'])} "
                       "→ Anlage KAP")
        if vv.get("kap_sonstige"):
            out.append(f"- Sonstige Kapitalverluste: {e(vv['kap_sonstige'])} "
                       "→ Anlage KAP")
        out.append("")

    from .erklaerungen import ANLAGEN_ERKLAERT

    def erk(key):
        if erklaeren and key in ANLAGEN_ERKLAERT:
            out.append(ANLAGEN_ERKLAERT[key])
            out.append("")

    n = s["anlagen"].get("N")
    if n:
        out.append("## Anlage N – Einkünfte aus nichtselbständiger Arbeit")
        erk("N")
        namen = {p: w.get("name", p)
                 for p, w in n.get("werbungskosten_pro_person", {}).items()}
        for av in n["arbeitsverhaeltnisse"]:
            tag = " (Bundeswehr/Übergangsgebührnisse)" if av["ist_bundeswehr"] else ""
            wer = namen.get(av.get("inhaber", "P1"), "")
            out += [
                f"### {av['arbeitgeber']}{tag} – {wer}",
                f"- Quelle: `{av['quelle']}`",
                f"- Bruttoarbeitslohn (eBescheinigung Z. 3): {e(av['bruttoarbeitslohn'])}",
                f"- Einbehaltene Lohnsteuer (Z. 4): {e(av['lohnsteuer'])}",
                f"- Solidaritätszuschlag (Z. 5): {e(av['soli'])}",
                f"- Kirchensteuer (Z. 6/7): {e(av['kirchensteuer'])}",
                f"- Steuerklasse: {av['steuerklasse'] or '–'}",
                "",
            ]
        for p_key, wk in n.get("werbungskosten_pro_person", {}).items():
            out += [
                f"### Werbungskosten – {wk['name']} (eigene Anlage N!)",
                f"- Entfernungspauschale: {wk['entfernungspauschale']['km']:.0f} km × "
                f"{wk['entfernungspauschale']['tage']} Tage = "
                f"{e(wk['entfernungspauschale']['betrag'])}",
                f"- Homeoffice-Pauschale: {wk['homeoffice_pauschale']['tage']} Tage = "
                f"{e(wk['homeoffice_pauschale']['betrag'])}",
                f"- Belege: {e(wk['belege_summe'])}",
                f"- **Summe: {e(wk['gesamt'])}** "
                f"(eigener Pauschbetrag: {e(wk['pauschbetrag'])})",
                ("- ✅ Einzelnachweis lohnt sich – Werte eintragen!"
                 if wk["einzelnachweis_lohnt"] else
                 "- ℹ️ Unter dem Pauschbetrag – greift automatisch."),
                "",
            ]
        if n.get("uebergangsbeihilfe"):
            out.append("### Übergangsbeihilfe (Einmalzahlung Bundeswehr)")
            for ub in n["uebergangsbeihilfe"]:
                out.append(f"- `{ub['datei']}` ({ub['inhaber']}): "
                           f"{e(ub['betrag'])} – als zusätzlicher Arbeitslohn "
                           "in die Schätzung eingerechnet.")
                if ub["lohnsteuer"] or ub["soli"] or ub["kirchensteuer"]:
                    out.append(
                        f"  - Bereits einbehalten: Lohnsteuer "
                        f"{e(ub['lohnsteuer'])}, Soli {e(ub['soli'])}, "
                        f"Kirchensteuer {e(ub['kirchensteuer'])} "
                        "(in der Schätzung als bereits gezahlt berücksichtigt).")
            out += [
                "- ℹ️ **Fünftelregelung (§ 34 EStG):** Die Schätzung vergleicht "
                "automatisch volle Besteuerung mit der Fünftelregelung "
                "(Rechenweg unten) und nutzt die günstigere Variante. "
                "Voraussetzung ist eine 'Vergütung für mehrjährige "
                "Tätigkeit' (§ 34 Abs. 2 Nr. 4 EStG) – bei Unsicherheit "
                "Steuerberater/Lohnsteuerhilfeverein hinzuziehen. In ELSTER "
                "ggf. die Zeile 'ermäßigt zu besteuernde Entschädigung' "
                "ausfüllen.",
                "",
            ]

    kap = s["anlagen"].get("KAP")
    if kap:
        out.append("## Anlage KAP – Kapitalerträge (Aktien/Dividenden)")
        erk("KAP")
        out += [
            f"- Kapitalerträge (Zeile 7): {e(kap['kapitalertraege'])}",
            f"- In Anspruch genommener Sparer-Pauschbetrag: "
            f"{e(kap['freistellungsauftrag_genutzt'])} von "
            f"{e(kap['sparer_pauschbetrag'])}",
            f"- Einbehaltene Kapitalertragsteuer (Z. 37): "
            f"{e(kap['kapitalertragsteuer'])}",
            f"- Einbehaltener Soli (Z. 38): {e(kap['soli'])}",
            f"- Anrechenbare ausländische Quellensteuer (Z. 41): "
            f"{e(kap['auslaendische_quellensteuer'])}",
            "- Günstigerprüfung: Zeile 4 ankreuzen, falls Grenzsteuersatz < 25 %.",
        ]
        if kap.get("termingeschaefte_gewinne") or \
                kap.get("termingeschaefte_verluste") or \
                kap.get("auslaendische_zinsen"):
            out += [
                f"- Ausländische Zinsen (Zeile 19): "
                f"{e(kap.get('auslaendische_zinsen', 0))}",
                f"- Gewinne aus Termingeschäften (Zeile 21): "
                f"{e(kap.get('termingeschaefte_gewinne', 0))}",
                f"- Verluste aus Termingeschäften (Zeile 24): "
                f"{e(kap.get('termingeschaefte_verluste', 0))}",
                "- ⚠️ Auslandsbroker (Phemex/eToro): keine Steuer einbehalten "
                "→ ~26,4 % werden per Bescheid festgesetzt, Nachzahlung "
                "einplanen. Verluste seit JStG 2024 voll verrechenbar.",
            ]
        out.append("")

    so = s["anlagen"].get("SO")
    if so and "pro_person" in so:
        out.append("## Anlage SO – Private Veräußerungsgeschäfte (Krypto, "
                   "FIFO-Engine)")
        erk("SO")
        namen = {"P1": "Ehegatte/Person 1", "P2": "Ehegatte/Person 2"}
        for p_key, a in so["pro_person"].items():
            a = {**{"veraeusserungen": 0, "rewards_summe": 0.0,
                    "netto_gewinn": 0.0, "gewinn_brutto": 0.0,
                    "verluste": 0.0, "gebuehren": 0.0,
                    "gewinn_steuerfrei_haltefrist": 0.0,
                    "freigrenze": 1000.0, "unter_freigrenze": True,
                    "steuerpflichtiger_betrag": a.get(
                        "steuerpflichtiger_betrag", 0.0),
                    "rewards_steuerpflichtig": 0.0}, **a}
            if not (a["veraeusserungen"] or a["rewards_summe"]
                    or a["steuerpflichtiger_betrag"]):
                continue
            out += [
                f"### {namen[p_key]} (eigene Anlage SO!)",
                f"- Veräußerungen mit Haltefrist < 1 Jahr: Netto-Gewinn "
                f"{e(a['netto_gewinn'])} (Gewinne {e(a['gewinn_brutto'])}, "
                f"Verluste {e(a['verluste'])})",
                f"- Abgezogene Gebühren: {e(a['gebuehren'])}",
                f"- Steuerfrei nach > 1 Jahr Haltefrist (NICHT eintragen): "
                f"{e(a['gewinn_steuerfrei_haltefrist'])}",
                (f"- ✅ Unter der Freigrenze {e(a['freigrenze'])} → 0 € "
                 "steuerpflichtig (Zeile 54: Angabe empfohlen)."
                 if a["unter_freigrenze"] else
                 f"- ⚠️ Einzutragender steuerpflichtiger Gewinn: "
                 f"{e(a['steuerpflichtiger_betrag'])}"),
            ]
            if a["rewards_summe"]:
                out.append(
                    f"- Staking/Rewards (§ 22 Nr. 3, Anlage SO Zeile 10 ff.): "
                    f"{e(a['rewards_summe'])} → steuerpflichtig: "
                    f"{e(a['rewards_steuerpflichtig'])}")
            out.append("")
    elif so:
        out += [
            "## Anlage SO – Private Veräußerungsgeschäfte (Krypto)",
            f"- Steuerpflichtiger Gewinn (Haltefrist < 1 Jahr): "
            f"{e(so['gewinn_steuerpflichtig'])}",
            f"- Steuerfrei (Haltefrist > 1 Jahr, NICHT eintragen): "
            f"{e(so['gewinn_steuerfrei_haltefrist'])}",
            f"- Verluste: {e(so['verluste'])}",
            (f"- ⚠️ Freigrenze {e(so['freigrenze'])} überschritten → gesamter "
             "Gewinn steuerpflichtig."
             if so["steuerpflichtig"] else
             f"- ✅ Unter der Freigrenze {e(so['freigrenze'])} → steuerfrei "
             "(Angabe trotzdem empfohlen, Zeile 54: Gewinn unter Freigrenze)."),
            "- Krypto-Report als Nachweis aufbewahren (Vorhaltepflicht).",
            "",
        ]

    gew = s["anlagen"].get("Gewerbe & Selbständigkeit (EÜR)")
    if gew:
        out.append("## Gewerbe & Selbständigkeit – Anlage G / Anlage EÜR")
        erk("Gewerbe & Selbständigkeit (EÜR)")
        namen = {"P1": "Person 1", "P2": "Person 2"}
        for r in gew["betriebe"]:
            anlage = ("Anlage V" if r["art"] == "vermietung" else
                     "Anlage S" if r["art"] == "freiberuflich" else "Anlage G")
            out += [
                f"### {r['betrieb']} ({anlage}) – "
                f"{namen.get(r['inhaber'], r['inhaber'])}",
                f"- Betriebseinnahmen: {e(r['einnahmen'])}",
                f"- Betriebsausgaben: {e(r['ausgaben'])}",
                f"- Abschreibungen (AfA): {e(r['afa'])}",
                f"- **Gewinn/Überschuss {r['jahr']}: {e(r['gewinn'])}**",
            ]
            if r["afa_positionen"]:
                out.append("- AfA-Positionen:")
                for a in r["afa_positionen"]:
                    out.append(
                        f"  - {a['bezeichnung']}: {e(a['anschaffungskosten'])} "
                        f"({a['anschaffungsdatum']}, "
                        f"{a['nutzungsdauer_jahre']} Jahre ND) → "
                        f"AfA {r['jahr']}: {e(a['afa_jahr'])}")
            for h in r["hinweise"]:
                out.append(f"- {'⚠️ ' if '⚠️' in h else 'ℹ️ '}{h}")
            out.append("")
        gesamt = sum(gew["gewinn_pro_person"].values())
        out += [f"**Gesamtgewinn aus Gewerbe/Selbständigkeit: {e(gesamt)}** "
               "(fließt in die Summe der Einkünfte ein).", ""]

    for name in ("Sonderausgaben", "Vorsorgeaufwand",
                 "Haushaltsnahe Aufwendungen", "Außergewöhnliche Belastungen",
                 "Behinderung, Pflege & Unterhalt"):
        block = s["anlagen"].get(name)
        if not block:
            continue
        out.append(f"## {name}")
        erk(name)
        for k, v in block.items():
            if k == "belege":
                for b in v:
                    parts = [f"`{b.get('datei')}`"]
                    for f in ("organisation", "versicherung", "firma"):
                        if b.get(f):
                            parts.append(str(b[f]))
                    betrag = b.get("betrag", b.get("arbeitskosten"))
                    out.append(f"- {' – '.join(parts)}: {e(_num(betrag))}")
            elif k == "hinweise" and isinstance(v, list):
                for h in v:
                    out.append(f"- {h}")
            elif isinstance(v, (int, float)):
                out.append(f"- {k.replace('_', ' ').capitalize()}: {e(v)}")
            elif isinstance(v, str):
                out.append(f"- {v}")
        out.append("")

    r = s["anlagen"].get("R")
    if r:
        out.append("## Anlage R – Renten")
        erk("R")
        gesamt_stpfl = 0.0
        namen = {"P1": "Person 1", "P2": "Person 2"}
        for eintrag in r["eintraege"]:
            out += [
                f"### {namen.get(eintrag['inhaber'], eintrag['inhaber'])} – "
                f"`{eintrag['datei']}`",
                f"- Jahresbetrag: {e(eintrag['jahresbetrag'])}",
                f"- Rentenbeginn: {eintrag['rentenbeginn_jahr'] or '–'} "
                f"→ Besteuerungsanteil {eintrag['besteuerungsanteil_prozent']:.1f} %",
                f"- Steuerpflichtiger Anteil (Zeile 4/5 Anlage R): "
                f"{e(eintrag['steuerpflichtiger_anteil'])}",
                f"- Steuerfreier Anteil (NICHT eintragen): "
                f"{e(eintrag['steuerfreier_anteil'])}",
                "",
            ]
            gesamt_stpfl += eintrag["steuerpflichtiger_anteil"]
        out += [f"**Steuerpflichtiger Rentenanteil gesamt: {e(gesamt_stpfl)}** "
               "(fließt in die Summe der Einkünfte ein).", ""]

    av = s["anlagen"].get("AV")
    if av:
        out.append("## Anlage AV – Riester-Rente")
        erk("AV")
        namen = {"P1": "Person 1", "P2": "Person 2"}
        for p, betrag in av["beitraege"].items():
            if betrag:
                out.append(f"- Eigenbeitrag {namen.get(p, p)}: {e(betrag)} "
                           f"(Höchstbetrag: {e(av['max_beitrag'])})")
        if av["kinder_ab_2008"] or av["kinder_vor_2008"]:
            out.append(
                f"- Kinderzulage: {av['kinder_ab_2008']} Kind(er) ab "
                f"Geburtsjahrgang 2008, {av['kinder_vor_2008']} davor.")
        out += [
            "- Die Günstigerprüfung (Sonderausgabenabzug vs. Zulage) "
            "übernimmt das Finanzamt automatisch – Ergebnis im Rechenweg "
            "des Tabs 'Ergebnis & ELSTER'.",
            "",
        ]

    sp = s.get("sparcheck") or {}
    if any(v > 0 for v in sp.values()):
        out.append("## Zusätzliche Posten aus dem Spar-Check "
                   "(Belege bereithalten!)")
        labels = {"wk_P1": "Werbungskosten Person 1 (Anlage N)",
                  "wk_P2": "Werbungskosten Person 2 (Anlage N)",
                  "sa": "Sonderausgaben",
                  "parteispenden": "Parteispenden (Hauptvordruck/§ 34g)",
                  "h35a_handwerker": "Handwerker-Arbeitskosten (§ 35a)",
                  "h35a_haushalt": "Haushaltsnahe Dienstleistungen (§ 35a)",
                  "h35a_minijob": "Haushalts-Minijob (§ 35a)",
                  "agb": "Außergewöhnliche Belastungen"}
        for k, v in sp.items():
            if v > 0:
                out.append(f"- {labels[k]}: {e(v)}")
        out.append("")

    historie = s.get("dokumente_historie") or []
    if historie:
        out += ["## Anhang: Herkunft der Werte", ""]
        for eintrag in historie:
            out.append(f"**`{eintrag['dateiname']}`**")
            for schritt in eintrag["historie"]:
                von = schritt.get("von") or "–"
                nach = schritt.get("nach") or "–"
                quelle_label = {"automatisch": "🤖 automatisch",
                               "chat": "💬 Chat-Klärung",
                               "manuell": "✍️ manuell"}.get(
                    schritt.get("quelle"), schritt.get("quelle", "–"))
                out.append(
                    f"- {schritt.get('zeitpunkt', '–')} · {quelle_label}: "
                    f"{schritt.get('aktion', '–')} ({von} → {nach})"
                    + (f" – _{schritt['begruendung']}_"
                       if schritt.get("begruendung") else ""))
            out.append("")

    out += [
        "---",
        "*Erstellt mit dem Steuer-Assistenten. Keine Steuerberatung im Sinne "
        "des StBerG – bei komplexen Fällen Steuerberater oder "
        "Lohnsteuerhilfeverein hinzuziehen.*",
    ]
    return "\n".join(out)


def export_json(s: dict, docs: list, findings: list) -> str:
    return json.dumps(
        {"zusammenfassung": s,
         "dokumente": [{k: v for k, v in d.items() if k != "_bytes"}
                       for d in docs],
         "pruefungen": findings},
        ensure_ascii=False, indent=2)
