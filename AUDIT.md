# Code- und Steuer-Audit

Durchgeführt von Claude Code in einer Doppelrolle als Senior-Python-Entwickler
und erfahrener deutscher Steuerberater. Grundlage: vollständige Lektüre von
`app.py` und allen Dateien in `core/` (inkl. `core/connectors/`).

Stand: 19.07.2026. Steuerwerte für 2024/2025 wurden gegen aktuelle
BMF-/Fachportal-Quellen gegengeprüft (siehe Abschnitt B.6).

---

## A) Technischer Audit

### A.1 Kritisch – in diesem Commit behoben

| # | Fund | Datei(en) | Fix |
|---|------|-----------|-----|
| 1 | `d["extrahierte_daten"]` per direktem Dict-Zugriff (statt `.get(...)`) an 9 Stellen in `run_checks()`. Fehlt der Key (z. B. bei handgepflegtem/älterem `persist.py`-JSON, oder künftig bei programmatisch erzeugten Dokumenten aus Teil 2/3), crasht die **komplette** Prüfung mit `KeyError` – nicht nur für das betroffene Dokument. | `core/checks.py` | Alle 9 Stellen auf `d.get("extrahierte_daten", {})` umgestellt. |
| 2 | Lädt ein Nutzer ein `krypto_report`-Dokument (z. B. Blockpit/CoinTracking-PDF) hoch, **ohne** den Krypto-Tab (FIFO-Engine) zu nutzen, erscheint der Gewinn zwar korrekt in der ELSTER-Hilfe (`elster_export.py` hatte bereits einen Fallback), aber die **Steuerschätzung** (`berechne_veranlagung`) ignorierte ihn komplett – das prominent angezeigte "Geschätztes Ergebnis" war dadurch potenziell erheblich zu optimistisch (fehlende Nachzahlung nicht sichtbar). | `core/veranlagung.py` | Fallback ergänzt (spiegelt exakt die Guard-Logik aus `elster_export.py`: nur wenn `crypto["pro_person"]` leer ist, sonst keine Doppelzählung). Regressionstest inkl. Doppelzählungs-Check ergänzt. |
| 3 | Kategorie `uebergangsbeihilfe` (Bundeswehr-Einmalzahlung) wurde von Vision zwar erkannt und lässt sich im UI anzeigen/korrigieren, floss aber **nirgends** in Rechnung oder Export ein – weder in `berechne_veranlagung` noch in `elster_export.build_summary`. Für genau die Zielgruppe dieses Tools (Bundeswehr-Übergangsgebührnisse) konnte damit ein ggf. fünfstelliger Betrag steuerpflichtigen Arbeitslohns komplett unter den Tisch fallen. | `core/veranlagung.py`, `core/elster_export.py`, `core/checks.py` | Betrag wird jetzt konservativ **voll versteuert** in den Bruttolohn eingerechnet (bewusst *keine* Fünftelregelung – siehe B.2, Fehlberechnung wäre schlimmer als Konservativität), erscheint als eigener Rechenschritt, eigener Export-Block und löst einen `hinweis`-Finding auf die Fünftelregelung aus. |

Alle drei Fixes sind durch `tests/test_audit_fixes.py` abgesichert (inkl. Doppelzählungs-Check für Fund 2). Bestehende Tests (`test_doppelerfassung.py`, `test_automatik.py`) laufen weiterhin grün.

### A.2 Mittel – Vorschläge (Rückfrage nötig)

