# CLAUDE.md – Steuer-Assistent (Bonn, NRW)

## Projekt
Streamlit-Tool zur Vorbereitung der privaten Einkommensteuererklärung.
Belege (PDF/Foto) werden per Anthropic Vision API klassifiziert und
extrahiert, Plausibilitätsprüfungen laufen automatisch, Output ist eine
ELSTER-Eingabehilfe (Markdown + JSON). KEINE direkte Übermittlung ans
Finanzamt (ERiC-Zertifizierung nötig) – bewusste Design-Entscheidung.

## Nutzerprofil (fest einprogrammiert, nicht ändern ohne Rückfrage)
- Zwei Arbeitsverhältnisse, beide Anlage N:
  1. Ziviler Arbeitgeber
  2. Übergangsgebührnisse Bundeswehr (BVA, ehem. SaZ, oft Steuerklasse VI
     → Pflichtveranlagung)
- Aktien/Dividenden → Anlage KAP
- Krypto → Anlage SO (§ 23 EStG: Haltefrist 1 Jahr, Freigrenze 1.000 €,
  NIEMALS als KAP behandeln)

## Krypto-Modul (Kernstück!)
- `core/crypto.py` – NormTx/Disposal/OpenLot, run_fifo() walletbezogen je
  (Inhaber, Depot, Asset), Jahresfrist über _jahrestag() (§ 187/188 BGB,
  29.02.→28.02.), aggregate() je Ehegatte (Freigrenze PRO PERSON),
  optimizer_hinweise(), § 32a-Tarif (est_nach_tarif, Splitting via
  2×Tarif(zvE/2)), steuer_auf_krypto() = Grenzbetrachtung.
- `core/crypto_parsers.py` – parse_coinbase (Convert → verkauf+kauf via
  Notes-Regex), parse_etoro (Closed Positions, Leverage>1/Short = CFD →
  KAP-Hinweis, KEINE Übernahme in SO), parse_generic + Claude-Mapping
  (claude_suggest_mapping), FxTable = EZB eurofxref-hist.csv mit
  Wochenend-Fallback. WICHTIG: Spalten-Lookup nutzt exakten Treffer,
  sonst KÜRZESTEN Match (Substring-Kollision "fees…" vs "total(…fees…)").
- `core/crypto_ui.py` – Tab-Rendering; Ergebnis landet in
  interview["_crypto"] (serialize()) → checks.py + elster_export.py
  lesen daraus.
- Ehe: sidebar-Radio setzt interview["zusammenveranlagung"]; Personen
  P1/P2 mit Namen. Jeder Ehegatte eigene Anlage SO + eigene Freigrenze.

## Ausbaustufe 3 (Vollständigkeit)
- `core/persist.py` – save_state()/load_state(): kompletter Projektstand
  als JSON (Sidebar-Buttons); Krypto-Dataclasses via asdict + ISO-Datum.
- Fragebogen PRO PERSON: interview-Keys mit Suffix _P1/_P2
  (entfernung_km_P1 usw.); Dokumente haben "inhaber" (Tab-1-Selectbox).
  Jeder Ehegatte: eigene Anlage N, eigener AN-Pauschbetrag.
- Stammdaten in interview["stammdaten"] (Steuernummer, Steuer-IDs, IBAN,
  Finanzamt, Religion) → ELSTER-Hilfe-Kopf + Vollständigkeits-Check.
- Verlustvorträge (§ 23, KAP Aktien/sonstige) als Fragebogen-Felder.
- Neue Checks: Verlustbescheinigung 15.12. (Verluste bei >1 Bank),
  Anlage Kind (Kinderbetreuung aus cfg["kinderbetreuung"], 2024: 2/3 max
  4.000 €, ab 2025: 80 % max 4.800 €), ETF-Vorabpauschale, Auslandsbezug
  (DBA-Warnung), LSB-Duplikate PRO PERSON gezählt (Counter).

