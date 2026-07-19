"""
Fünftelregelung (§ 34 Abs. 1, Abs. 2 Nr. 4 EStG) für außerordentliche
Einkünfte – hier: Vergütung für eine mehrjährige Tätigkeit, typischerweise
die Bundeswehr-Übergangsbeihilfe (Einmalzahlung als Abgeltung mehrjähriger
Dienstzeit).

Methode: Die außerordentlichen Einkünfte werden für die TARIFBERECHNUNG so
behandelt, als wären sie auf 5 Jahre verteilt (Progressionsglättung),
tatsächlich versteuert wird aber alles im Zuflussjahr:
  1. ESt auf zvE OHNE die außerordentlichen Einkünfte
  2. ESt auf zvE OHNE + 1/5 der außerordentlichen Einkünfte
  3. Differenz aus 1./2. × 5 = ESt auf die außerordentlichen Einkünfte
  4. Gesamt-ESt = 1. + 3.

Das Finanzamt wendet die Fünftelregelung von Amts wegen an, wenn sie
günstiger ist als die normale Besteuerung – rechnerisch ist sie bei
progressivem Tarif nie schlechter als die volle Versteuerung im
Zuflussjahr (Konvexität der Tariffunktion).

Voraussetzung (nicht automatisch prüfbar, siehe Warnhinweis): Es muss sich
laut § 34 Abs. 2 Nr. 4 EStG um eine "Vergütung für mehrjährige Tätigkeit"
handeln (Zusammenballung von Einkünften mehrerer Jahre in einer Zahlung).
"""

from .crypto import est_nach_tarif


def _est(zve: float, cfg: dict, splitting: bool) -> float:
    if zve <= 0:
        return 0.0
    return (2 * est_nach_tarif(zve / 2, cfg)) if splitting \
        else est_nach_tarif(zve, cfg)


def fuenftelregelung(zve_ohne_aussererdentlich: float,
                     aussererdentliche_einkuenfte: float,
                     cfg: dict, splitting: bool) -> dict:
    """Vergleicht volle Besteuerung vs. Fünftelregelung für außerordentliche
    Einkünfte (z. B. Übergangsbeihilfe) und liefert beide Ergebnisse plus
    die günstigere Variante.

    Rückgabe: {
        "est_normal": ESt bei voller Versteuerung (zvE_ohne + Betrag),
        "est_fuenftel": ESt mit Fünftelregelung angewendet,
        "ersparnis": est_normal - est_fuenftel (>= 0, da nie ungünstiger),
        "guenstiger": "fuenftel" | "normal" (bei Gleichstand "normal"),
    }
    """
    zve_ohne = max(0.0, zve_ohne_aussererdentlich)
    betrag = max(0.0, aussererdentliche_einkuenfte)

    est_normal = _est(zve_ohne + betrag, cfg, splitting)

    est_basis = _est(zve_ohne, cfg, splitting)
    est_mit_fuenftel_zve = _est(zve_ohne + betrag / 5, cfg, splitting)
    est_auf_fuenftel = 5 * (est_mit_fuenftel_zve - est_basis)
    est_fuenftel = round(est_basis + est_auf_fuenftel, 2)

    ersparnis = round(est_normal - est_fuenftel, 2)
    guenstiger = "fuenftel" if ersparnis > 0 else "normal"

    return {
        "est_normal": round(est_normal, 2),
        "est_fuenftel": est_fuenftel,
        "ersparnis": max(0.0, ersparnis),
        "guenstiger": guenstiger,
    }
