"""
Erklär-Ebene für Steuer-Einsteiger: Glossar, Steuer-1×1, Erklärungen je
Dokumentkategorie und ELSTER-Abschnitt sowie der "Frag nach"-Chat
(Claude erklärt mit den echten Zahlen des Nutzers – keine Rechtsberatung).
"""

import anthropic

GLOSSAR = {
    "Steuererklärung": "Deine Jahres-Abrechnung mit dem Staat: Du meldest, was du verdient und beruflich/privat ausgegeben hast. Das Finanzamt vergleicht das mit der Steuer, die dein Arbeitgeber schon monatlich abgeführt hat – zu viel gezahlt = Erstattung, zu wenig = Nachzahlung.",
    "Anlage": "Ein Kapitel des Steuerformulars. Anlage N = Gehalt, Anlage KAP = Zinsen/Aktien, Anlage SO = u. a. Krypto. Du füllst nur die Kapitel aus, die dich betreffen.",
    "Lohnsteuer": "Die Steuer, die dein Arbeitgeber jeden Monat direkt vom Brutto abzieht und ans Finanzamt überweist – eine Vorauszahlung, keine Endabrechnung.",
    "Steuerklasse VI": "Gilt für den zweiten Job (bei dir: die Übergangsgebührnisse). Hier wird bewusst zu viel Lohnsteuer einbehalten – deshalb MUSST du eine Erklärung abgeben, und oft gibt es dabei eine Korrektur in die eine oder andere Richtung.",
    "Werbungskosten": "Alles, was du ausgibst, um arbeiten zu können: Fahrten, Arbeitsmittel, Fortbildungen. Sie senken dein zu versteuerndes Einkommen – du bekommst also einen Teil über die Steuer zurück.",
    "Pauschbetrag": "Ein Betrag, den JEDER automatisch abgezogen bekommt, ganz ohne Belege (z. B. 1.230 € Werbungskosten pro Arbeitnehmer). Belege lohnen sich erst, wenn du ÜBER diesem Betrag liegst.",
    "Freibetrag vs. Freigrenze": "Der wichtigste Unterschied im ganzen Steuerrecht: Beim FREIBETRAG bleibt der Betrag immer steuerfrei, nur der Rest darüber wird versteuert. Bei der FREIGRENZE gilt: Einen Cent drüber – und ALLES ist steuerpflichtig. Die 1.000 € bei Krypto sind eine Freigrenze!",
    "Entfernungspauschale": "0,30 €/km (ab Kilometer 21: 0,38 €) für die EINFACHE Strecke Wohnung–Arbeit, pro Arbeitstag – egal ob Auto, Bahn oder Rad.",
    "Homeoffice-Pauschale": "6 € pro Tag, an dem du zuhause gearbeitet hast (max. 1.260 €/Jahr). Für denselben Tag gibt es aber keine Entfernungspauschale zusätzlich.",
    "Abgeltungsteuer": "Pauschal 25 % auf Kapitalerträge (Zinsen, Dividenden, Aktiengewinne). Deutsche Banken ziehen sie automatisch ab – damit ist die Steuer 'abgegolten', also eigentlich erledigt.",
    "Sparer-Pauschbetrag": "1.000 € Kapitalerträge pro Person (Ehepaar: 2.000 € gemeinsam) bleiben steuerfrei – aber nur, wenn du der Bank einen Freistellungsauftrag erteilt hast. Sonst holst du dir die Steuer über die Anlage KAP zurück.",
    "Günstigerprüfung": "Ein Kreuzchen in der Anlage KAP: Das Finanzamt prüft, ob dein persönlicher Steuersatz unter 25 % liegt – wenn ja, bekommst du die Differenz zurück. Kann nie schaden, nur nützen.",
    "Haltefrist (Krypto)": "Kryptowährungen, die du länger als 1 Jahr hältst, kannst du KOMPLETT STEUERFREI verkaufen – egal wie hoch der Gewinn. Verkaufst du früher, zählt der Gewinn wie zusätzliches Gehalt.",
    "FIFO": "'First in, first out': Beim Verkauf gelten immer die ÄLTESTEN Coins als zuerst verkauft. Das bestimmt, welche Haltefrist und welcher Einkaufspreis für die Gewinnberechnung gelten.",
    "Krypto-Tausch": "Auch BTC gegen ETH tauschen ist steuerlich ein VERKAUF von BTC (mit Gewinn/Verlust) plus ein Neukauf von ETH – nicht erst der Verkauf gegen Euro zählt!",
    "Zusammenveranlagung / Splitting": "Ihr gebt EINE gemeinsame Erklärung ab. Eure Einkommen werden addiert, halbiert, die Steuer darauf berechnet und verdoppelt. Vorteil: Je unterschiedlicher eure Gehälter, desto mehr spart ihr.",
    "Zu versteuerndes Einkommen (zvE)": "Das, was nach Abzug aller Kosten, Pauschalen und Freibeträge vom Bruttoeinkommen übrig bleibt – NUR darauf wird die Steuer berechnet. Deshalb lohnt jeder anerkannte Abzug.",
    "Grenzsteuersatz": "Der Steuersatz auf den NÄCHSTEN verdienten Euro. Wichtig für Krypto: Steuerpflichtige Gewinne werden 'oben drauf' gerechnet und mit diesem – höchsten – Satz besteuert.",
    "Verlustbescheinigung": "Hast du bei einer Bank Verluste und bei einer anderen Gewinne, verrechnet das Finanzamt sie nur, wenn dir die Bank die Verluste bescheinigt. Antrag bis 15.12. des Jahres – danach ist die Chance fürs Jahr weg.",
    "Verlustvortrag": "Nicht verrechnete Verluste verfallen nicht, sondern werden ins nächste Jahr 'mitgenommen' und mindern dort deine Gewinne. Steht im Feststellungsbescheid vom Finanzamt.",
    "Vorabpauschale": "Bei ETFs besteuert der Staat jährlich einen fiktiven Mini-Gewinn im Voraus. Die Bank bucht das automatisch ab – beim späteren Verkauf wird es angerechnet, du zahlst also nichts doppelt.",
    "Übergangsgebührnisse": "Deine monatlichen Bundeswehr-Zahlungen nach der Dienstzeit. Steuerlich sind sie ganz normales Gehalt (zweiter Arbeitgeber, Anlage N) – nicht steuerfrei!",
    "ELSTER": "Das offizielle Online-Portal des Finanzamts (elster.de). Dort trägst du die Werte aus diesem Tool ein und schickst die Erklärung elektronisch ab.",
    "Steuerbescheid": "Die Antwort des Finanzamts (meist nach 4–12 Wochen): die offizielle Abrechnung mit Erstattung oder Nachzahlung. Immer prüfen – 1 Monat Einspruchsfrist!",
    "Belegvorhaltung": "Belege werden NICHT mehr mitgeschickt, aber du musst sie aufbewahren – das Finanzamt kann sie jederzeit nachfordern.",
}