## Erklär-Ebene (Zielgruppe: Steuer-Laie!)
- `core/erklaerungen.py` – GLOSSAR (~24 Begriffe), STEUER_101 (Einsteiger-
  Guide), KATEGORIE_ERKLAERUNG (je Dokumenttyp, MUSS synchron zu
  categories.py bleiben – Test prüft das), ANLAGEN_ERKLAERT (Export-Blöcke),
  frag_steuerberater() = Chat mit Nutzerdaten-Kontext (CHAT_SYSTEM).
- Sidebar-Toggle "Erklär-Modus" (default AN) steuert Kategorie-Captions in
  Tab 1 und die "Einfach erklärt"-Blöcke in render_elster_help(erklaeren=).
- Tab 5 "Verstehen & Fragen": Steuer-1×1, durchsuchbares Glossar,
  st.chat_input-Chat (Verlauf in session_state.chat_verlauf).
- Grundregel bei allen Erweiterungen: JEDE neue Zahl/Prüfung braucht eine
  Erklärung in Alltagssprache – der Nutzer versteht Steuern nicht.

## Ausbaustufe 4 (Maximierung + Ergebnis)
- `core/sparcheck.py` – ITEMS-Checkliste (~23 Posten, Buckets wk/sa/
  parteispenden/h35a_*/agb), render_sparcheck() = Tab 4, summen() liefert
  Topf-Summen; fließt in Rechner + ELSTER-Hilfe ("Zusätzliche Posten").
- `core/veranlagung.py` – berechne_veranlagung(): Brutto → WK (max mit
  Pauschbetrag) → +Krypto → −Vorsorge (LSB Z. 23–26, Fallback 19 % mit
  Warnung) → −SA (inkl. gezahlter KiSt!) → −agB über zumutbarer Grenze →
  zvE → Splitting-Tarif → −§35a/§34g → Soli (Freigrenze aus cfg) + KiSt
  9 % → Vergleich mit gezahlter LSt → ergebnis (+ = Erstattung). Alle
  Schritte in "schritte" für den aufklappbaren Rechenweg.
- Fristen: cfg["abgabefrist_datum"] (ISO) – 2024: 2025-07-31, 2025:
  2026-07-31; checks.py warnt <45 Tage, Fehler bei Überschreitung
  (Verspätungszuschlag-Hinweis). Tab 5 zeigt Countdown-Metric.
- Tab-Reihenfolge (Stand Ausbaustufe 6): Dokumente · Krypto · Betrieb ·
  Fragebogen · Spar-Check · Ergebnis&ELSTER · Verstehen.

## Einfacher Modus (geführter Wizard)
- `core/wizard.py` – render_wizard(): lineare 5-Schritte-Führung (Start ·
  Belege · Fragen · Ergebnis · Fertig) für Steuer-Laien, die sich in der
  Tab-Ansicht überfordert fühlen. Sidebar-Radio "Wie möchtest du arbeiten?"
  schaltet zwischen Einfach (Wizard) und Experte (alle 6 Tabs) um; im
  Einfach-Modus rendert app.py NUR den Wizard (st.stop() vor den Tabs).
  State: st.session_state.wizard_step (Index 0–4).
- Wizard nutzt dieselben Kernfunktionen wie die Tabs (run_checks,
  berechne_veranlagung, build_summary, render_crypto_tab) – KEINE eigene
  Business-Logik, nur reduzierte Feldauswahl (4 Ja/Nein-Fragen statt
  Stammdaten/Verlustvorträge/Fahrtkosten – diese bleiben im Experten-Modus).
  Krypto-Erfassung erscheint als eingebetteter Expander in Schritt "Fragen",
  wenn "Krypto verkauft?" mit Ja beantwortet wird (kein eigener Wizard-Schritt,
  damit die Schrittzahl konstant bleibt).
