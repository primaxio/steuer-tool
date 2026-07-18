# 🧾 Steuer-Assistent (Bonn, NRW)

Streamlit-Tool zur Vorbereitung der privaten Einkommensteuererklärung.
Belege werden per **Claude Vision** erkannt, den richtigen Anlagen
zugeordnet, auf Fehler geprüft – am Ende entsteht eine
**ELSTER-Eingabehilfe** zum 1:1-Übertragen.

## Abgedecktes Profil
- **Anlage N ×2:** ziviler Arbeitgeber + Übergangsgebührnisse Bundeswehr (BVA)
- **Anlage KAP:** Aktien/Dividenden (Bank-Steuerbescheinigungen)
- **Anlage SO:** Krypto mit vollwertiger **FIFO-Engine** (walletbezogen,
  BMF-Schreiben 06.03.2025): Import von **eToro-XLSX**, **Coinbase-CSV**,
  Base/generischen Exporten (Claude-gestützte Spaltenerkennung),
  Gebühren-Abzug, Haltefrist je Lot, **Haltefrist-Optimizer**
  („noch X Tage halten → steuerfrei"), CFD-Erkennung bei eToro (→ KAP!),
  Staking-Rewards (§ 22 Nr. 3), USD→EUR tagesgenau via EZB-Kursdatei,
  Steuerschätzung nach § 32a-Tarif inkl. Splitting
- **Zusammenveranlagung:** Depots je Ehegatte zuordenbar – § 23-Freigrenze
  wird korrekt PRO PERSON geprüft, Sparer-Pauschbetrag 2.000 € gemeinsam
- Werbungskosten (Pendlerpauschale, Homeoffice, Belege), Sonderausgaben,
  Vorsorgeaufwand, § 35a, außergewöhnliche Belastungen

## Außerdem an Bord
**Spar-Check & Erstattungsrechner:** ~23 Abzugsposten als Checkliste
(inkl. Nebenkosten-§35a, Parteispenden, BFD-Fortbildungen), kompletter
Veranlagungs-Rechenweg mit geschätzter Erstattung/Nachzahlung und
Abgabefrist-Countdown mit Verspätungszuschlag-Warnung.

**Erklär-Modus für Einsteiger:** Steuer-1×1, Glossar, Erklärungen an
jedem Dokument und jeder Anlage, plus "Frag nach"-Chat, der jede Frage
in Alltagssprache mit deinen echten Zahlen beantwortet.

Projektstand speichern/laden (JSON, Sidebar), Stammdaten-Erfassung,
Fragebogen und Werbungskosten je Ehegatte, Verlustvorträge,
Verlustbescheinigungs-Frist (15.12.), Anlage-Kind- und
Vorabpauschale-Hinweise, DBA-Warnung bei Auslandsbezug.

**Belege-Eingang:** Einfach alles hochladen – das Tool sortiert jeden
Beleg automatisch nach Steuerjahr (Zahlungsdatum/Abflussprinzip).
Belege anderer Jahre werden geparkt und sind nach dem Jahreswechsel in
der Seitenleiste sofort da – ideal, um Belege laufend übers Jahr zu
sammeln statt einmal im Jahr zu suchen.

**API-Sync & Steuerreport (Beta):** Coinbase-Abruf per Nur-Lese-CDP-Key,
Base-Wallets on-chain via Basescan (Swap-Erkennung, Gas als Gebühr,
CoinGecko-Tageskurse) und ein prüfungsfester PDF-Steuerreport mit
Methodik-Seite nach BMF-Schreiben. Live-Test der APIs steht noch aus –
siehe CLAUDE.md. eToro bleibt Datei-Import (keine öffentliche API).

## Installation
```bash
cd steuer-tool
python -m venv .venv
.venv\Scripts\activate          # Windows  (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
```

## API-Key
Anthropic-Key unter https://console.anthropic.com erstellen, dann entweder:
```bash
set ANTHROPIC_API_KEY=sk-ant-...     # Windows
export ANTHROPIC_API_KEY=sk-ant-...  # macOS/Linux
```
…oder beim Start in der Seitenleiste eintragen.
Jede Dokumentanalyse ist ein API-Aufruf (wenige Cent pro Beleg).

## Start
```bash
streamlit run app.py
```
Browser öffnet sich unter http://localhost:8501.

## Workflow
1. **Tab 1 – Dokumente:** PDFs/Fotos hochladen → „Analysieren“. Kategorie und
   Betrag lassen sich pro Beleg manuell korrigieren (🔴 = unsicher, prüfen!).
2. **Tab 2 – Krypto:** CSV/XLSX der Börsen hochladen, Inhaber wählen,
   importieren. Für USD-Exporte die EZB-Kursdatei (eurofxref-hist.csv von
   ecb.europa.eu) laden. Ergebnis: Gewinne je Ehegatte, Optimizer, Schätzung.
3. **Tab 3 – Fragebogen & Prüfung:** Pendler-km, Arbeits-/Homeoffice-Tage etc.
   beantworten. Darunter laufen automatische Prüfungen: fehlende
   Bescheinigungen, falsches Steuerjahr, Duplikate, Freigrenzen,
   Barzahlung bei § 35a, Pauschbetrags-Vergleich u. v. m.
4. **Tab 4 – ELSTER-Hilfe:** Zusammenfassung pro Anlage mit allen Werten,
   Download als Markdown + JSON. Dann in **elster.de** übertragen
   (Tipp: Belegabruf/vorausgefüllte Erklärung aktivieren).

## Neues Steuerjahr pflegen
In `core/tax_config.py` einen Jahresblock kopieren und die Pauschbeträge
anhand der BMF-Werte aktualisieren. Fehlt ein Jahr, rechnet das Tool mit dem
nächstliegenden und zeigt eine Warnung.

## Wichtige Hinweise
- **Keine Steuerberatung** im Sinne des StBerG – das Tool bereitet vor,
  die Verantwortung für die Abgabe bleibt bei dir.
- Eine **direkte elektronische Übermittlung** ans Finanzamt ist nur über
  zertifizierte ERiC-Software möglich – daher der Weg über ELSTER.
- Extrahierte Werte immer mit den Originalbelegen abgleichen (KI kann
  Zahlen falsch lesen, v. a. bei schlechten Fotos).
- Belege lokal aufbewahren (Vorhaltepflicht; das Finanzamt kann sie anfordern).
