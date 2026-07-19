"""
Automatische Steuerjahr-Zuordnung von Belegen.
Priorität: von Claude erkanntes Steuerjahr → Jahreszahl(en) im Datum
(bei Zeiträumen das Endjahr) → None (Rückfrage an den Nutzer).
"""

import re
from collections import Counter


def bestimme_steuerjahr(doc: dict) -> int | None:
    sj = doc.get("steuerjahr")
    if sj:
        try:
            j = int(sj)
            if 2000 <= j <= 2099:
                return j
        except (ValueError, TypeError):
            pass
    jahre = [int(m) for m in re.findall(r"(?:19|20)\d{2}",
                                        str(doc.get("datum") or ""))]
    if jahre:
        return max(jahre)  # Zeitraum "01.12.2025–15.01.2026" → 2026 (Abfluss)
    return None


def jahres_uebersicht(docs: list) -> Counter:
    return Counter(int(d.get("steuerjahr_zuordnung", 0) or 0) for d in docs)


def docs_im_jahr(docs: list, jahr: int) -> list:
    return [d for d in docs
            if int(d.get("steuerjahr_zuordnung", jahr) or jahr) == jahr]