| # | Fund | Datei(en) |
|---|------|-----------|
| M1 | Verlustvorträge (`verlustvortrag_23`, `verlustvortrag_kap_aktien`, `verlustvortrag_kap_sonstige`) werden als Fragebogen-Feld erfasst und in der ELSTER-Hilfe *angezeigt*, aber **nie tatsächlich verrechnet** – `berechne_veranlagung` mindert weder den steuerpflichtigen Krypto-Gewinn noch die KAP-Erträge damit. Die Schätzung ist dadurch bei vorhandenem Verlustvortrag zu **pessimistisch** (überschätzte Nachzahlung/unterschätzte Erstattung) – umgekehrte Richtung wie A.1 #2/#3, also nicht in derselben Kategorie "kritisch, weil Steuer unterschätzt". | `core/veranlagung.py` |
| M2 | Vorsorgeaufwand wird nur grob geschätzt: entweder aus den SV-Zeilen der Lohnsteuerbescheinigung (RV/KV/PV) oder als 19-%-Pauschale vom Brutto. Es gibt **keine** echte Höchstbetragsberechnung nach § 10 Abs. 3/4 EStG (Basis-KV/PV voll abzugsfähig vs. "sonstige Vorsorgeaufwendungen" mit 1.900-€/2.800-€-Deckel, Günstigerprüfung alt/neu). Zusätzliche `vorsorge_versicherung`-Dokumente (private Haftpflicht, BU, Riester/Rürup) werden zwar in der ELSTER-Hilfe gelistet, aber – mit gutem Grund per Warnhinweis erklärt – **nicht** in die Schätzung eingerechnet. | `core/veranlagung.py` |
| M3 | Irreführender Warnhinweis: `"SV-Beiträge (Zeilen 23–26) fehlten in den Bescheinigungen"` erscheint **immer**, wenn `vorsorge == 0` – auch wenn schlicht noch **gar keine** Lohnsteuerbescheinigung hochgeladen wurde (nicht nur wenn sie hochgeladen wurde, aber die Zeilen fehlten). | `core/veranlagung.py` (Zeile ~60–67) |
| M4 | `eToro`-Parser: `profit_usd`-Parsing ersetzt blind `","` durch `"."` – bei Tausendertrennzeichen im Format `"1,234.56"` oder `"1.234,56"` würde das kaputte Zahlen erzeugen. Laut CLAUDE.md wurde die Engine bereits gegen echte eToro-Exporte validiert (vermutlich exakt das Format, das eToro tatsächlich liefert) – Änderung ohne Testdaten riskant. | `core/crypto_parsers.py` (`parse_etoro`) |
| M5 | `docs_andere = [d for d in st.session_state.docs if d not in docs_aktuell]` (und die parallele `d in docs_aktuell`-Prüfung) vergleicht Dokument-Dicts über **strukturelle Gleichheit**, nicht Identität. Zwei zufällig inhaltsgleiche Dokumente (gleicher Dateiname, Kategorie, Beträge, Datum …) würden sich gegenseitig "verschlucken". Bei echten Dateien mit unterschiedlichem `dateiname` extrem unwahrscheinlich, aber fragil. | `core/dokumente_ui.py` |
| M6 | `berechne_veranlagung`/`build_summary` filtern KAP-Erträge, Sonderausgaben, agB **nicht** nach `inhaber` – bei Zusammenveranlagung ist das für die gemeinsame gemeinsame Veranlagung korrekt (ein gemeinsamer Topf), sollte aber explizit dokumentiert werden, damit es nicht versehentlich als Bug missverstanden wird. | `core/veranlagung.py`, `core/elster_export.py` |
| M7 | Abgabefrist-**Hinweistext** "mit Berater" für 2025 ist falsch: Code sagt `30.04.2027`, korrekt (dauerhafte Fristverkürzung ab VZ 2025 auf Ende Februar) wäre **01.03.2027** (28.02.2027 fällt auf einen Sonntag). Betrifft nur den Anzeigetext, nicht die für Fristen-Warnungen genutzte `abgabefrist_datum` (die stimmt). | `core/tax_config.py` (Zeile 55) |
| M8 | `uebergangsbeihilfe`-Dokumente haben laut `vision.py`-Prompt **kein** kategoriespezifisches Extraktionsschema (nur der generische `betrag_eur`) – Lohnsteuer/Soli/Kirchensteuer, die auf der Beihilfe ggf. einbehalten wurden, werden nicht erfasst und fehlen dadurch in "bereits gezahlte Lohnsteuer". Das führt (in Kombination mit Fix A.1 #3) tendenziell zu einer **Überschätzung** der Nachzahlung – sicherer als eine Unterschätzung, aber ungenau. |`core/vision.py` |
| M9 | Keine automatische Verrechnung des im Vorjahr ggf. zu viel/zu wenig gezahlten Soli/KiSt – nicht kritisch, nur zur Vollständigkeit erwähnt. | `core/veranlagung.py` |

### A.3 Gering

- `crypto_parsers.py`: `_clean_num()` nutzt Regex-Heuristik für Dezimaltrennzeichen – bei sehr ungewöhnlichen Formaten (z. B. `"1'234.56"`) unklar definiertes Verhalten. Kein bekannter Bug, nur Robustheitshinweis.
- `report.py`: PDF-Erstellung nutzt `/tmp/krypto_steuerreport_{jahr}.pdf` als festen Pfad – bei parallelen Nutzern/Sessions auf demselben Server theoretische Race Condition (Streamlit Community Cloud: jede Session eigener Container, daher aktuell unkritisch).
- `connectors/coinbase_api.py`, `connectors/base_chain.py`: laut eigener Doku "LIVE UNGETESTET" bzw. "Live-Test nötig" – Audit bestätigt nur strukturelle Konsistenz (Rückgabetypen etc.), keine Aussage über Korrektheit gegen die echte API möglich ohne Live-Zugang.
- `core/_init_.py` und `core/connectors/_init_.py`: Dateien mit **einem** Unterstrich (statt `__init__.py`) liegen zusätzlich zu den korrekten `__init__.py`-Dateien im Repo – vermutlich ein Tippfehler bei einem früheren manuellen Upload. Wirkungslos (Python ignoriert sie), aber unnötiger Ballast.
- Kein CI/Lint-Setup (z. B. `ruff`, `flake8`) – würde diese Klasse von Bugs (bracket-access auf möglicherweise fehlende Keys) künftig automatisiert abfangen.

### A.4 Konsistenz-Check (explizit angefragt)

- **`categories.py` ↔ `erklaerungen.py`**: Alle 13 Kategorie-Keys sind in `KATEGORIE_ERKLAERUNG` vorhanden – synchron. ✅
- **`categories.py` ↔ Auswertung**: Bis auf `uebergangsbeihilfe` (jetzt behoben, A.1 #3) wird jede Kategorie in mindestens einer der drei Auswertungsstellen (`checks.py`, `veranlagung.py`, `elster_export.py`) verarbeitet. ✅ nach Fix.
- **Tests**: `tests/test_doppelerfassung.py`, `tests/test_automatik.py`, `tests/test_audit_fixes.py` (neu) – alle grün. Kein pytest-Framework, alle Skripte einzeln lauffähig (siehe CLAUDE.md-Konvention).

---

## B) Steuerfachlicher Audit

### B.1 Fehlende/unvollständige Anlagen (priorisiert für dieses Nutzerprofil)

| Priorität | Anlage/Thema | Status | Relevanz für dieses Profil |
|---|---|---|---|
| **Hoch** | **Anlage G / EÜR** (Gewerbebetrieb, z. B. Fernwärme-/Energieverkauf) | Fehlt komplett | ✅ **Teil 2 dieser Session baut das** (bereits freigegeben) |
| Hoch | **Fünftelregelung § 34 EStG** (Übergangsbeihilfe) | Nur Hinweis, keine Berechnung (siehe A.1 #3) | Sehr relevant – kann bei hoher Einmalzahlung mehrere Tausend Euro Unterschied machen |
| Mittel | **Verlustvortrag/-rücktrag – tatsächliche Verrechnung** | Nur Eingabefeld, keine Wirkung (M1) | Relevant bei Krypto-/Aktienverlusten aus Vorjahren |
| Mittel | **Günstigerprüfung KAP** | Nur Frage/Hinweis, keine echte Vergleichsrechnung (Abgeltungsteuer vs. persönlicher Steuersatz) | Relevant, da das Tool den Grenzsteuersatz für Krypto ohnehin schon berechnet (`steuer_auf_krypto`) – ließe sich mit vertretbarem Aufwand auch für KAP anwenden |
| Mittel | **Vorsorgeaufwand-Höchstbetragsberechnung** (§ 10 Abs. 3/4) | Nur grobe Schätzung (M2) | Mittlere Relevanz – wirkt sich bei Angestellten oft kaum aus (Deckel meist schon durch KV/PV erreicht), aber bei Selbständigen-Anteilen (Teil 2!) relevanter |
| Niedrig | **Anlage AV** (Riester) | Fehlt komplett | Spar-Check erwähnt Riester nur als Tipp-Text, keine Berechnung/Anlage |
| Niedrig | **Anlage R** (Renten) | Fehlt komplett | Für aktives Nutzerprofil (Ehepaar im Erwerbsleben) aktuell nicht relevant, ggf. später (gesetzl. Rente, Betriebsrente) |
| Niedrig | **Anlage V** (Vermietung) | Fehlt komplett | Nicht im aktuellen Nutzerprofil (kein Vermietungsobjekt bekannt) |
| Niedrig | **Behinderten-/Pflege-Pauschbetrag, § 33a Unterhaltsleistungen** | Fehlt in `checks.py`/`veranlagung.py` (nur als Tipp-Text im Spar-Check unter "behinderung_pflege", ohne echte Berechnung/Pauschbetragstabelle) | Aktuell nicht bekannt relevant für dieses Profil, aber leicht nachrüstbar |

### B.2 Fünftelregelung – bewusst NICHT automatisch implementiert

Eine korrekte Berechnung braucht: (a) Prüfung, ob die Zahlung wirklich "zusammengeballte Einkünfte für eine mehrjährige Tätigkeit" i. S. § 34 Abs. 2 Nr. 4 EStG ist, (b) die Fünftel-Methode (ESt auf zvE ohne Beihilfe vs. ESt auf zvE + 1/5 der Beihilfe, Differenz × 5), (c) Zusammenspiel mit dem Grundtarif/Splitting. Eine falsch berechnete Ermäßigung wäre eine konkrete Falschauskunft – deshalb aktuell nur Hinweis + konservative volle Besteuerung (A.1 #3). **Empfehlung:** als eigenständiges, sauber getestetes Feature nachrüsten, sobald gewünscht.

### B.3 Verlustvortrag/-rücktrag

Aktuell reines Anzeige-Feature. Empfehlung: `verlustvortrag_23` von `krypto_stpfl` abziehen (analog zur neuen Fallback-Logik aus A.1 #2, `max(0, krypto_stpfl - verlustvortrag_23)`), `verlustvortrag_kap_*` entsprechend von den KAP-Erträgen vor der Sparer-Pauschbetrag-Berechnung. Überschaubarer Umfang, aber bewusst nicht "kritisch" eingestuft und daher nicht automatisch umgesetzt (Interpretationsspielraum: Vortrag vs. Rücktrag, Reihenfolge der Verrechnung).

### B.4 Kirchensteuer als Sonderausgabe

Bereits korrekt umgesetzt: `kist_gezahlt` (aus LSB-Zeilen) fließt in die Sonderausgaben ein (`veranlagung.py`, Schritt 4). Kein Fund.

### B.5 Pflichtangaben-Vollständigkeit

Stammdaten-Check (`checks.py`, Ende) deckt Steuernummer/Steuer-ID/IBAN ab. Kein Fund über die bestehende Implementierung hinaus.

### B.6 Pausch- und Freibeträge 2024/2025 – Abgleich gegen aktuelle Quellen

Live per Web-Suche gegengeprüft (19.07.2026):

| Wert | Code 2024 | Quelle 2024 | Code 2025 | Quelle 2025 | Status |
|---|---|---|---|---|---|
| Grundfreibetrag | 11.784 € | 11.784 € ✅ | 12.096 € | 12.096 € ✅ | ✅ korrekt |
| Soli-Freigrenze (einzeln/zusammen) | 18.130 / 36.260 € | – (2024, nicht separat gesucht) | 19.950 / 39.900 € | 19.950 / 39.900 € ✅ | ✅ korrekt (2025 verifiziert) |
| Tarif-Eckwerte (Zonengrenzen, Koeffizienten) | – | grundsätzlich konsistent mit BMF-Formelschema | – | "Eckwerte um 2,6 % verschoben", Reichensteuer-Grenze unverändert bei 277.826 € | ✅ plausibel, Struktur stimmt |
| Kinderbetreuung (Anteil/Max) | 67 % / 4.000 € | vor 2025 geltendes Recht ✅ | 80 % / 4.800 € | 80 % / 4.800 € ✅ (Wachstumschancengesetz, ab 1.1.2025) | ✅ korrekt |
| Abgabefrist ohne Berater 2025 | – | – | 31.07.2026 | 31.07.2026 ✅ | ✅ korrekt |
| Abgabefrist **mit Berater** 2025 | – | – | 30.04.2027 (Code) | **01.03.2027** (dauerhafte Fristverkürzung ab VZ 2025) | ❌ **siehe A.2 M7** |
| § 23-Freigrenze, § 35a-Höchstbeträge, Homeoffice-Pauschale, GWG-Grenze, § 22 Nr. 3-Freigrenze | unverändert seit mehreren Jahren | – | unverändert | – | Nicht einzeln neu gesucht, laut Fachwissen seit Jahren stabil und in beiden Jahresblöcken identisch – **Empfehlung:** vor der nächsten Abgabesaison trotzdem einmal gegen ein aktuelles BMF-Schreiben gegenlesen. |

**Fazit B.6:** Die steuerlich sensibelsten Werte (Grundfreibetrag, Tarifformel, Soli-Freigrenze, Kinderbetreuung) sind korrekt. Einzige gefundene Abweichung: der Anzeige-Hinweistext zur Beraterfrist 2025 (M7, unkritisch für Berechnungen).

---

## Offene Fragen an dich

1. ~~**M1 (Verlustvortrag-Verrechnung)**~~ – soll ich das umsetzen? Überschaubarer Aufwand, würde die Schätzung genauer machen.
2. ~~**Fünftelregelung (§ 34 EStG)**~~ – soll ich ein eigenständiges, separat getestetes Berechnungsmodul dafür bauen (B.2)?
3. ~~**Günstigerprüfung KAP**~~ – echte Vergleichsrechnung statt nur Hinweis?
4. ~~**M7 (Abgabefrist-Text)**~~ – einfache Korrektur, soll ich das direkt mit übernehmen?
5. ~~Alle "gering"-Punkte (A.3)~~ – nur zur Kenntnis, oder sollen einzelne davon (z. B. die `_init_.py`-Dateien löschen) gleich mit erledigt werden?

Teil 2 (Betriebsmodul) und Teil 3 (Chat-Triage) sind bereits freigegeben und werden im Anschluss unabhängig von diesen Rückfragen umgesetzt.

---

## Status-Update (19.07.2026, nach Freigabe "alles aufräumen und fixen")

Alle offenen Fragen oben wurden mit Ja beantwortet. Umgesetzt und durch
Regressionstests abgesichert (`tests/test_audit_nachbesserungen.py`,
`tests/test_fuenftelregelung.py`, erweiterte `tests/test_audit_fixes.py`):

- **M1** – Verlustvortrag § 23 mindert jetzt den Krypto-Gewinn vor der
  Freigrenzenprüfung, `verlustvortrag_kap_*` mindert die KAP-
  Bemessungsgrundlage (veranlagung.py, Schritt 2/10).
- **M2** – Echte Vorsorgeaufwand-Höchstbetragsberechnung (§ 10 Abs. 3/4
  EStG), sonstige Vorsorgeaufwendungen wirken nur noch bis zum Deckel
  (1.900 €/Person Arbeitnehmer, konfigurierbar in tax_config.py).
- **M3, M5, M6, M7** – bereits in einer vorherigen Teilrunde erledigt
  (irreführender Warnhinweis entschärft, `ist_im_jahr()`-Prädikat statt
  struktureller Dict-Vergleiche, KAP/SA/agB-Nicht-Filterung nach Inhaber
  dokumentiert, Abgabefrist-Text 2025 korrigiert).
- **M4** – eToro-Parser parst vorzeichenbehaftete Beträge mit
  Tausendertrennzeichen jetzt korrekt (`_clean_num_signed()`).
- **M8** – Übergangsbeihilfe erfasst jetzt Lohnsteuer/Soli/Kirchensteuer
  separat (vision.py-Extraktion + veranlagung.py/elster_export.py).
- **M9** – bewusst NICHT umgesetzt: eine Verrechnung von im Vorjahr zu
  viel/zu wenig gezahltem Soli/KiSt würde ein komplett neues
  Datenmodell (Vorjahresbescheid-Erfassung) voraussetzen, das aktuell
  nirgends im Tool existiert – das ist eine neue Funktion, kein Bugfix,
  und bleibt bewusst als Backlog-Idee stehen statt ungefragt eine neue
  Eingabemaske zu bauen.
- **Fünftelregelung § 34 EStG** – eigenständiges Modul
  `core/fuenftelregelung.py`, automatische Vergleichsrechnung statt
  Hinweistext, separat getestet (inkl. mathematischem
  Neutralitätsbeweis in der linearen Tarifzone).
- **Günstigerprüfung KAP § 32d Abs. 6 EStG** – echte Vergleichsrechnung
  (persönlicher Grenzsteuersatz vs. 25 % Abgeltungsteuer) statt reinem
  Hinweis.
- **A.3 Gering**: `report.py`-Pfadkollision behoben (uuid-Suffix);
  `ruff`-Lint-Setup ergänzt (`pyproject.toml`, `select = ["F"]`) und
  3 echte unbenutzte Imports entfernt; die `_init_.py`-Tippfehler-Dateien
  existierten bei Prüfung nicht mehr im Repo (bereits anderweitig
  bereinigt); Connectors bleiben ⚠️ LIVE UNGETESTET (kein Fix ohne
  echten API-Zugriff möglich); `_clean_num()`-Regex-Robustheitshinweis
  bleibt als Kenntnisnahme stehen (kein bekannter Bug, kein konkreter
  Anwendungsfall für exotische Formate wie `"1'234.56"` bei deutschen
  Steuerbelegen).

Damit sind alle A.2/A.3-Funde aus diesem Audit abgearbeitet (mit
Ausnahme von M9, s. o.). Neue, tiefere Funde (z. B. aus B.1 "Niedrig":
Anlage AV/R/V, Behinderten-Pauschbetrag) sind nicht Teil dieser Runde
und bräuchten eine eigene Freigabe.

---

## Status-Update 2 (19.07.2026, nach expliziter Freigabe "Alles machen und
## nochmal im Loop auf Fehler testen und gegenkorrigieren")

Alle B.1-"Niedrig"-Punkte sowie die restlichen "Bekannte Grenzen"-Backlog-
Ideen wurden bewertet und – soweit mit vertretbarem Aufwand seriös
umsetzbar – implementiert, jeweils mit eigener Regressionstest-Datei
(`tests/test_neue_anlagen.py`, `tests/test_belegablage.py`,
`tests/test_crypto_fifo.py`):

- **agB Zumutbare Belastung (§ 33 Abs. 3 EStG)**: Der bisherige flache
  4-%/6-%-Näherungswert wurde durch die echte dreistufige Berechnung
  (BFH VI R 75/14, gestaffelt nach Einkommenshöhe UND Familienstand/
  Kinderzahl) ersetzt. Neues Fragebogen-Feld `kinder_anzahl`.
- **Behinderten-/Pflege-Pauschbetrag, § 33a-Unterhalt (§ 33b, § 33a
  EStG)**: Bisher nur ein Tipp-Text im Spar-Check ohne echte Berechnung –
  jetzt eine vollständige Pauschbetragstabelle (GdB 20–100, Merkzeichen
  H/Bl/TBl, Pflegegrad 2–5) und eine echte § 33a-Berechnung
  (Höchstbetrag = Grundfreibetrag, Kürzung um eigene Einkünfte des
  Empfängers über 624 €), alle OHNE Kürzung um die zumutbare Belastung
  (das ist der gesetzliche Unterschied zu normalen Krankheitskosten).
- **Anlage AV (Riester, § 10a EStG)**: Neuer Fragebogen-Bereich mit
  echter Günstigerprüfung (Sonderausgabenabzug vs. Zulage inkl.
  Kinderzulage ab/vor Geburtsjahrgang 2008) – vorher gab es nur ein
  pauschales Freitext-Feld im Spar-Check ohne Berechnung.
- **Anlage R (Renten, § 22 Nr. 1 EStG)**: Komplett neue Kategorie
  "rentenbezugsmitteilung" + `core/rente.py` mit der vollständigen
  Besteuerungsanteil-Kohortentabelle (1990–2058, inkl. der durch das
  Wachstumschancengesetz 2024 verlangsamten Steigerung ab 2023). Bei
  fehlendem Rentenbeginn-Jahr konservativ 100 % Besteuerungsanteil
  (keine Unterschätzung) – ein früher Testlauf deckte hier einen echten
  Bug auf (Fallback landete fälschlich bei 50 % statt 100 %, siehe
  `tests/test_neue_anlagen.py::test_rente_ohne_rentenbeginn_jahr_...`),
  der vor dem Commit korrigiert wurde.
- **Anlage V (Vermietung)**: War strukturell schon vorhanden
  (`betrieb.py` unterstützte `art="vermietung"` bereits vollständig,
  inkl. korrektem Anlage-V-Label im Export) – ergänzt um einen Hinweis
  zu den GEBÄUDE-AfA-Sätzen (§ 7 Abs. 4 EStG: 2 %/2,5 %/3 % je nach
  Baujahr, nicht frei wählbar wie bei sonstigen Anlagegütern).
- **Rürup/Basisrente**: Aus dem alten, undifferenzierten
  "Riester-/Rürup"-Sammelposten des Spar-Checks herausgelöst und korrekt
  als voll abzugsfähige Basisvorsorge (wie die gesetzliche RV, kein
  1.900-€-Deckel) eingeordnet – vorher wurde Rürup fälschlich implizit
  wie eine gedeckelte "sonstige Vorsorgeaufwendung" behandelt.
- **Belegablage-Persistenz**: Hochgeladene Originaldateien werden jetzt
  als Base64 im Dokument gespeichert (`doc["_bytes"]`/`doc["_mime"]`),
  überleben Speichern/Laden des Projektstands und sind per
  Download-Button wieder abrufbar – vorher gingen die Originaldateien
  nach der Analyse verloren (nur Metadaten blieben). `_bytes` wird
  bewusst aus dem JSON-Export und dem Chat-Kontext herausgefiltert
  (Größe/Redundanz).
- **Krypto: Haltefrist-Verknüpfung bei Wallet-Transfers**: Die FIFO-
  Engine (`core/crypto.py`) verknüpft jetzt automatisch
  transfer_out/transfer_in-Paare zwischen EIGENEN Wallets desselben
  Inhabers (unterschiedliches Depot, zeitlich passend, empfangene Menge
  ≤ versendete Menge wegen Netzwerkgebühr) und übernimmt Haltefrist UND
  Kostenbasis der Ursprungs-Lots ins Ziel-Depot – vorher begann die
  Haltefrist beim reinen Wallet-Wechsel fälschlich neu. Funktioniert
  auch über mehrere unterschiedlich alte Lots hinweg (jedes Sub-Lot
  behält sein eigenes Originaldatum) und bleibt bei unterschiedlichen
  Inhabern bewusst UNverknüpft. Neue Testdatei `test_crypto_fifo.py`
  deckt jetzt erstmals auch die Basis-FIFO-Logik ab (bisher ungetestet).

### Bewusst NICHT umgesetzt (technisch nicht seriös möglich oder Scope-Sprung)

- **Bilanzierung (§ 4 Abs. 1/§ 5 EStG)**: Doppelte Buchführung mit
  Bilanz/GuV/Anlagenspiegel ist ein fundamental anderes
  Rechnungslegungssystem als die EÜR, das erst ab hohen Umsatz-/
  Gewinnschwellen (i. d. R. > 800.000 €/80.000 €, HGB-Kaufmannseigen-
  schaft) überhaupt greift – für das Nebengewerbe-Profil dieses Tools
  (Kleinunternehmer-Schwellen, EÜR) irrelevant und ein Scope-Sprung
  auf ein komplett neues Rechnungslegungsmodul, keine Erweiterung des
  bestehenden EÜR-Moduls.
- **USt-Voranmeldung**: Umsatzsteuer-Voranmeldungen sind ein eigenes,
  von der Einkommensteuererklärung (dem gesamten Zweck dieses Tools)
  unabhängiges Verfahren mit eigenem Meldezeitraum/-rhythmus
  (monatlich/vierteljährlich, ELSTER-USt-VA statt Einkommensteuer) –
  nur relevant für regelbesteuerte Unternehmer, die das Tool ohnehin
  schon zum Steuerberater schickt (`kleinunternehmer_19ustg`-Warnungen
  in betrieb.py). Eigenständiges Modul außerhalb des Werkzeugzwecks.
- **eToro-Optimizer für offene Positionen**: eToro bietet für Retail-
  Nutzer keine öffentliche API zum Abruf offener Positionen (anders als
  z. B. Coinbase) – ohne diese Datenquelle kann der Optimizer (Halte-
  Empfehlungen für offene Lots) für eToro-Depots strukturell nicht
  vervollständigt werden. Kein Implementierungsdefizit, sondern eine
  externe Datenverfügbarkeits-Grenze.
- **Connectors Live-Test** (`core/connectors/coinbase_api.py`,
  `core/connectors/base_chain.py`): Weiterhin ⚠️ LIVE UNGETESTET – ein
  echter Test erfordert einen echten, live gültigen API-Key (Coinbase
  CDP-Key bzw. Basescan-Key) mit Zugriff auf ein reales Konto/eine
  reale Wallet, über die dieses Environment nicht verfügt. Kann nicht
  seriös simuliert werden, ohne den Sinn des Tests (Verifikation gegen
  die ECHTE API) zu verfehlen.

Alle Regressionstests (`for f in tests/test_*.py; do python "$f"; done`)
und `ruff check .` laufen grün. Details zur genauen Implementierung siehe
CLAUDE.md.
