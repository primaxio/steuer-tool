"""
Plausibilitätsprüfungen und Fehlererkennung.
Liefert Findings mit Level: "fehler" | "warnung" | "hinweis" | "frage".
"""


def _num(value, default=0.0):
    try:
        if value is None:
            return default
        if isinstance(value, str):
            value = value.replace(".", "").replace(",", ".").replace("€", "").strip()
        return float(value)
    except (ValueError, TypeError):
        return default


def _docs_by_cat(docs, *cats):
    return [d for d in docs if d.get("kategorie") in cats]


def run_checks(docs: list, cfg: dict, interview: dict) -> list:
    """Alle Prüfungen ausführen. `interview` = Antworten aus dem Fragebogen."""
    from datetime import date
    findings = []
    add = lambda level, text: findings.append({"level": level, "text": text})
    jahr = cfg["jahr"]

    # ---------- Abgabefrist ----------
    frist_str = cfg.get("abgabefrist_datum")
    if frist_str:
        frist = date.fromisoformat(frist_str)
        rest = (frist - date.today()).days
        if rest < 0:
            add("fehler",
                f"⏰ Die Abgabefrist ({frist:%d.%m.%Y}) ist um {-rest} Tage "
                "ÜBERSCHRITTEN! Bei Pflichtveranlagung (Steuerklasse VI) "
                "droht ein Verspätungszuschlag (0,25 % der Steuer, mind. "
                "25 € PRO MONAT). Jetzt schnellstmöglich abgeben – oder ein "
                "Steuerberater/Lohnsteuerhilfeverein verlängert die Frist.")
        elif rest <= 45:
            add("warnung",
                f"⏰ Nur noch {rest} Tage bis zur Abgabefrist am "
                f"{frist:%d.%m.%Y}! Da ihr abgeben MÜSST (Steuerklasse VI), "
                "jetzt priorisieren – fehlende Belege können notfalls per "
                "berichtigter Erklärung nachgereicht werden.")

    # ---------- Konfiguration ----------
    if not cfg.get("_geprueft", True):
        add("warnung",
            f"Für {jahr} sind noch keine geprüften Pauschbeträge hinterlegt – "
            f"es werden die Werte von {cfg.get('_basisjahr')} verwendet. "
            "Bitte in core/tax_config.py aktualisieren.")

    # ---------- Vollständigkeit Lohnsteuerbescheinigungen ----------
    lsb_zivil = _docs_by_cat(docs, "lohnsteuerbescheinigung_zivil")
    lsb_bw = _docs_by_cat(docs, "lohnsteuerbescheinigung_bundeswehr")

    if not lsb_zivil:
        add("fehler",
            "Es fehlt die Lohnsteuerbescheinigung des zivilen Arbeitgebers "
            "(Anlage N, Arbeitgeber 1).")
    if not lsb_bw and interview.get("hat_bundeswehr", True):
        add("fehler",
            "Es fehlt die Bescheinigung über die Übergangsgebührnisse der "
            "Bundeswehr (BVA). Diese sind voll steuerpflichtiger Arbeitslohn "
            "und müssen als zweites Arbeitsverhältnis in Anlage N erfasst werden.")
    from collections import Counter
    zivil_je_person = Counter(d.get("inhaber", "P1") for d in lsb_zivil)
    bw_je_person = Counter(d.get("inhaber", "P1") for d in lsb_bw)
    if any(c > 1 for c in zivil_je_person.values()) or \
            any(c > 1 for c in bw_je_person.values()):
        add("warnung",
            "Mehrere Lohnsteuerbescheinigungen derselben Kategorie für "
            "DIESELBE Person erkannt – Duplikat oder Arbeitgeberwechsel? "
            "Bitte prüfen (und Inhaber-Zuordnung in Tab 1 kontrollieren).")

    # Steuerklasse VI → Pflichtveranlagung
    for d in lsb_zivil + lsb_bw:
        stkl = str(d.get("extrahierte_daten", {}).get("steuerklasse", ""))
        if "6" in stkl or "VI" in stkl.upper():
            add("hinweis",
                f"Steuerklasse VI erkannt ({d['dateiname']}): Bei zwei "
                "Arbeitsverhältnissen besteht Pflicht zur Abgabe der "
                "Steuererklärung. Häufig ergibt sich hier eine Nachzahlung – "
                "ggf. Vorauszahlungen einplanen.")
            break

    # ---------- Steuerjahr-Abgleich ----------
    for d in docs:
        doc_jahr = d.get("steuerjahr")
        if doc_jahr and int(doc_jahr) != jahr:
            add("fehler",
                f"'{d['dateiname']}' gehört zum Steuerjahr {doc_jahr}, die "
                f"Erklärung ist aber für {jahr}. Beleg entfernen oder Jahr wechseln.")

    # ---------- Duplikate ----------
    seen = {}
    for d in docs:
        key = (d.get("kategorie"), _num(d.get("betrag_eur")), d.get("datum"),
               (d.get("aussteller") or "").lower())
        if key in seen and key[1] > 0:
            add("warnung",
                f"Möglicher doppelter Beleg: '{d['dateiname']}' und "
                f"'{seen[key]}' (gleicher Betrag, Datum und Aussteller).")
        else:
            seen[key] = d["dateiname"]

    # ---------- Unsichere Klassifizierungen ----------
    for d in docs:
        if _num(d.get("confidence"), 1.0) < 0.7:
            add("frage",
                f"'{d['dateiname']}' wurde nur unsicher als "
                f"'{d.get('dokumenttyp', '?')}' erkannt – bitte Kategorie "
                "manuell bestätigen oder korrigieren.")

    # ---------- Kapitalerträge (KAP) ----------
    zusammen = bool(interview.get("zusammenveranlagung"))
    kap_docs = _docs_by_cat(docs, "steuerbescheinigung_bank")
    if kap_docs:
        fsa = sum(_num(d["extrahierte_daten"].get(
            "in_anspruch_genommener_freistellungsauftrag")) for d in kap_docs)
        ertraege = sum(_num(d["extrahierte_daten"].get(
            "kapitalertraege_zeile7", d.get("betrag_eur"))) for d in kap_docs)
        pb = cfg["sparer_pauschbetrag"] * (2 if zusammen else 1)
        if zusammen:
            add("hinweis",
                "Zusammenveranlagung: Gemeinsamer Sparer-Pauschbetrag "
                f"{pb:.0f} € – Freistellungsaufträge können zwischen euch "
                "frei verteilt werden (bei den Banken anpassen).")
        if ertraege > 0 and fsa < min(ertraege, pb):
            add("hinweis",
                f"Sparer-Pauschbetrag ({pb:.0f} €) wurde laut Bescheinigungen "
                f"nur mit {fsa:.2f} € ausgeschöpft. Über die Anlage KAP holst "
                "du dir zu viel gezahlte Kapitalertragsteuer zurück.")
        quellensteuer = sum(_num(d["extrahierte_daten"].get(
            "auslaendische_quellensteuer")) for d in kap_docs)
        if quellensteuer > 0:
            add("hinweis",
                f"Ausländische Quellensteuer ({quellensteuer:.2f} €) erkannt – "
                "in Anlage KAP anrechnen lassen.")
        add("frage",
            "Günstigerprüfung: Liegt dein persönlicher Grenzsteuersatz unter "
            "25 %? Dann in Anlage KAP Zeile 4 die Günstigerprüfung beantragen "
            "(prüft das Finanzamt kostenlos, kann nur Vorteile bringen).")

    # ---------- Krypto (Anlage SO) ----------
    crypto_engine = interview.get("_crypto")
    if crypto_engine:
        for p_key, a in crypto_engine["pro_person"].items():
            if a.get("netto_gewinn", 0) < 0:
                add("hinweis",
                    f"Krypto-Verlust ({-a.get('netto_gewinn', 0):.2f} €, {p_key}): "
                    "In Anlage SO eintragen – nur mit § 23-Gewinnen "
                    "verrechenbar (Rück-/Vortrag möglich), nicht mit "
                    "Lohn oder Kapitalerträgen.")
        for w in crypto_engine.get("warnungen", []):
            add("warnung", f"Krypto-Import: {w}")
    krypto = _docs_by_cat(docs, "krypto_report")
    if krypto and not crypto_engine:
        gewinn = sum(_num(d["extrahierte_daten"].get(
            "gewinn_steuerpflichtig", d.get("betrag_eur"))) for d in krypto)
        freigrenze = cfg["freigrenze_private_veraeusserung"]
        if 0 < gewinn < freigrenze:
            add("hinweis",
                f"Krypto-Gewinn ({gewinn:.2f} €) liegt unter der Freigrenze von "
                f"{freigrenze:.0f} € – damit komplett steuerfrei. Achtung: Es "
                "ist eine FREIGRENZE, kein Freibetrag – ab "
                f"{freigrenze:.0f},01 € wäre alles steuerpflichtig.")
        elif gewinn >= freigrenze:
            add("warnung",
                f"Krypto-Gewinn ({gewinn:.2f} €) über der Freigrenze – der "
                "GESAMTE Gewinn ist mit deinem persönlichen Steuersatz zu "
                "versteuern (Anlage SO).")
        add("frage",
            "Krypto: Sind im Report alle Wallets/Börsen enthalten und wurde "
            "die FIFO-Methode verwendet? Verkäufe nach > 1 Jahr Haltefrist "
            "sind steuerfrei und gehören nicht in die Anlage SO. Tipp: Nutze "
            "den Krypto-Tab für die automatische FIFO-Berechnung.")
    elif interview.get("hat_krypto_verkauft") and not crypto_engine:
        add("fehler",
            "Du hast angegeben, Krypto verkauft zu haben, aber es liegt kein "
            "Krypto-Report vor. Bei Haltefrist < 1 Jahr müssen die Gewinne in "
            "die Anlage SO – bitte Report (z. B. Blockpit/CoinTracking) hochladen.")

    # ---------- § 35a ----------
    for d in _docs_by_cat(docs, "handwerker_haushaltsnah"):
        daten = d.get("extrahierte_daten", {})
        zahlungsart = str(daten.get("zahlungsart", "")).lower()
        if "bar" in zahlungsart:
            add("fehler",
                f"'{d['dateiname']}': Barzahlung erkannt – bei § 35a werden "
                "nur unbare Zahlungen (Überweisung) anerkannt!")
        if not _num(daten.get("arbeitskosten")):
            add("frage",
                f"'{d['dateiname']}': Arbeitskosten sind nicht separat "
                "ausgewiesen. Nur Arbeits-/Fahrtkosten (nicht Material) sind "
                "begünstigt – ggf. korrigierte Rechnung anfordern.")

    # ---------- Werbungskosten vs. Pauschbetrag (PRO PERSON) ----------
    namen = interview.get("personen", {"P1": "Person 1", "P2": "Person 2"})
    aktive_personen = ["P1", "P2"] if zusammen else ["P1"]
    pb = cfg["arbeitnehmer_pauschbetrag"]
    for p_key in aktive_personen:
        wk_summe = sum(_num(d.get("betrag_eur"))
                       for d in _docs_by_cat(docs, "werbungskosten")
                       if d.get("inhaber", "P1") == p_key)
        tage = int(_num(interview.get(f"arbeitstage_{p_key}")))
        ho_tage = int(_num(interview.get(f"homeoffice_tage_{p_key}")))
        ep = entfernungspauschale(
            _num(interview.get(f"entfernung_km_{p_key}")), tage, cfg)
        ho = min(ho_tage * cfg["homeoffice_pauschale_pro_tag"],
                 cfg["homeoffice_max"])
        wk_gesamt = wk_summe + ep + ho
        if 0 < wk_gesamt <= pb:
            add("hinweis",
                f"{namen[p_key]}: Werbungskosten ({wk_gesamt:.2f} €) liegen "
                f"unter dem Pauschbetrag ({pb:.0f} €), der automatisch "
                "abgezogen wird – jeder Ehegatte hat einen EIGENEN "
                "Pauschbetrag. Prüfe fehlende Posten (Arbeitsmittel, "
                "Fortbildung, Kontoführung 16 €, Homeoffice).")
        if tage + ho_tage > 366:
            add("fehler",
                f"{namen[p_key]}: Arbeitstage + Homeoffice-Tage > 366 – pro "
                "Tag gibt es Entfernungspauschale ODER Homeoffice-Pauschale, "
                "nicht beides.")

    # ---------- Verlustvorträge & Verlustbescheinigung ----------
    if _num(interview.get("verlustvortrag_23")) > 0:
        add("hinweis",
            f"Verlustvortrag § 23 aus Vorjahren "
            f"({_num(interview.get('verlustvortrag_23')):.2f} €): wird mit "
            "diesjährigen Krypto-/§ 23-Gewinnen verrechnet – in Anlage SO "
            "angeben (Feststellungsbescheid beilegen).")
    banken = {(d.get("aussteller") or "").lower()
              for d in _docs_by_cat(docs, "steuerbescheinigung_bank")}
    verluste_kap = any(
        _num(d["extrahierte_daten"].get("verlust_aktien")) > 0 or
        _num(d["extrahierte_daten"].get("verlust_sonstige")) > 0
        for d in _docs_by_cat(docs, "steuerbescheinigung_bank"))
    if len(banken) > 1 and verluste_kap:
        add("warnung",
            "Verluste bei mehreren Banken erkannt: Bankübergreifende "
            "Verrechnung geht NUR mit Verlustbescheinigung – Antrag bei der "
            "Bank bis spätestens 15.12. des Steuerjahres! Ohne Bescheinigung "
            "bleibt der Verlusttopf bei der Bank stehen.")

    # ---------- Kinder / ETF / Auslandsbezug ----------
    if interview.get("hat_kinder"):
        kb = cfg.get("kinderbetreuung", {})
        add("hinweis",
            "Kinder: Anlage Kind je Kind ausfüllen (Kindergeld vs. "
            "Freibeträge prüft das Finanzamt automatisch). "
            f"Kinderbetreuungskosten sind zu {kb.get('anteil_prozent', 80)} % "
            f"bis max. {kb.get('max', 4800):.0f} €/Kind als Sonderausgaben "
            "abziehbar (Rechnung + Überweisung nötig).")
    elif "hat_kinder" not in interview:
        add("frage", "Habt ihr Kinder? Dann gehört je Kind eine Anlage Kind "
                     "dazu (Kindergeld, Betreuungskosten, Schulgeld).")
    if interview.get("hat_etf"):
        add("hinweis",
            "ETFs im Depot: Die Vorabpauschale wird von der Bank automatisch "
            "abgeführt und steht in der Steuerbescheinigung – beim Verkauf "
            "mindert sie den Gewinn. Teilfreistellung (Aktien-ETF 30 %) "
            "berücksichtigt die Bank ebenfalls.")
    if interview.get("auslandsbezug"):
        add("warnung",
            "Auslandsbezug (Wohnsitz/Einkünfte z. B. in Österreich): "
            "Ansässigkeit nach DBA klären – sie bestimmt, welcher Staat was "
            "besteuert (Progressionsvorbehalt!). Hier unbedingt einen "
            "Steuerberater mit DBA-Erfahrung hinzuziehen; das Tool deckt nur "
            "die unbeschränkte Steuerpflicht in Deutschland ab.")

    # ---------- Interview-Basisfragen ----------
    if not interview.get("entfernung_km_P1"):
        add("frage",
            "Wie viele Kilometer beträgt die einfache Entfernung zwischen "
            "Wohnung (Bonn) und erster Tätigkeitsstätte? (Fragebogen, für "
            "die Entfernungspauschale – bei Zusammenveranlagung je Person.)")
    if interview.get("zusammenveranlagung"):
        add("hinweis",
            "Zusammenveranlagung: Eine gemeinsame Erklärung unter der "
            "gemeinsamen Steuernummer, aber getrennte Anlagen N/SO je "
            "Ehegatte. Die § 23-Freigrenze (Krypto) gilt PRO PERSON für "
            "eigene Gewinne und ist nicht übertragbar – Depots daher im "
            "Krypto-Tab dem richtigen Inhaber zuordnen.")
    st_daten = interview.get("stammdaten", {})
    fehlend = [f for f, lbl in [("steuernummer", "gemeinsame Steuernummer"),
                                ("steuer_id_P1", "Steuer-ID Person 1"),
                                ("iban", "IBAN für Erstattung")]
               if not st_daten.get(f)]
    if zusammen and not st_daten.get("steuer_id_P2"):
        fehlend.append("Steuer-ID Person 2")
    if fehlend:
        add("frage", "Stammdaten unvollständig: " + ", ".join(fehlend) +
            " (Fragebogen-Tab oben ausfüllen – ohne sie ist die "
            "ELSTER-Übertragung unvollständig).")
    if not interview.get("kirchensteuerpflichtig_beantwortet"):
        add("frage", "Bist du kirchensteuerpflichtig? (Relevant für KAP und "
                     "Sonderausgabenabzug der Kirchensteuer.)")

    return findings


def entfernungspauschale(km: float, tage: int, cfg: dict) -> float:
    """Entfernungspauschale mit gestaffeltem Satz ab dem 21. Kilometer."""
    if km <= 0 or tage <= 0:
        return 0.0
    if km <= 20:
        return round(km * tage * cfg["entfernungspauschale_bis_20km"], 2)
    return round(
        tage * (20 * cfg["entfernungspauschale_bis_20km"]
                + (km - 20) * cfg["entfernungspauschale_ab_21km"]), 2)
