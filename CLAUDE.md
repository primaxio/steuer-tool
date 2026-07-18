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
- Tab-Reihenfolge: Dokumente · Krypto · Fragebogen · Spar-Check ·
  Ergebnis&ELSTER · Verstehen.

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

## Architektur
- `app.py` – Streamlit-UI, 3 Tabs (Dokumente / Fragebogen & Prüfung /
  ELSTER-Hilfe & Export). State in st.session_state: docs, interview,
  analyzed_files.
- `core/tax_config.py` – Pauschbeträge pro Jahr (TAX_YEARS-Dict).
  Neues Jahr = Block kopieren + BMF-Werte eintragen. Fallback auf
  nächstliegendes Jahr mit Warnung (_geprueft=False).
- `core/categories.py` – 11 Dokumentkategorien → Anlagen-Mapping.
- `core/vision.py` – Anthropic-API-Call (PDF als document-Block, Bilder
  als image-Block, base64). System-Prompt erzwingt striktes JSON.
  Modell: claude-sonnet-4-6 (konfigurierbar in tax_config.VISION_MODEL).
- `core/checks.py` – Regelwerk, liefert Findings mit Level
  fehler/warnung/frage/hinweis. Enthält entfernungspauschale()
  (0,30 €/km bis 20 km, 0,38 € ab km 21).
- `core/elster_export.py` – build_summary() aggregiert pro Anlage,
  render_elster_help() erzeugt Markdown, export_json() Rohdaten.

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
Kein Test-Framework eingerichtet. Schneller Smoketest ohne API:
Mock-Doc-Dicts an run_checks() und build_summary() übergeben
(Beispiel-Struktur siehe docs-Format in app.py / vision.py-Rückgabe).
Bei Änderungen an checks.py oder elster_export.py: Smoketest laufen
lassen, bevor die App gestartet wird. Sinnvoller nächster Schritt:
pytest mit Fixtures für die Mock-Dokumente.

## Bekannte Grenzen / Backlog-Ideen
- Krypto: Transfers zwischen eigenen Wallets übernehmen Haltefrist nicht
  automatisch (Warnung wird ausgegeben) → Lot-Verknüpfung wäre Ausbau
- eToro liefert keine offenen Positionen → Optimizer dort unvollständig
- Echte Export-Dateien der Börsen noch nicht getestet (nur synthetische) –
  ERSTER SCHRITT in Claude Code: echte eToro/Coinbase-Exporte durchlaufen
  lassen und Parser nachschärfen
- Extraktionsqualität bei schlechten Fotos → ggf. Retry mit Hinweis-Prompt
- Übergangsbeihilfe (Einmalzahlung): Fünftelregelung nur als Hinweis,
  keine Berechnung
- Zumutbare Belastung (agB) wird nicht berechnet, nur erwähnt
- Belegablage: analysierte Dateien werden nicht gespeichert, nur Metadaten

## Wichtig
Steuerrechtliche Konstanten NIE hart in Logik schreiben – immer über
cfg aus tax_config.py. Disclaimer (keine Steuerberatung, § 5 StBerG)
in UI und Exporten beibehalten.