KATEGORIE_ERKLAERUNG = {
    "lohnsteuerbescheinigung_zivil": "Die Jahres-Zusammenfassung deines Arbeitgebers: Was du brutto verdient hast und welche Steuern schon bezahlt wurden. Das Fundament der ganzen Erklärung – ohne sie geht nichts.",
    "lohnsteuerbescheinigung_bundeswehr": "Dasselbe für deine Übergangsgebührnisse – die Bundeswehr ist steuerlich dein zweiter Arbeitgeber. Weil hier Steuerklasse VI gilt, wurde vermutlich zu viel Steuer einbehalten, die über die Erklärung korrigiert wird.",
    "uebergangsbeihilfe": "Die Einmalzahlung der Bundeswehr. Sie kann ermäßigt besteuert werden ('Fünftelregelung') – das kann viel Geld sparen und sollte geprüft werden.",
    "steuerbescheinigung_bank": "Zeigt deine Aktien-/Zinserträge und die bereits abgezogene Steuer. Damit holst du dir zu viel gezahlte Abgeltungsteuer zurück, z. B. wenn der Freistellungsauftrag nicht ausgeschöpft war.",
    "krypto_report": "Die Übersicht deiner Krypto-Verkäufe. Entscheidend: Was wurde unter 1 Jahr Haltefrist verkauft (steuerpflichtig) und was darüber (steuerfrei)?",
    "werbungskosten": "Ein beruflicher Ausgabenbeleg (Laptop, Fachbuch, Fortbildung). Lohnt sich, sobald deine gesamten Werbungskosten über 1.230 € liegen – jeder Euro darüber senkt deine Steuer.",
    "vorsorge_versicherung": "Versicherungsbeiträge (Haftpflicht, BU, Kranken-/Pflegeversicherung) sind als Vorsorgeaufwand absetzbar – oft vergessen, oft mehrere hundert Euro wert.",
    "spende": "Spenden an gemeinnützige Organisationen senken als Sonderausgaben direkt dein zu versteuerndes Einkommen.",
    "handwerker_haushaltsnah": "20 % der ARBEITSKOSTEN (nicht Material!) von Handwerkern oder Haushaltshilfen zieht das Finanzamt direkt von deiner Steuer ab. Bedingung: per Überweisung bezahlt, niemals bar.",
    "nebenkostenabrechnung": "Deine Betriebskostenabrechnung enthält versteckte Steuer-Rabatte: 20 % der Lohnkosten für Hausmeister, Treppenhausreinigung & Co. zieht das Finanzamt direkt von der Steuer ab. Das Tool hat die begünstigten Posten automatisch herausgesucht – Grundsteuer, Wasser und Heizöl zählen nicht.",
    "broker_steuerbericht": "Der offizielle Jahresbericht deines Brokers. Termingeschäfte (CFDs) und Zinsen wurden automatisch in die Anlage KAP übernommen – dort werden sie mit ~26,4 % besteuert, weil Auslandsbroker keine Steuer einbehalten. Der Krypto-Wert dient als Kontrollzahl.",
    "krankheitskosten": "Arzt-, Zahnarzt-, Brillenkosten zählen als außergewöhnliche Belastung – aber erst oberhalb deiner 'zumutbaren Belastung' (einige Prozent des Einkommens). Sammeln lohnt in teuren Jahren.",
    "betrieb_einnahme": "Eine Einnahme aus deinem Betrieb oder Nebengewerbe (z. B. eine Gutschrift vom Energieversorger für verkauften Strom/Wärme). Ordne sie im Tab 'Betrieb' dem richtigen Betrieb zu – zusammen mit den Ausgaben ergibt das deinen Gewinn (Einnahmen-Überschuss-Rechnung).",
    "betrieb_ausgabe": "Eine Ausgabe deines Betriebs (Wartung, Material, Anschaffung). Sie mindert deinen Gewinn – bei größeren Anschaffungen (Anlagegütern) wird der Betrag nicht auf einmal, sondern über mehrere Jahre verteilt abgeschrieben (AfA).",
    "sonstiges": "Konnte nicht sicher zugeordnet werden – bitte einmal kurz prüfen und die richtige Kategorie wählen.",
}

