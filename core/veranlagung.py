"""
Erstattungsrechner: vereinfachte Veranlagungsrechnung vom Bruttolohn bis
zur geschätzten Erstattung/Nachzahlung. Bewusst konservativ und als
SCHÄTZUNG gekennzeichnet – der Bescheid des Finanzamts kann abweichen.
"""

from .checks import _num, entfernungspauschale
from .crypto import est_nach_tarif
from .sparcheck import summen


def _ed(d, feld, fallback=None):
    return _num(d.get("extrahierte_daten", {}).get(feld, fallback))


def berechne_veranlagung(docs: list, cfg: dict, interview: dict) -> dict:
    zusammen = bool(interview.get("zusammenveranlagung"))
    aktive = ("P1", "P2") if zusammen else ("P1",)
    spar = summen(interview)
    crypto = interview.get("_crypto") or {"pro_person": {}}
    b = {"schritte": [], "warnhinweise": []}
    step = lambda text, wert: b["schritte"].append(
        {"text": text, "wert": round(wert, 2)})

    lsb = [d for d in docs if d.get("kategorie", "").startswith(
        "lohnsteuerbescheinigung")]

    # ---------- 1) Einkünfte aus nichtselbständiger Arbeit je Person
    summe_einkuenfte = 0.0
    uebergangsbeihilfe_docs = [d for d in docs
                              if d.get("kategorie") == "uebergangsbeihilfe"]
    for p in aktive:
        brutto = sum(_ed(d, "bruttoarbeitslohn", d.get("betrag_eur"))
                     for d in lsb if d.get("inhaber", "P1") == p)
        beihilfe = sum(_num(d.get("betrag_eur")) for d in uebergangsbeihilfe_docs
                       if d.get("inhaber", "P1") == p)
        if beihilfe:
            # Konservativ voll versteuert (Regeltarif) – die ggf. günstigere
            # Fünftelregelung (§ 34 EStG) wird hier NICHT berechnet, siehe
            # Hinweis in checks.py. Lieber zu viel als zu wenig Steuer schätzen.
            brutto += beihilfe
            step(f"+ Übergangsbeihilfe {p} (voll versteuert, "
                 "Fünftelregelung ungeprüft)", beihilfe)
        ep = entfernungspauschale(
            _num(interview.get(f"entfernung_km_{p}")),
            int(_num(interview.get(f"arbeitstage_{p}"))), cfg)
        ho = min(int(_num(interview.get(f"homeoffice_tage_{p}")))
                 * cfg["homeoffice_pauschale_pro_tag"], cfg["homeoffice_max"])
        belege = sum(_num(d.get("betrag_eur")) for d in docs
                     if d.get("kategorie") == "werbungskosten"
                     and d.get("inhaber", "P1") == p)
        wk = max(cfg["arbeitnehmer_pauschbetrag"],
                 ep + ho + belege + spar[f"wk_{p}"])
        einkuenfte = max(0.0, brutto - wk)
        step(f"Bruttolohn {p}", brutto)
        step(f"− Werbungskosten {p} (mind. Pauschbetrag)", -wk)
        summe_einkuenfte += einkuenfte

    # ---------- 1b) Einkünfte aus Gewerbebetrieb/selbständiger Arbeit (EÜR)
    betriebe_daten = interview.get("_betriebe") or {"gewinn_pro_person": {}}
    for p in aktive:
        gewinn = betriebe_daten["gewinn_pro_person"].get(p, 0.0)
        if gewinn:
            step(f"+ Gewinn aus Gewerbebetrieb/selbst. Arbeit {p} (EÜR)", gewinn)
            summe_einkuenfte += gewinn

    # ---------- 2) Sonstige Einkünfte (Krypto § 23 + § 22 Nr. 3)
    krypto_stpfl = sum(
        a.get("steuerpflichtiger_betrag", 0) + a.get("rewards_steuerpflichtig", 0)
        for a in crypto["pro_person"].values())
    if not crypto["pro_person"]:
        # Kein FIFO-Engine-Ergebnis vorhanden (Krypto-Tab nicht genutzt) –
        # Fallback auf hochgeladene krypto_report-Dokumente, sonst würde
        # dieser Gewinn in der Schätzung fehlen (steht aber in build_summary!).
        krypto_docs = [d for d in docs if d.get("kategorie") == "krypto_report"]
        krypto_stpfl = sum(_ed(d, "gewinn_steuerpflichtig", d.get("betrag_eur"))
                           for d in krypto_docs)
        if krypto_stpfl:
            b["warnhinweise"].append(
                "Krypto-Report-Dokument(e) ohne Nutzung des Krypto-Tabs "
                "(FIFO-Engine) erkannt – Gewinn wurde als grobe Schätzung "
                "aus dem Beleg übernommen. Für eine genaue, walletbezogene "
                "FIFO-Berechnung den Krypto-Tab nutzen.")
    if krypto_stpfl:
        step("+ Steuerpflichtige Krypto-Einkünfte (Anlage SO)", krypto_stpfl)
    summe_einkuenfte += krypto_stpfl
    step("= Summe der Einkünfte", summe_einkuenfte)

    # ---------- 3) Vorsorgeaufwendungen (aus Lohnsteuerbescheinigungen)
    vorsorge = sum(_ed(d, "rv_arbeitnehmer") + _ed(d, "kv_beitraege")
                   + _ed(d, "pv_beitraege") for d in lsb)
    if vorsorge == 0:
        # Fallback: grobe Näherung, falls SV-Zeilen nicht extrahiert wurden
        brutto_ges = sum(_ed(d, "bruttoarbeitslohn", d.get("betrag_eur"))
                         for d in lsb)
        vorsorge = round(brutto_ges * 0.19, 2)
        b["warnhinweise"].append(
            "SV-Beiträge (Zeilen 23–26) fehlten in den Bescheinigungen – "
            "Vorsorgeaufwand wurde mit ~19 % des Bruttos GESCHÄTZT.")
    step("− Vorsorgeaufwendungen (RV + KV + PV)", -vorsorge)
    b["warnhinweise"].append(
        "Zusätzliche Versicherungen (Haftpflicht, BU …) wirken sich bei "
        "Arbeitnehmern meist NICHT mehr aus (1.900 €-Deckel durch KV/PV "
        "bereits überschritten) – trotzdem eintragen, schadet nie.")

    # ---------- 4) Sonderausgaben
    spenden_belege = sum(_num(d.get("betrag_eur")) for d in docs
                         if d.get("kategorie") == "spende")
    kist_gezahlt = sum(_ed(d, "kirchensteuer") for d in lsb)
    sa = max(cfg["sonderausgaben_pauschbetrag"] * len(aktive),
             spenden_belege + spar["sa"] + kist_gezahlt)
    step("− Sonderausgaben (Spenden, Kirchensteuer, Betreuung …)", -sa)

    # ---------- 5) Außergewöhnliche Belastungen (über zumutbarer Grenze)
    agb_belege = sum(_num(d.get("betrag_eur")) for d in docs
                     if d.get("kategorie") == "krankheitskosten")
    agb = agb_belege + spar["agb"]
    zumutbar = round(summe_einkuenfte * (0.04 if zusammen else 0.06), 2)
    agb_wirksam = max(0.0, agb - zumutbar)
    if agb > 0:
        step(f"− Außergew. Belastungen über zumutbarer Grenze "
             f"(~{zumutbar:,.0f} €)".replace(",", "."), -agb_wirksam)

    zve = max(0.0, summe_einkuenfte - vorsorge - sa - agb_wirksam)
    step("= zu versteuerndes Einkommen (zvE)", zve)

    # ---------- 6) Tarifliche ESt (Splitting)
    est = (2 * est_nach_tarif(zve / 2, cfg)) if zusammen \
        else est_nach_tarif(zve, cfg)
    step(f"Tarifliche Einkommensteuer ({'Splitting' if zusammen else 'Grundtarif'})", est)

    # ---------- 7) Direkte Steuerermäßigungen
    handwerker_belege = sum(_ed(d, "arbeitskosten", d.get("betrag_eur"))
                            for d in docs
                            if d.get("kategorie") == "handwerker_haushaltsnah")
    nk_handwerker = sum(_ed(d, "summe_handwerker") for d in docs
                        if d.get("kategorie") == "nebenkostenabrechnung")
    nk_haushalt = sum(_ed(d, "summe_haushaltsnah") for d in docs
                      if d.get("kategorie") == "nebenkostenabrechnung")
    erm_handwerker = min(
        0.20 * (handwerker_belege + nk_handwerker + spar["h35a_handwerker"]),
        cfg["handwerker_max_ermaessigung"])
    erm_haushalt = min(0.20 * (nk_haushalt + spar["h35a_haushalt"]),
                       cfg["haushaltsnahe_max_ermaessigung"])
    erm_minijob = min(0.20 * spar["h35a_minijob"], 510.0)
    erm_partei = min(0.50 * spar["parteispenden"],
                     1650.0 if zusammen else 825.0)
    for lbl, wert in [("− § 35a Handwerker (20 %)", erm_handwerker),
                      ("− § 35a Haushaltsnahe Dienste (20 %)", erm_haushalt),
                      ("− § 35a Haushalts-Minijob (20 %)", erm_minijob),
                      ("− § 34g Parteispenden (50 %)", erm_partei)]:
        if wert > 0:
            step(lbl, -wert)
    est_fest = max(0.0, est - erm_handwerker - erm_haushalt
                   - erm_minijob - erm_partei)
    step("= festzusetzende Einkommensteuer", est_fest)

    # ---------- 8) Soli & Kirchensteuer (festzusetzen)
    soli_grenze = cfg.get("soli_freigrenze_zusammen" if zusammen
                          else "soli_freigrenze_einzel", 0)
    soli_fest = round(est_fest * 0.055, 2) if est_fest > soli_grenze else 0.0
    if soli_fest:
        b["warnhinweise"].append(
            "Soli: über der Freigrenze grob mit 5,5 % gerechnet – in der "
            "Milderungszone fällt er real niedriger aus.")
    kist_fest = round(est_fest * 0.09, 2) \
        if interview.get("kirchensteuerpflichtig") else 0.0

    # ---------- 9) Bereits gezahlt
    lst_gezahlt = sum(_ed(d, "lohnsteuer") for d in lsb)
    soli_gezahlt = sum(_ed(d, "soli") for d in lsb)
    step("Bereits gezahlte Lohnsteuer", lst_gezahlt)

    # ---------- 10) KAP-Erstattungspotenzial (Sparer-Pauschbetrag)
    kap_docs = [d for d in docs
                if d.get("kategorie") == "steuerbescheinigung_bank"]
    ertraege = sum(_ed(d, "kapitalertraege_zeile7", d.get("betrag_eur"))
                   for d in kap_docs)
    fsa = sum(_ed(d, "in_anspruch_genommener_freistellungsauftrag")
              for d in kap_docs)
    pb_kap = cfg["sparer_pauschbetrag"] * len(aktive)
    kap_erstattung = round(
        max(0.0, min(ertraege, pb_kap) - fsa) * 0.25 * 1.055, 2)
    if kap_erstattung:
        step("+ Rückholbare Abgeltungsteuer (ungenutzter "
             "Sparer-Pauschbetrag)", kap_erstattung)

    # ---------- 11) Abgeltungsteuer auf Auslands-KAP (Termingeschäfte, Zinsen)
    berichte = [d for d in docs if d.get("kategorie") == "broker_steuerbericht"]
    tg = sum(_num(interview.get(f"termin_gewinne_{p}")) for p in aktive) + \
        sum(_ed(d, "kap_zeile21_termingewinne") for d in berichte)
    tv = sum(_num(interview.get(f"termin_verluste_{p}")) for p in aktive) + \
        sum(_ed(d, "kap_zeile24_terminverluste") for d in berichte)
    bz = sum(_num(interview.get(f"broker_zinsen_{p}")) for p in aktive) + \
        sum(_ed(d, "kap_zeile19_zinsen") for d in berichte)
    if berichte:
        b["warnhinweise"].append(
            "Broker-Steuerberichte automatisch übernommen (KAP): " +
            ", ".join(d.get("aussteller") or d["dateiname"] for d in berichte) +
            ". Achtung: Dieselben Werte NICHT zusätzlich manuell im "
            "Termingeschäfte-Feld eintragen (Doppelung).")
    kap_zusatz = 0.0
    if tg or tv or bz:
        pb_rest = max(0.0, pb_kap - ertraege)
        bemessung = max(0.0, tg - tv + bz - pb_rest)
        kap_zusatz = round(bemessung * 0.26375, 2)  # 25 % + Soli
        if kap_zusatz:
            step("− Abgeltungsteuer Auslandsbroker (Termingeschäfte/Zinsen, "
                 "~26,375 %)", -kap_zusatz)
            b["warnhinweise"].append(
                "Auslandsbroker haben keine Steuer einbehalten – die "
                "Abgeltungsteuer wird per Bescheid festgesetzt (hier als "
                "Nachzahlung eingerechnet, ggf. zzgl. Kirchensteuer).")

    ergebnis = round((lst_gezahlt + soli_gezahlt + kist_gezahlt
                      + kap_erstattung)
                     - (est_fest + soli_fest + kist_fest + kap_zusatz), 2)

    b.update({
        "zve": round(zve, 2), "est_tariflich": round(est, 2),
        "est_fest": round(est_fest, 2), "soli_fest": soli_fest,
        "kist_fest": kist_fest, "gezahlt_gesamt": round(
            lst_gezahlt + soli_gezahlt + kist_gezahlt, 2),
        "kap_erstattung": kap_erstattung,
        "ergebnis": ergebnis,   # + = Erstattung, − = Nachzahlung
        "hat_lsb": bool(lsb),
    })
    return b
