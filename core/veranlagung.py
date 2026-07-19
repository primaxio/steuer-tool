"""
Erstattungsrechner: vereinfachte Veranlagungsrechnung vom Bruttolohn bis
zur geschätzten Erstattung/Nachzahlung. Bewusst konservativ und als
SCHÄTZUNG gekennzeichnet – der Bescheid des Finanzamts kann abweichen.
"""

from .checks import _num, entfernungspauschale
from .crypto import est_nach_tarif
from .fuenftelregelung import fuenftelregelung
from .rente import rentenanteil_steuerpflichtig
from .sparcheck import summen


def _ed(d, feld, fallback=None):
    return _num(d.get("extrahierte_daten", {}).get(feld, fallback))


def _tarif(zve: float, zusammen: bool, cfg: dict) -> float:
    """Tarifliche ESt (Grundtarif/Splitting) für eine zvE-Grenzbetrachtung."""
    zve = max(0.0, zve)
    return (2 * est_nach_tarif(zve / 2, cfg)) if zusammen \
        else est_nach_tarif(zve, cfg)


def _zumutbare_belastung(gesamtbetrag_einkuenfte: float, zusammen: bool,
                         kinderzahl: int, cfg: dict) -> float:
    """§ 33 Abs. 3 EStG, dreistufige Berechnung (BFH VI R 75/14): auf den
    Einkommensanteil bis 15.340 € gilt der niedrigste Satz der jeweiligen
    Spalte, auf den Anteil 15.340–51.130 € der mittlere, auf den Rest der
    höchste Satz. Sätze hängen von Familienstand/Kinderzahl ab."""
    if kinderzahl >= 3:
        key = "kinder_3plus"
    elif kinderzahl >= 1:
        key = "kinder_1_2"
    elif zusammen:
        key = "verheiratet"
    else:
        key = "ledig"
    satz1, satz2, satz3 = cfg["zumutbare_belastung_saetze"][key]
    stufe1, stufe2 = cfg["zumutbare_belastung_stufen"]
    g = max(0.0, gesamtbetrag_einkuenfte)
    teil1 = min(g, stufe1) * satz1
    teil2 = max(0.0, min(g, stufe2) - stufe1) * satz2
    teil3 = max(0.0, g - stufe2) * satz3
    return round(teil1 + teil2 + teil3, 2)