- `core/dokumente_ui.py` – render_dokumente_tab(): Beleg-Upload/-Analyse/
  -Korrektur aus dem alten Tab 1 extrahiert, damit Experten-Tab und
  Wizard-Schritt "Belege" dieselbe Logik nutzen (keine Duplikate).
  `core/jahr_zuordnung.docs_im_jahr()` ist der gemeinsame Jahres-Filter.
- Sidebar im Einfach-Modus reduziert: Jahr-Wahl/Pauschbeträge und
  Projektstand-Speichern/Laden sind in Expander eingeklappt (im
  Experten-Modus standardmäßig ausgeklappt).

## Belege-Eingang mit Jahres-Sortierung
- `core/jahr_zuordnung.py` – bestimme_steuerjahr(): Claude-Feld
  "steuerjahr" → Jahreszahlen im Datum (Zeitraum: Endjahr) → None
  (Rückfrage, Fallback aktives Jahr). Vision-Prompt erklärt das
  ABFLUSSPRINZIP (§ 11 EStG): Zahlungsjahr zählt, Dez/Jan-Belege →
  Rückfrage.
- app.py: doc["steuerjahr_zuordnung"] nach Analyse gesetzt;
  _docs_im_jahr() filtert für Prüfung/Rechner/ELSTER/Chat. Belege
  anderer Jahre bleiben gespeichert ("geparkt", Expander in Tab 1,
  Jahr je Beleg editierbar); Sidebar zeigt Zählung je Jahr.
  Jahreswechsel = Sidebar-Dropdown; Krypto filtert ohnehin je
  Verkaufsjahr in aggregate().

## Ausbaustufe 5 – "Blockpit-Style" (⚠️ LIVE UNGETESTET)
- `core/connectors/preise.py` – PreisDienst: CoinGecko-Tageskurse EUR,
  Datei-Cache preise_cache.json, Rate-Limit-Pause, SYMBOL_IDS erweiterbar.
- `core/connectors/coinbase_api.py` – CDP-JWT (ES256, iss=cdp,
  uri="GET api.coinbase.com/…"), v2 /accounts + /transactions paginiert,
  mappe_transaktion() → NormTx; bewerte_fehlende() zieht EUR-Werte nach.
  NUR-LESE-Key! Gegen Doku implementiert – ERSTER CLAUDE-CODE-TASK:
  Live-Test (Feldnamen "trade"/Convert-Legs, Gebührenbehandlung prüfen!).
- `core/connectors/base_chain.py` – Basescan txlist+tokentx, Bündelung je
  Tx-Hash: raus+rein = Swap (verkauf+kauf zum Marktwert, Gas als Gebühr),
  nur-rein = transfer_in mit Herkunfts-Rückfrage; DeFi-Mehrbein → Warnung.
- `core/report.py` – erstelle_report(): Querformat-PDF mit Methodik-Seite
  (BMF 06.03.2025, walletbezogene FIFO, §§ 187/188 BGB), Kennzahlen je
  Person, Einzelaufstellung, offene Lots, Warn-Anhang. "Anerkennung"
  = Dokumentationsqualität, kein Zertifikat – so dem Nutzer kommuniziert.
- crypto_ui: Expander "Automatischer Abruf per API" + Report-Button.
- Grenzen (ehrlich dokumentieren, nie verschweigen): kein eToro-API
  (existiert nicht für Retail), DeFi/LP/NFT nur Warnungen, CoinGecko-
  Tageskurse statt Intraday.

## Termingeschäfte & Broker-Zinsen (KAP)
- Eingabe im Krypto-Tab-Expander (je Person: termin_gewinne_/termin_
  verluste_/broker_zinsen_{P}); Quelle = offizielle Broker-Steuerberichte
  (eToro-Report, Phemex P/L). Fließt in ELSTER-Hilfe (KAP Z. 19/21/24,
  setdefault-Block auch ohne Bank-Doc) und veranlagung.py (Abgeltung-
  steuer 26,375 % auf max(0, Netto − Rest-Sparer-PB) als Nachzahlung).
