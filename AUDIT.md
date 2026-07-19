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

1. **M1 (Verlustvortrag-Verrechnung)** – soll ich das umsetzen? Überschaubarer Aufwand, würde die Schätzung genauer machen.
2. **Fünftelregelung (§ 34 EStG)** – soll ich ein eigenständiges, separat getestetes Berechnungsmodul dafür bauen (B.2)?
3. **Günstigerprüfung KAP** – echte Vergleichsrechnung statt nur Hinweis?
4. **M7 (Abgabefrist-Text)** – einfache Korrektur, soll ich das direkt mit übernehmen?
5. Alle "gering"-Punkte (A.3) – nur zur Kenntnis, oder sollen einzelne davon (z. B. die `_init_.py`-Dateien löschen) gleich mit erledigt werden?

Teil 2 (Betriebsmodul) und Teil 3 (Chat-Triage) sind bereits freigegeben und werden im Anschluss unabhängig von diesen Rückfragen umgesetzt.