def _behinderten_pflege_unterhalt(interview: dict, cfg: dict) -> tuple:
    """§ 33b EStG (Behinderten-/Pflege-Pauschbetrag) und § 33a EStG
    (Unterhalt) – anders als Krankheitskosten OHNE Kürzung um die
    zumutbare Belastung, deshalb als eigener Block direkt vom
    Gesamtbetrag der Einkünfte abgezogen. Gibt (summe, hinweise) zurück."""
    summe = 0.0
    hinweise = []
    for p in ("P1", "P2"):
        gdb = int(_num(interview.get(f"gdb_{p}")))
        if gdb >= 20:
            if interview.get(f"gdb_hilflos_blind_{p}"):
                betrag = cfg["behinderten_pauschbetrag_hilflos_blind"]
            else:
                stufe = max((g for g in cfg["behinderten_pauschbetrag"]
                            if g <= gdb), default=0)
                betrag = cfg["behinderten_pauschbetrag"].get(stufe, 0.0)
            if betrag:
                summe += betrag
                hinweise.append(
                    f"Behinderten-Pauschbetrag {p} (GdB {gdb}): "
                    f"{betrag:.2f} € – ohne Einzelnachweis, ohne Kürzung "
                    "um die zumutbare Belastung.")
    pflegegrad = int(_num(interview.get("pflegegrad_angehoeriger")))
    if pflegegrad >= 2:
        betrag = cfg["pflege_pauschbetrag"].get(
            min(pflegegrad, 5), cfg["pflege_pauschbetrag"][5])
        summe += betrag
        hinweise.append(
            f"Pflege-Pauschbetrag (Pflegegrad {pflegegrad}, unentgeltliche "
            f"häusliche Pflege): {betrag:.2f} € – ohne Kürzung um die "
            "zumutbare Belastung.")
    unterhalt_betrag = _num(interview.get("unterhalt_betrag"))
    if unterhalt_betrag:
        anrechnungsfrei = cfg["unterhalt_anrechnungsfreier_betrag"]
        eigene_einkuenfte = _num(interview.get("unterhalt_eigene_einkuenfte"))
        kuerzung = max(0.0, eigene_einkuenfte - anrechnungsfrei)
        hoechstbetrag = cfg["grundfreibetrag"]
        abzugsfaehig = max(0.0, min(unterhalt_betrag, hoechstbetrag) - kuerzung)
        if abzugsfaehig:
            summe += abzugsfaehig
            hinweise.append(
                f"§ 33a-Unterhalt: {abzugsfaehig:.2f} € abzugsfähig "
                f"(Höchstbetrag {hoechstbetrag:.2f} € = Grundfreibetrag, "
                f"gekürzt um eigene Einkünfte/Bezüge des Empfängers über "
                f"{anrechnungsfrei:.2f} € anrechnungsfreiem Betrag) – "
                "ohne Kürzung um die zumutbare Belastung.")
    return round(summe, 2), hinweise


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
    summe_einkuenfte_ohne_beihilfe = 0.0
    beihilfe_gesamt = 0.0
    uebergangsbeihilfe_docs = [d for d in docs
                              if d.get("kategorie") == "uebergangsbeihilfe"]
    for p in aktive:
        brutto_ohne_beihilfe = sum(
            _ed(d, "bruttoarbeitslohn", d.get("betrag_eur"))
            for d in lsb if d.get("inhaber", "P1") == p)
        beihilfe = sum(_num(d.get("betrag_eur")) for d in uebergangsbeihilfe_docs
                       if d.get("inhaber", "P1") == p)
        brutto = brutto_ohne_beihilfe + beihilfe
        if beihilfe:
            beihilfe_gesamt += beihilfe
            step(f"+ Übergangsbeihilfe {p} (Zuordnung Fünftelregelung "
                 "vs. volle Besteuerung folgt nach dem Tarifschritt)",
                 beihilfe)
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
        summe_einkuenfte_ohne_beihilfe += max(0.0, brutto_ohne_beihilfe - wk)

    # ---------- 1b) Einkünfte aus Gewerbebetrieb/selbständiger Arbeit (EÜR)
    betriebe_daten = interview.get("_betriebe") or {"gewinn_pro_person": {}}
    for p in aktive:
        gewinn = betriebe_daten["gewinn_pro_person"].get(p, 0.0)
        if gewinn:
            step(f"+ Gewinn aus Gewerbebetrieb/selbst. Arbeit {p} (EÜR)", gewinn)
            summe_einkuenfte += gewinn
            summe_einkuenfte_ohne_beihilfe += gewinn

    # ---------- 1c) Einkünfte aus Renten (Anlage R, § 22 Nr. 1 EStG)
    renten_docs = [d for d in docs if d.get("kategorie") == "rentenbezugsmitteilung"]
    for p in aktive:
        for d in renten_docs:
            if d.get("inhaber", "P1") != p:
                continue
            jahresbetrag = _ed(d, "jahresbetrag_rente", d.get("betrag_eur"))
            beginn = int(_ed(d, "rentenbeginn_jahr", 0))
            if not jahresbetrag:
                continue
            r = rentenanteil_steuerpflichtig(jahresbetrag, beginn, cfg)
            if r["steuerpflichtiger_anteil"]:
                step(f"+ Rente {p} (Besteuerungsanteil "
                     f"{r['besteuerungsanteil_prozent']:.1f} %, "
                     f"Rentenbeginn {beginn or '?'})",
                     r["steuerpflichtiger_anteil"])
                summe_einkuenfte += r["steuerpflichtiger_anteil"]
                summe_einkuenfte_ohne_beihilfe += r["steuerpflichtiger_anteil"]
                if not beginn:
                    b["warnhinweise"].append(
                        "Rentenbeginn-Jahr auf der Rentenbezugsmitteilung "
                        "nicht erkannt – Besteuerungsanteil wurde "
                        "vorsichtshalber mit 100 % angesetzt. Bitte "
                        "Rentenbeginn-Jahr im Beleg prüfen/nachtragen.")

    # ---------- 2) Sonstige Einkünfte (Krypto § 23 + § 22 Nr. 3)
    krypto_23 = sum(a.get("steuerpflichtiger_betrag", 0)
                    for a in crypto["pro_person"].values())
    krypto_rewards = sum(a.get("rewards_steuerpflichtig", 0)
                         for a in crypto["pro_person"].values())
    if not crypto["pro_person"]:
        # Kein FIFO-Engine-Ergebnis vorhanden (Krypto-Tab nicht genutzt) –
        # Fallback auf hochgeladene krypto_report-Dokumente, sonst würde
        # dieser Gewinn in der Schätzung fehlen (steht aber in build_summary!).
        krypto_docs = [d for d in docs if d.get("kategorie") == "krypto_report"]
        krypto_23 = sum(_ed(d, "gewinn_steuerpflichtig", d.get("betrag_eur"))
                        for d in krypto_docs)
        krypto_rewards = 0.0
        if krypto_23:
            b["warnhinweise"].append(
                "Krypto-Report-Dokument(e) ohne Nutzung des Krypto-Tabs "
                "(FIFO-Engine) erkannt – Gewinn wurde als grobe Schätzung "
                "aus dem Beleg übernommen. Für eine genaue, walletbezogene "
                "FIFO-Berechnung den Krypto-Tab nutzen.")
    if krypto_23:
        step("+ Steuerpflichtiger Krypto-Gewinn § 23 (vor Verlustvortrag)",
             krypto_23)
    # Verlustvortrag § 23 EStG: NUR mit § 23-Gewinnen verrechenbar, NICHT
    # mit § 22 Nr. 3 (Rewards/Staking) – unterschiedliche Einkunftsarten.
    verlustvortrag_23 = _num(interview.get("verlustvortrag_23"))
    vortrag_verrechnet = min(verlustvortrag_23, krypto_23) if krypto_23 > 0 else 0.0
    if vortrag_verrechnet:
        step("− Verlustvortrag § 23 aus Vorjahren verrechnet",
             -vortrag_verrechnet)
        rest = round(verlustvortrag_23 - vortrag_verrechnet, 2)
        if rest:
            b["warnhinweise"].append(
                f"Verlustvortrag § 23: {rest:.2f} € bleiben nach "
                "Verrechnung für Folgejahre vortragsfähig (Feststellungs-"
                "bescheid beachten).")
    krypto_23_netto = max(0.0, krypto_23 - verlustvortrag_23)
    if krypto_rewards:
        step("+ Steuerpflichtige Rewards/Staking (§ 22 Nr. 3)", krypto_rewards)
    krypto_stpfl = krypto_23_netto + krypto_rewards
    summe_einkuenfte += krypto_stpfl
    summe_einkuenfte_ohne_beihilfe += krypto_stpfl
    step("= Summe der Einkünfte", summe_einkuenfte)

    # ---------- 3) Vorsorgeaufwendungen (aus Lohnsteuerbescheinigungen)
    # § 10 Abs. 1 Nr. 2 EStG (Basisversorgung Alter, RV): eigener,
    # unabhängiger Höchstbetrag (Beitragsbemessungsgrenze) – seit 2023 zu
    # 100 % abzugsfähig, hier nicht extra gedeckelt (bei normalen
    # Arbeitnehmerbeiträgen ohnehin weit darunter).
    rv_summe = sum(_ed(d, "rv_arbeitnehmer") for d in lsb) + spar["vorsorge_basis"]
    kv_pv_summe = sum(_ed(d, "kv_beitraege") + _ed(d, "pv_beitraege")
                      for d in lsb)
    if rv_summe == 0 and kv_pv_summe == 0 and lsb:
        # Fallback: grobe Näherung, NUR wenn Lohnsteuerbescheinigungen
        # vorliegen, aber die SV-Zeilen darin nicht extrahiert wurden (nicht
        # wenn schlicht noch gar keine LSB hochgeladen ist – das deckt schon
        # der "fehlt LSB"-Fehler in checks.py ab, doppelte Warnung wäre
        # irreführend).
        brutto_ges = sum(_ed(d, "bruttoarbeitslohn", d.get("betrag_eur"))
                         for d in lsb)
        kv_pv_summe = round(brutto_ges * 0.19, 2)
        b["warnhinweise"].append(
            "SV-Beiträge (Zeilen 23–26) fehlten in den Bescheinigungen – "
            "Vorsorgeaufwand wurde mit ~19 % des Bruttos GESCHÄTZT (als "
            "Basis-KV/PV behandelt).")
    vorsorge_basis = rv_summe + kv_pv_summe
    basis_label = "− Vorsorgeaufwendungen Basis (RV + KV + PV" + \
        (" + Rürup/Basisrente" if spar["vorsorge_basis"] else "") + ")"
    step(basis_label, -vorsorge_basis)

    # § 10 Abs. 1 Nr. 3a + Abs. 4 EStG: "sonstige Vorsorgeaufwendungen"
    # (private Haftpflicht, Berufsunfähigkeit, Risikoleben u. Ä.) sind NUR
    # abzugsfähig, soweit der Höchstbetrag (1.900 €/Person bei Arbeit-
    # nehmern mit steuerfreiem KV/PV-Zuschuss, sonst 2.800 €) nicht schon
    # durch die Basis-KV/PV ausgeschöpft ist – DIESE bleiben unabhängig
    # vom Höchstbetrag immer voll abzugsfähig (Mindestvorsorgepauschale,
    # § 10 Abs. 4 Satz 4 EStG, BVerfG-Vorgabe zum steuerfreien Existenz-
    # minimum der Krankenversicherung).
    sonstige_belege = sum(_num(d.get("betrag_eur")) for d in docs
                          if d.get("kategorie") == "vorsorge_versicherung")
    hoechstbetrag = cfg.get("vorsorge_hoechstbetrag_arbeitnehmer", 1900.0) \
        * len(aktive)
    sonstige_effektiv = min(sonstige_belege, max(0.0, hoechstbetrag - kv_pv_summe))
    if sonstige_effektiv:
        step("− davon zusätzlich wirksame sonstige Vorsorgeaufwendungen "
             "(§ 10 Abs. 4 Höchstbetrag)", -sonstige_effektiv)
    if sonstige_belege and sonstige_effektiv < sonstige_belege:
        b["warnhinweise"].append(
            f"Sonstige Vorsorgeaufwendungen (Haftpflicht/BU u. Ä., "
            f"{sonstige_belege:.2f} €) wirken sich nur mit "
            f"{sonstige_effektiv:.2f} € aus – der Höchstbetrag "
            f"({hoechstbetrag:.0f} € für {len(aktive)} Person(en)) ist "
            "durch Kranken-/Pflegeversicherung bereits ausgeschöpft "
            "(§ 10 Abs. 4 EStG). Das ist bei Angestellten mit "
            "gesetzlicher KV der Normalfall – trotzdem eintragen, schadet "
            "nie (z. B. bei niedrigeren KV-Beiträgen wirkt es doch).")
    vorsorge = vorsorge_basis + sonstige_effektiv

    # ---------- 4) Sonderausgaben
    # Bewusst NICHT nach inhaber gefiltert: Sonderausgaben, agB und KAP-
    # Erträge werden bei Zusammenveranlagung als GEMEINSAMER Topf der
    # Ehegatten veranlagt (eine gemeinsame Steuernummer/Erklärung) – anders
    # als Anlage N/SO, die PRO PERSON eigene Pausch-/Freibeträge haben.
    spenden_belege = sum(_num(d.get("betrag_eur")) for d in docs
                         if d.get("kategorie") == "spende")
    kist_gezahlt = sum(_ed(d, "kirchensteuer") for d in lsb) + \
        sum(_ed(d, "kirchensteuer") for d in uebergangsbeihilfe_docs)
    sa = max(cfg["sonderausgaben_pauschbetrag"] * len(aktive),
             spenden_belege + spar["sa"] + kist_gezahlt)
    step("− Sonderausgaben (Spenden, Kirchensteuer, Betreuung …)", -sa)

    # ---------- 5) Außergewöhnliche Belastungen (über zumutbarer Grenze)
    agb_belege = sum(_num(d.get("betrag_eur")) for d in docs
                     if d.get("kategorie") == "krankheitskosten")
    agb = agb_belege + spar["agb"]
    kinderzahl = int(_num(interview.get("kinder_anzahl")))
    zumutbar = _zumutbare_belastung(summe_einkuenfte, zusammen, kinderzahl, cfg)
    agb_wirksam = max(0.0, agb - zumutbar)
    if agb > 0:
        step(f"− Außergew. Belastungen über zumutbarer Grenze "
             f"(~{zumutbar:,.0f} €, § 33 Abs. 3 EStG)".replace(",", "."),
             -agb_wirksam)

    # ---------- 5b) Behinderten-/Pflege-Pauschbetrag, § 33a-Unterhalt
    # (§ 33b, § 33a EStG) – anders als Krankheitskosten OHNE Kürzung um
    # die zumutbare Belastung, deshalb ein eigener, ungekürzter Abzug.
    pauschbetraege_agb, pauschbetraege_hinweise = \
        _behinderten_pflege_unterhalt(interview, cfg)
    if pauschbetraege_agb:
        step("− Behinderten-/Pflege-Pauschbetrag, § 33a-Unterhalt "
             "(ohne zumutbare Belastung)", -pauschbetraege_agb)
        b["warnhinweise"].extend(pauschbetraege_hinweise)

    zve = max(0.0, summe_einkuenfte - vorsorge - sa - agb_wirksam
              - pauschbetraege_agb)
    step("= zu versteuerndes Einkommen (zvE)", zve)
    # agb_wirksam hängt (über "zumutbar") minimal von summe_einkuenfte ab –
    # für die Fünftelregelung-Vergleichsgröße vernachlässigbar genau genug,
    # ohne Beihilfe im zvE nachgebildet:
    zve_ohne_beihilfe = max(
        0.0, summe_einkuenfte_ohne_beihilfe - vorsorge - sa - agb_wirksam
        - pauschbetraege_agb)

    # ---------- 6) Tarifliche ESt (Splitting), ggf. mit Fünftelregelung
    # (§ 34 EStG) auf die Übergangsbeihilfe – das Finanzamt wendet die
    # günstigere Variante ohnehin von Amts wegen an.
    est_normal = _tarif(zve, zusammen, cfg)
    est = est_normal
    if beihilfe_gesamt > 0:
        fuenftel = fuenftelregelung(zve_ohne_beihilfe, beihilfe_gesamt,
                                    cfg, zusammen)
        if fuenftel["guenstiger"] == "fuenftel":
            est = fuenftel["est_fuenftel"]
            step(f"Tarifliche Einkommensteuer "
                 f"({'Splitting' if zusammen else 'Grundtarif'}, "
                 "Fünftelregelung § 34 EStG angewendet)", est)
            b["warnhinweise"].append(
                f"Fünftelregelung auf die Übergangsbeihilfe angewendet – "
                f"spart ca. {fuenftel['ersparnis']:.2f} € ggü. voller "
                "Besteuerung. Voraussetzung: Die Zahlung muss eine "
                "'Vergütung für mehrjährige Tätigkeit' sein (§ 34 Abs. 2 "
                "Nr. 4 EStG, bei einer regulären Bundeswehr-"
                "Übergangsbeihilfe i. d. R. der Fall). Das Finanzamt prüft "
                "und wendet die günstigere Variante ohnehin automatisch an "
                "– bei Unsicherheit Steuerberater/Lohnsteuerhilfeverein "
                "fragen.")
        else:
            step(f"Tarifliche Einkommensteuer "
                 f"({'Splitting' if zusammen else 'Grundtarif'})", est)
    else:
        step(f"Tarifliche Einkommensteuer "
             f"({'Splitting' if zusammen else 'Grundtarif'})", est)

    # ---------- 6b) Riester-Günstigerprüfung (§ 10a EStG): Das Finanzamt
    # vergleicht automatisch die Steuerersparnis durch den vollen
    # Sonderausgabenabzug mit der bereits gutgeschriebenen Zulage – nur
    # der ÜBERSTEIGENDE Betrag wird zusätzlich per Bescheid erstattet,
    # sonst bleibt es bei der Zulage (kein Bescheid-Effekt). Vereinfachte
    # Grenzbetrachtung auf Basis des Grundtarifs (bei gleichzeitiger
    # Fünftelregelung eine leichte Näherung).
    riester_beitrag = sum(_num(interview.get(f"riester_beitrag_{p}"))
                          for p in aktive)
    if riester_beitrag > 0:
        abzugsbetrag = min(riester_beitrag,
                           cfg["riester_max_beitrag"] * len(aktive))
        kinder_ab_2008 = int(_num(interview.get("riester_kinder_ab_2008")))
        kinder_vor_2008 = int(_num(interview.get("riester_kinder_vor_2008")))
        grundzulage = cfg["riester_grundzulage"] * sum(
            1 for p in aktive if _num(interview.get(f"riester_beitrag_{p}")) > 0)
        kinderzulage = (kinder_ab_2008 * cfg["riester_kinderzulage_ab_2008"]
                        + kinder_vor_2008 * cfg["riester_kinderzulage_vor_2008"])
        zulage = grundzulage + kinderzulage
        ersparnis = round(
            est - _tarif(max(0.0, zve - abzugsbetrag), zusammen, cfg), 2)
        zusatzvorteil = max(0.0, round(ersparnis - zulage, 2))
        if zusatzvorteil:
            est -= zusatzvorteil
            step("− Riester-Günstigerprüfung: Steuerersparnis über die "
                 "Zulage hinaus (§ 10a EStG)", -zusatzvorteil)
            b["warnhinweise"].append(
                f"Riester lohnt sich über die Zulage hinaus: "
                f"Sonderausgabenabzug spart ca. {ersparnis:.2f} € "
                f"Steuern, die Zulage ({zulage:.2f} €) allein wäre "
                f"weniger wert – die Differenz kommt zusätzlich per "
                "Steuerbescheid (Anlage AV).")
        else:
            b["warnhinweise"].append(
                f"Riester: Die Zulage ({zulage:.2f} €) ist mindestens so "
                f"hoch wie die Steuerersparnis durch den Sonderausgaben-"
                f"abzug (ca. {ersparnis:.2f} €) – das Finanzamt gewährt "
                "dann nur die Zulage, kein zusätzlicher Bescheid-Effekt "
                "(Günstigerprüfung § 10a Abs. 2 EStG). Trotzdem lohnt "
                "sich Riester meist – die Zulage bleibt in jedem Fall.")

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
    lst_gezahlt = sum(_ed(d, "lohnsteuer") for d in lsb) + \
        sum(_ed(d, "lohnsteuer") for d in uebergangsbeihilfe_docs)
    soli_gezahlt = sum(_ed(d, "soli") for d in lsb) + \
        sum(_ed(d, "soli") for d in uebergangsbeihilfe_docs)
    step("Bereits gezahlte Lohnsteuer", lst_gezahlt)

    # ---------- 10) KAP-Erstattungspotenzial (Sparer-Pauschbetrag)
    kap_docs = [d for d in docs
                if d.get("kategorie") == "steuerbescheinigung_bank"]
    ertraege_brutto = sum(_ed(d, "kapitalertraege_zeile7", d.get("betrag_eur"))
                          for d in kap_docs)
    # Verlustvortrag KAP (Aktien + sonstige): vereinfachend gegen die
    # blendete Kapitalertrags-Summe verrechnet. Real gibt es getrennte
    # Verlusttöpfe (Aktien-Verlusttopf nur mit Aktiengewinnen verrechenbar,
    # § 20 Abs. 6 S. 4 EStG) – ohne Aufschlüsselung Aktien/sonstige in den
    # Bank-Bescheinigungen ist die feinere Trennung hier nicht abbildbar.
    verlustvortrag_kap = (_num(interview.get("verlustvortrag_kap_aktien"))
                          + _num(interview.get("verlustvortrag_kap_sonstige")))
    ertraege = max(0.0, ertraege_brutto - verlustvortrag_kap)
    if verlustvortrag_kap and ertraege_brutto:
        b["warnhinweise"].append(
            "Verlustvortrag KAP wurde vereinfacht gegen die gesamten "
            "Kapitalerträge verrechnet (ohne Trennung Aktien-Verlusttopf "
            "vs. sonstige Verluste) – bei größeren Beträgen mit dem "
            "Steuerbescheid abgleichen.")
    fsa = sum(_ed(d, "in_anspruch_genommener_freistellungsauftrag")
              for d in kap_docs)
    pb_kap = cfg["sparer_pauschbetrag"] * len(aktive)
    kap_erstattung = round(
        max(0.0, min(ertraege, pb_kap) - fsa) * 0.25 * 1.055, 2)
    if kap_erstattung:
        step("+ Rückholbare Abgeltungsteuer (ungenutzter "
             "Sparer-Pauschbetrag)", kap_erstattung)

    # ---------- 10b) Günstigerprüfung KAP (§ 32d Abs. 6 EStG)
    # Vergleich: pauschale Abgeltungsteuer (25 % + Soli) vs. Grundtarif/
    # Splitting auf das steuerpflichtige zvE + KAP-Erträge (Grenzbetrachtung,
    # analog steuer_auf_krypto()). Lohnt sich nur bei niedrigem persönlichen
    # Steuersatz (typischerweise < 25 %) – das Finanzamt prüft das mit
    # angekreuzter Zeile 4 der Anlage KAP ohnehin automatisch und wendet
    # die günstigere Variante an.
    kap_stpfl_bemessung = max(0.0, ertraege - pb_kap)
    if interview.get("guenstigerpruefung", True) and kap_stpfl_bemessung > 0:
        est_ohne_kap = _tarif(zve, zusammen, cfg)
        est_mit_kap = _tarif(zve + kap_stpfl_bemessung, zusammen, cfg)
        mehrsteuer_grundtarif = round(est_mit_kap - est_ohne_kap, 2)
        abgeltung_betrag = round(kap_stpfl_bemessung * 0.25 * 1.055, 2)
        if mehrsteuer_grundtarif < abgeltung_betrag:
            guenstiger_vorteil = round(abgeltung_betrag - mehrsteuer_grundtarif, 2)
            step("+ Günstigerprüfung KAP (persönlicher Steuersatz < 25 %)",
                 guenstiger_vorteil)
            kap_erstattung += guenstiger_vorteil
            b["warnhinweise"].append(
                f"Günstigerprüfung lohnt sich: Dein persönlicher Grenz-"
                f"steuersatz auf die KAP-Erträge läge bei etwa "
                f"{round(mehrsteuer_grundtarif / kap_stpfl_bemessung * 100, 1)} % "
                "statt der pauschalen ~26,4 % Abgeltungsteuer – in Anlage "
                "KAP Zeile 4 ankreuzen! Grobe Schätzung ohne Kirchensteuer-"
                "Effekt auf die Abgeltungsteuer.")

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
