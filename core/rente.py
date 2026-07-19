"""
Anlage R – gesetzliche Rente (§ 22 Nr. 1 Satz 3 Buchst. a Doppelbuchst. aa
EStG). Der steuerpflichtige Anteil einer Rente hängt NICHT vom aktuellen
Steuerjahr ab, sondern vom Jahr des Rentenbeginns ("Kohorte") – dieser
Prozentsatz gilt einmalig festgeschrieben für die gesamte Rentenlaufzeit.

Deckt den Regelfall ab (gesetzliche Rentenversicherung, Rürup-/Basisrente).
Sofortbeginnende Leibrenten aus privater Rentenversicherung gegen
Einmalbeitrag nutzen stattdessen eine abweichende, altersabhängige
Ertragsanteil-Tabelle (§ 22 Nr. 1 S. 3 Bst. a Doppelbuchst. bb EStG) – das
ist ein Sonderfall und wird hier bewusst nicht abgebildet (kein bekannter
Anwendungsfall im Nutzerprofil dieses Tools).
"""

from .checks import _num


def besteuerungsanteil_prozent(rentenbeginn_jahr: int, cfg: dict) -> float:
    """Fixer Besteuerungsanteil (%) für die Kohorte des Rentenbeginn-Jahres.
    UNBEKANNTES Jahr (0/None) → konservativ 100 % (volle Steuerpflicht, um
    keine Steuer zu unterschätzen) – das ist bewusst ANDERS als ein
    bekanntes, nur sehr altes Jahr (< 1990), das echt in die günstige
    50-%-Kohorte fällt."""
    tabelle = cfg.get("renten_besteuerungsanteil", {})
    if not rentenbeginn_jahr:
        return 100.0
    if not tabelle:
        return 100.0
    if rentenbeginn_jahr in tabelle:
        return tabelle[rentenbeginn_jahr]
    if rentenbeginn_jahr < min(tabelle):
        return tabelle[min(tabelle)]
    return tabelle[max(tabelle)]


def rentenanteil_steuerpflichtig(jahresbetrag: float, rentenbeginn_jahr: int,
                                 cfg: dict) -> dict:
    """Steuerpflichtiger Anteil einer Jahresrente. Der Freibetrag (Differenz
    zum Jahresbetrag) wird EINMALIG im zweiten vollen Rentenbezugsjahr als
    fester Euro-Betrag festgeschrieben – hier vereinfacht als laufender
    Prozentsatz auf den jeweiligen Jahresbetrag angewendet (bei stabilem
    Rentenbetrag entspricht das exakt dem festgeschriebenen Freibetrag)."""
    jahresbetrag = max(0.0, _num(jahresbetrag))
    anteil_pct = besteuerungsanteil_prozent(int(rentenbeginn_jahr or 0), cfg)
    steuerpflichtig = round(jahresbetrag * anteil_pct / 100.0, 2)
    return {
        "jahresbetrag": round(jahresbetrag, 2),
        "besteuerungsanteil_prozent": anteil_pct,
        "steuerpflichtiger_anteil": steuerpflichtig,
        "steuerfreier_anteil": round(jahresbetrag - steuerpflichtig, 2),
    }