- Engine-Validierung 07/2026: FIFO centgenau identisch mit offiziellem
  eToro-Steuerbericht 2024 (906,49 €, inkl. Same-Day-Lot-Split);
  Blockpit wich beim eToro-Import ab (BTC-AK) und ließ eToro-CFDs/
  Zinsen aus → Primärquellen bevorzugen.

## Automatik-Kategorien + EZB-Auto-Kurse
- Zwei "selbstbuchende" Dokumentkategorien (categories.py + vision.py-
  Prompt): "nebenkostenabrechnung" (Vision extrahiert begünstigte § 35a-
  Lohnanteile als summe_haushaltsnah/summe_handwerker – Grundsteuer/
  Wasser/Heizkosten etc. NICHT) und "broker_steuerbericht"
  (kap_zeile19_zinsen, kap_zeile21_termingewinne,
  kap_zeile24_terminverluste, so_krypto_gewinn, broker_name).
- Beide fließen AUTOMATISCH in veranlagung.py (NK-Summen in die 20 %-
  § 35a-Ermäßigung; Broker-Werte ADDITIV zu den manuellen tg/tv/bz-
  Interview-Feldern → Warnhinweis gegen Doppel-Eingabe) und in
  elster_export.build_summary (KAP-Block + § 35a-Block, Beleg-Label
  "NK-Abrechnung (automatisch)"). checks.py bestätigt je Doc per
  "hinweis" die übernommenen Summen bzw. den Kontrollwert-Abgleich.
- WICHTIG: broker so_krypto_gewinn ist NUR Kontrollwert gegen die
  FIFO-Engine – er geht NIE in die Rechnung ein (sonst Doppelerfassung
  mit Anlage SO aus dem Krypto-Tab).
- render_elster_help füllt fehlende SO-Keys defensiv mit Defaults auf
  (Kontrollwert ohne vollständige Krypto-Daten darf keinen KeyError
  werfen).
- FxTable.from_ecb_online (crypto_parsers.py): lädt eurofxref-hist.zip
  von der EZB, 24h-Datei-Cache /tmp/ezb_kurse.csv; crypto_ui lädt beim
  ersten Tab-Aufruf automatisch (ss["_fx"]), bei Fehlschlag Fallback:
  manueller CSV-Upload + Notfall-Kurs-Eingabe (1,08).

## Coinbase-Realdaten-Erkenntnisse (07/2026, WICHTIG)
- run_fifo: (1) Sortierung tagesweise – Zugänge vor Abgängen (Settlement-
  Timing in Exporten!), (2) transfer_out bucht Lots STEUERNEUTRAL aus
  (FIFO, mit Kostenbasis – vorher blieben ausgezahlte Coins fälschlich
  im Topf), (3) Null-Mengen-Lots werden übersprungen.
- parse_coinbase: Marktwert-Fallback via "Price at Transaction"×Menge;
  interne Transfers (Staking/Unstaking/Eth2 Deprecation) werden
  ignoriert, ETH2→ETH normalisieren, Fiat-EUR-Zeilen ausfiltern,
  Rebates/Price Improvements → transfer_in (steuerneutraler Zufluss).
- Coinbase-Exporte können Einzahlungen AUSLASSEN (hier: 9.600 USDT von
  Phemex fehlten!) → "Verkauf ohne Bestand"-Warnungen ernst nehmen und
  fehlende Zugänge manuell zum Marktwert nachbuchen.
- Für exakte Ergebnisse EZB-TAGESkurse laden (eurofxref-hist.csv);
  Monatsdurchschnitte erzeugen wenige % Abweichung.

## Code- und Steuer-Audit-Prozess
- `AUDIT.md` – lebendes Dokument (nicht nur einmalig): technischer +
  steuerfachlicher Review, priorisiert kritisch/mittel/gering. Kritische
  Funde werden direkt behoben (mit Regressionstest), mittlere/geringe
  Funde bleiben als Vorschlagsliste bis zur expliziten Freigabe.