ANLAGEN_ERKLAERT = {
    "N": "💡 *Einfach erklärt: Hier stehen eure Gehälter und die schon gezahlte Lohnsteuer. Das Finanzamt rechnet nach, ob die monatlichen Abzüge gepasst haben. Die Werbungskosten darunter senken die Steuer – jeder von euch hat dabei seinen eigenen 1.230 €-Pauschbetrag.*",
    "KAP": "💡 *Einfach erklärt: Deine Bank hat auf Aktiengewinne pauschal 25 % Steuer abgezogen. Hier prüfst du, ob das zu viel war – etwa weil der Sparer-Pauschbetrag (2.000 € für euch beide) nicht genutzt wurde. Meist gibt es hier Geld zurück.*",
    "SO": "💡 *Einfach erklärt: Hier kommen NUR Krypto-Verkäufe rein, die unter 1 Jahr gehalten wurden. Länger gehaltene Coins sind komplett steuerfrei und tauchen gar nicht erst auf. Achtung Freigrenze: Ab 1.000 € Gewinn pro Person wird der GESAMTE Gewinn steuerpflichtig – nicht nur der Teil darüber.*",
    "Sonderausgaben": "💡 *Einfach erklärt: Private Ausgaben, die der Staat trotzdem belohnt – vor allem Spenden und Kirchensteuer.*",
    "Vorsorgeaufwand": "💡 *Einfach erklärt: Deine Versicherungsbeiträge. Kranken- und Pflegeversicherung zählen fast immer voll.*",
    "Haushaltsnahe Aufwendungen": "💡 *Einfach erklärt: 20 % der Handwerker-Arbeitskosten werden dir DIREKT von der Steuer abgezogen – das ist bares Geld, kein bloßer Abzugsposten.*",
    "Außergewöhnliche Belastungen": "💡 *Einfach erklärt: Hohe Krankheitskosten zählen erst, wenn sie deine 'zumutbare' Eigenbeteiligung übersteigen.*",
    "Gewerbe & Selbständigkeit (EÜR)": "💡 *Einfach erklärt: Betreibst du nebenbei ein Gewerbe (z. B. Stromverkauf) oder arbeitest freiberuflich, zählt hier NICHT der Umsatz, sondern der GEWINN: Einnahmen minus Ausgaben minus Abschreibungen (AfA – große Anschaffungen werden über mehrere Jahre verteilt abgezogen, nicht auf einmal). Dieser Gewinn wird wie Gehalt zu deinem übrigen Einkommen addiert.*",
}