- Erste Runde (07/2026) behoben: KeyError-Crash-Risiko bei fehlendem
  "extrahierte_daten"-Key (checks.py, IMMER `.get("extrahierte_daten", {})`
  verwenden, NIE `d["extrahierte_daten"]`), krypto_report-Dokumente ohne
  FIFO-Engine fehlten in der Steuerschätzung (jetzt Fallback mit
  Doppelzählungs-Schutz), Übergangsbeihilfe floss nirgends in Rechnung/
  Export ein.
- Zweite Runde (07/2026, nach expliziter Freigabe "alles aufräumen und
  fixen") – alle A.2/A.3-Funde aus AUDIT.md umgesetzt:
  - M1: Verlustvortrag § 23/KAP wirkt jetzt WIRKLICH mindernd (vorher nur
    Anzeige) – `interview["verlustvortrag_23"]` mindert Krypto-Gewinn vor
    Freigrenzenprüfung, `verlustvortrag_kap_*` mindert die KAP-
    Bemessungsgrundlage (Schritt 10/10b in veranlagung.py).
  - M2: Vorsorgeaufwand-Höchstbetrag (§ 10 Abs. 4 EStG, 1.900 €/Person
    Arbeitnehmer) jetzt real berechnet statt pauschal 19 % geschätzt –
    `cfg["vorsorge_hoechstbetrag_arbeitnehmer"/"_selbststaendig"]`,
    sonstige Vorsorgeaufwendungen (private Zusatzversicherungen) wirken
    nur noch bis zum Deckel zusätzlich zu RV/KV/PV.
  - M4: eToro-Parser parst vorzeichenbehaftete Beträge mit
    Tausendertrennzeichen korrekt (`_clean_num_signed()` statt der alten
    `.replace()`-Kette, die bei negativen Werten crashte/falsch rundete).
  - M8: Übergangsbeihilfe fließt jetzt mit eigenem Lohnsteuerabzug
    (lohnsteuer/soli/kirchensteuer aus vision.py-Extraktion) in die
    Rechnung UND wird automatisch gegen die Fünftelregelung geprüft
    (siehe unten) statt nur als Hinweistext.
  - Fünftelregelung § 34 Abs. 1, Abs. 2 Nr. 4 EStG: NEUES eigenständiges,
    separat getestetes Modul `core/fuenftelregelung.py`
    (`fuenftelregelung()`), rechnet die Vergleichsrechnung (normale
    Besteuerung vs. Fünftel-Methode) für außerordentliche Einkünfte
    (aktuell: Übergangsbeihilfe) automatisch durch und wählt die
    günstigere Variante – kein reiner Hinweistext mehr.
  - Günstigerprüfung KAP (§ 32d Abs. 6 EStG): veranlagung.py Schritt 10b
    vergleicht jetzt den tatsächlichen Grenzsteuersatz mit der 25 %
    Abgeltungsteuer und wendet automatisch den günstigeren an, inkl.
    Rechenweg-Ausweis der Ersparnis – vorher nur ein Hinweis ohne
    Berechnung.
  - Abgabefrist-Hinweistext 2025 korrigiert (30.04.2027 → 01.03.2027,
    da mit Steuerberater).
  - Kleinere technische Aufräumarbeiten: `jahr_zuordnung.ist_im_jahr()`
    als gemeinsames Prädikat (vorher doppelte Mengen-Logik in
    dokumente_ui.py), PDF-Report-Dateiname kollisionssicher
    (uuid-Suffix), `ruff`-Lint-Setup (siehe unten).
- Ruff-Lint-Setup: `pyproject.toml` mit `[tool.ruff.lint] select = ["F"]`
  – bewusst NUR Pyflakes (unbenutzte Imports, undefinierte Namen,
  Doppel-Definitionen), keine Stilregeln (E7xx/E4xx), um keinen
  großflächigen Reformatierungs-Diff zu erzwingen. `ruff check .` vor
  größeren Änderungen laufen lassen.
- Pausch-/Freibeträge werden bei Gelegenheit gegen aktuelle BMF-/
  Fachportal-Quellen gegengeprüft (WebSearch), nicht nur aus dem
  Trainingswissen übernommen – Abweichungen landen in AUDIT.md.

## Betriebsmodul (EÜR, Anlage G/S) – Ausbaustufe 6
- `core/betrieb.py` – Datenmodell Betrieb/Position/AfaPosition (dataclasses,
  Daten als ISO-Strings statt datetime → persist.py braucht keine
  Sonderbehandlung). berechne_euer(betrieb, jahr, cfg): Einnahmen −
  Ausgaben − AfA = Gewinn. AfaPosition.afa_fuer_jahr(): lineare AfA,
  zeitanteilig nach VOLLEN MONATEN im Anschaffungsjahr (§ 7 Abs. 1 EStG) –
  über monatliche_afa × Monate-im-Jahr, nicht grob pro-rata übers Jahr.
- Steuerliche Sonderregeln als Hinweise (NIE hart kodiert, alle
  Schwellwerte aus cfg): § 3 Nr. 72 EStG PV-Steuerbefreiung bis 30 kWp
  GILT NUR FÜR STROM, nicht für Wärme (Fernwärme/BHKW bleibt gewerblich –
  Namens-Heuristik warnt, wenn "wärme"/"bhkw" im Betriebsnamen steht trotz
  art≠photovoltaik). § 19 UStG Kleinunternehmer-Umsatzgrenzen sind
  JAHRESABHÄNGIG (2024: 22.000 €/50.000 €, ab 2025: 25.000 €/100.000 € –
  JStG 2024) → cfg["kleinunternehmer_grenze_vorjahr"/"_laufend"].
  § 11 GewStG Gewerbesteuer-Freibetrag 24.500 € NUR bei art=="gewerblich"
  (Freiberufler zahlen keine Gewerbesteuer).
- Kategorien "betrieb_einnahme"/"betrieb_ausgabe": Vision extrahiert
  betrieb_zuordnung, netto/umsatzsteuer/brutto, menge_und_einheit,
  gegenpartei, bei Anschaffungen ist_anlagegut + geschaetzte_nutzungsdauer.
  Anlagegüter werden NICHT automatisch als AfA übernommen (steuerlich zu
  wichtig für Stillschweigen) – Tab 🏭 Betrieb zeigt sie als Vorschlag mit
  Bestätigungs-Button (core/betrieb_ui.py::_anlagegut_vorschlaege).
- `core/betrieb_ui.py` – Tab "🏭 3 · Betrieb": Betriebe anlegen, EÜR-
  Übersicht, Einnahmen-/Ausgaben-/AfA-Tabellen (aus Belegen via
  _sync_docs_in_betrieb() automatisch befüllt, dedupliziert über
  Positon.quelle=Dateiname, + manuelle st.form-Eingabe). Ergebnis landet
  in interview["_betriebe"] (gewinn_pro_person je P1/P2) – analog zum
  Krypto-Modul-Pattern (interview["_crypto"]), von veranlagung.py/
  elster_export.py/checks.py gelesen, OHNE core.betrieb direkt zu
  importieren (lose Kopplung).
- Fragebogen "hat_betrieb_{P}" je Person (Tab Fragebogen); Gewinn fließt
  als eigene Einkunftsart (Schritt "1b") in berechne_veranlagung ein;
  eigener Export-Block "Anlage G / Anlage EÜR" in elster_export.py
  (Anlage-Label je nach art: G/S/V); checks.py warnt bei Betrieb ohne
  Belege, unbestätigten Anlagegut-Belegen und promotet "⚠️"-Hinweise aus
  betrieb.py (Umsatzgrenzen etc.) zu zentralen Findings.

## Chat-Dokumenten-Triage & Zuordnungs-Historie
- `core/vision.py::_berechne_klaerungsbedarf()` – deterministisch in
  Python (NICHT vom Modell behauptet, daher reproduzierbar testbar):
  true bei confidence<0.7, Kategorie "sonstiges" ODER fehlenden
  steuerlich relevanten Angaben (Betrag/Datum fehlt, offene Rückfrage,
  bei Betriebsbelegen fehlende betrieb_zuordnung).
- `core/erklaerungen.py::klaerungs_chat()` – Steuerberater-Chat für EIN
  konkretes unklares Dokument, Kontext = extrahierte Daten + Kategorien
  aus categories.py + Personen + Betriebe. Antwortet strukturiert
  {"antwort", "vorschlag": {...}, "sicher": bool} – "sicher" erst true
  bei konkreter, begründeter Zuordnung ohne offene Rückfrage.
- `core/dokumente_ui.py` – Bereich "❓ Klärung nötig (N)" oben in Tab 1,
  Mini-Chat pro Dokument (eigener Verlauf in
  session_state[f"klaerchat_{dateiname}"]). Bei "sicher": true → Button
  "✅ Zuordnung übernehmen" (_uebernehme_chat_vorschlag()) setzt
  Kategorie/Inhaber/Betrieb/Steuerjahr/Betrag, klaerungsbedarf=False,
  protokolliert in doc["hinweise"] UND doc["zuordnungs_historie"].
- Jedes Dokument führt "zuordnungs_historie" (Liste von
  {zeitpunkt, aktion, von, nach, quelle: automatisch|chat|manuell,
  begruendung}) – initialer Eintrag von analyze_document(), weitere bei
  manueller Korrektur (Tab-1-Selectbox) und Chat-Übernahme
  (_historie_eintrag()-Helper, ein Aufruf pro Änderungsereignis).
- elster_export.py rendert einen Anhang "Herkunft der Werte" – NUR für
  Dokumente mit mehr als dem initialen Automatik-Eintrag (sonst wäre der
  Anhang bei jedem einzelnen Beleg redundant).
- persist.py brauchte KEINE Änderung: Dokumente sind bereits reine Dicts,
  zuordnungs_historie wird als weiterer Key transparent mitgespeichert/
  -geladen (durch tests/test_klaerung.py abgesichert).

## Architektur
- `app.py` – Streamlit-UI, 7 Tabs (Dokumente / Krypto / Betrieb /
  Fragebogen & Prüfung / Spar-Check / Ergebnis & ELSTER / Verstehen).
  State in st.session_state: docs, interview, analyzed_files, betriebe.
- `core/tax_config.py` – Pauschbeträge pro Jahr (TAX_YEARS-Dict).
  Neues Jahr = Block kopieren + BMF-Werte eintragen. Fallback auf
  nächstliegendes Jahr mit Warnung (_geprueft=False).
- `core/categories.py` – 13 Dokumentkategorien → Anlagen-Mapping.
- `core/vision.py` – Anthropic-API-Call (PDF als document-Block, Bilder
  als image-Block, base64). System-Prompt erzwingt striktes JSON.
  Modell: claude-sonnet-4-6 (konfigurierbar in tax_config.VISION_MODEL).
- `core/checks.py` – Regelwerk, liefert Findings mit Level
  fehler/warnung/frage/hinweis. Enthält entfernungspauschale()
  (0,30 €/km bis 20 km, 0,38 € ab km 21).
- `core/elster_export.py` – build_summary() aggregiert pro Anlage,
  render_elster_help() erzeugt Markdown, export_json() Rohdaten.
- `core/fuenftelregelung.py` – fuenftelregelung(): Vergleichsrechnung
  § 34 Abs. 1/Abs. 2 Nr. 4 EStG für außerordentliche Einkünfte, von
  veranlagung.py aufgerufen, eigenständig getestet.

## Konventionen
- Sprache: Code-Kommentare, UI und Prompts auf Deutsch.
- Beträge intern als float EUR; Anzeige deutsch formatiert (1.234,56 €)
  über die e()-Lambda in elster_export.py.
- `_num()` in checks.py parst deutsche Zahlformate ("1.234,56") robust –
  für alle Betragskonvertierungen verwenden.
- Neue Prüfregeln immer in core/checks.py ergänzen, nicht in der UI.
- Neue Dokumenttypen: categories.py + Extraktionsfelder im System-Prompt
  von vision.py ergänzen (beide Stellen!).

## Setup & Start
```bash
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
set ANTHROPIC_API_KEY=sk-ant-...
streamlit run app.py
```

## Tests
Kein pytest-Framework, aber ein `tests/`-Ordner mit eigenständig
lauffähigen Smoketests (jeweils `python tests/test_X.py`, reine
assert-Skripte ohne API-Zugriff – Mock-Doc-Dicts direkt an run_checks()/
build_summary()/berechne_veranlagung() übergeben):
- `test_doppelerfassung.py` – Doppelerfassungs-Wächter (Scan vs. Spar-Check)
- `test_automatik.py` – NK-Abrechnung/Broker-Steuerbericht-Automatik
- `test_audit_fixes.py` – Regressionen aus dem ersten Audit (KeyError-Fix,
  krypto_report-Fallback, Übergangsbeihilfe)
- `test_betrieb.py` – EÜR/AfA-Berechnung, Integration in Rechner + Export
- `test_klaerung.py` – Chat-Triage-Übernahme, Zuordnungs-Historie,
  persist.py-Rundreise
- `test_audit_nachbesserungen.py` – Regressionen der zweiten Audit-Runde
  (M2 Vorsorge-Höchstbetrag, M4 eToro-Vorzeichen-Parsing u. a.)
- `test_fuenftelregelung.py` – eigenständiges Modul-Test für
  `core/fuenftelregelung.py` (u. a. mathematischer Neutralitätsbeweis in
  der linearen Tarifzone, nie schlechter als Normalbesteuerung)
Bei Änderungen an checks.py/veranlagung.py/elster_export.py: alle
Testdateien laufen lassen, bevor die App gestartet wird (`for f in
tests/test_*.py; do python "$f"; done`). Zusätzlich `ruff check .` für
den Pyflakes-Lint-Durchlauf (unbenutzte Imports/undefinierte Namen).

## Bekannte Grenzen / Backlog-Ideen
- Krypto: Transfers zwischen eigenen Wallets übernehmen Haltefrist nicht
  automatisch (Warnung wird ausgegeben) → Lot-Verknüpfung wäre Ausbau
- eToro liefert keine offenen Positionen → Optimizer dort unvollständig
- Echte Export-Dateien der Börsen noch nicht getestet (nur synthetische) –
  ERSTER SCHRITT in Claude Code: echte eToro/Coinbase-Exporte durchlaufen
  lassen und Parser nachschärfen
- Extraktionsqualität bei schlechten Fotos → ggf. Retry mit Hinweis-Prompt
- Zumutbare Belastung (agB) wird nicht berechnet, nur erwähnt
- Belegablage: analysierte Dateien werden nicht gespeichert, nur Metadaten
- Betriebsmodul: nur EÜR (§ 4 Abs. 3 EStG), keine Bilanzierung; keine
  Umsatzsteuer-Voranmeldung; Vermietung (Anlage V) rechnerisch wie EÜR
  behandelt (strukturell identisch, aber andere Anlage/Terminologie)
- Ausbaustufe-5-Connectors (Coinbase-API, Base-Chain) weiterhin
  ⚠️ LIVE UNGETESTET – kann ohne echten API-Zugriff nicht verifiziert
  werden, siehe Abschnitt oben

## Wichtig
Steuerrechtliche Konstanten NIE hart in Logik schreiben – immer über
cfg aus tax_config.py. Disclaimer (keine Steuerberatung, § 5 StBerG)
in UI und Exporten beibehalten.