STEUER_101 = """
## 📖 Steuer-1×1 – euer Fall in 5 Minuten

**1. Warum ihr abgeben MÜSST:** Du hast zwei Arbeitgeber (Job + Bundeswehr-
Übergangsgebührnisse). Der zweite läuft über Steuerklasse VI, bei der pauschal
zu viel Steuer einbehalten wird. Das Finanzamt will deshalb die Jahresabrechnung
sehen – die Erklärung ist Pflicht, aber oft auch eine Chance auf Erstattung.

**2. Wie die Rechnung grundsätzlich funktioniert:**
Alle Einnahmen (Gehälter, steuerpflichtige Krypto-Gewinne …)
**minus** alle anerkannten Ausgaben (Werbungskosten, Versicherungen, Spenden …)
**=** zu versteuerndes Einkommen → darauf wird die Steuer nach Tarif berechnet
→ Vergleich mit dem, was schon gezahlt wurde → **Erstattung oder Nachzahlung.**
Deshalb gilt: Jeder Beleg, der Ausgaben nachweist, ist potenziell Geld.

**3. Als Ehepaar:** Ihr gebt EINE Erklärung unter eurer gemeinsamen
Steuernummer ab (Zusammenveranlagung mit Splitting-Vorteil). Trotzdem hat
jeder eigene Anlagen (N, SO) und eigene Pausch-/Freigrenzen – das Tool
trennt das automatisch, wenn ihr Dokumente und Depots richtig zuordnet.

**4. Krypto in einem Satz:** Über 1 Jahr gehalten = steuerfrei. Unter 1 Jahr
verkauft oder getauscht = Gewinn wird wie Extra-Gehalt besteuert – außer der
Jahresgewinn bleibt pro Person unter 1.000 € (Freigrenze: 1 € drüber = alles
steuerpflichtig!). Aktien laufen komplett getrennt davon über die Bank (25 %).

**5. Der Weg von hier:**
Tab 1 Belege hochladen → Tab 2 Krypto importieren → Tab 3 Fragen beantworten
und Prüfhinweise abarbeiten → Tab 4 Werte nach **elster.de** übertragen →
absenden → nach 4–12 Wochen kommt der Steuerbescheid (prüfen! 1 Monat
Einspruchsfrist). Belege behaltet ihr zuhause – nachreichen nur auf Anfrage.
"""

CHAT_SYSTEM = """Du bist ein geduldiger Steuer-Erklärer für absolute Laien
(Ehepaar aus Bonn: er mit zwei Arbeitsverhältnissen inkl. Bundeswehr-
Übergangsgebührnissen, Aktien und Krypto). Regeln:
- Einfache Alltagssprache, kurze Antworten (max. ~150 Wörter), keine
  Paragraphen-Schlachten; Fachbegriffe sofort in einem Halbsatz erklären.
- Nutze die mitgelieferten ECHTEN Zahlen des Nutzers für konkrete Beispiele.
- Sei ehrlich bei Unsicherheit und weise bei komplexen Themen (z. B.
  Auslandsbezug) auf Steuerberater/Lohnsteuerhilfeverein hin.
- Du gibst Bildung und Orientierung, keine verbindliche Steuerberatung."""


def frag_steuerberater(frage: str, kontext: str, verlauf: list,
                       api_key: str, model: str) -> str:
    """Chat-Antwort mit Nutzerdaten als Kontext."""
    client = anthropic.Anthropic(api_key=api_key)
    messages = list(verlauf) + [{"role": "user", "content": frage}]
    resp = client.messages.create(
        model=model, max_tokens=800,
        system=CHAT_SYSTEM + "\n\nAktuelle Daten des Nutzers (JSON):\n"
        + (kontext or "noch keine Daten erfasst"),
        messages=messages)
    return "".join(b.text for b in resp.content if b.type == "text")
