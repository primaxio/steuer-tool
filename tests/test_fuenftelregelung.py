# Eigenständiger Test für core/fuenftelregelung.py (§ 34 EStG).
# Aufruf: python tests/test_fuenftelregelung.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.crypto import est_nach_tarif
from core.fuenftelregelung import fuenftelregelung
from core.tax_config import get_config

CFG24 = get_config(2024)


def test_fuenftelregelung_nie_schlechter_als_normal():
    # Kernaussage des § 34 EStG: bei progressivem Tarif ist die
    # Fünftelregelung nie ungünstiger als die volle Versteuerung.
    for zve_ohne, betrag in [(20000, 5000), (40000, 15000), (0, 12000),
                             (60000, 30000), (11000, 2000)]:
        r = fuenftelregelung(zve_ohne, betrag, CFG24, splitting=False)
        assert r["est_fuenftel"] <= r["est_normal"] + 0.01, r
        assert r["ersparnis"] >= 0
    print("✅ Fünftelregelung ist in allen Testfällen nie ungünstiger als "
          "die volle Versteuerung")


def test_fuenftelregelung_exakt_gleich_in_linearer_tarifzone():
    # Zone 4 (2024: bis 277.825 €) ist LINEAR (fester 42%-Grenzsteuersatz) –
    # dort darf die Fünftelregelung rechnerisch KEINEN Vorteil bringen
    # (Spreizung einer linearen Funktion ändert nichts an der Summe).
    r = fuenftelregelung(100000, 50000, CFG24, splitting=False)
    assert abs(r["est_fuenftel"] - r["est_normal"]) < 0.5, r
    assert r["guenstiger"] == "normal"
    print(f"✅ In der linearen Tarifzone (42 %) ist die Fünftelregelung "
          f"korrekt wirkungslos (est_normal={r['est_normal']}, "
          f"est_fuenftel={r['est_fuenftel']})")


def test_fuenftelregelung_bringt_vorteil_beim_zonenwechsel():
    # zvE_ohne in Zone 2 (progressiv), zvE_ohne+Betrag reicht in Zone 3 ->
    # hier MUSS die Fünftelregelung einen echten (positiven) Vorteil bringen.
    r = fuenftelregelung(20000, 15000, CFG24, splitting=False)
    assert r["ersparnis"] > 0, r
    assert r["guenstiger"] == "fuenftel"
    print(f"✅ Beim Zonenwechsel bringt die Fünftelregelung einen "
          f"nachvollziehbaren Vorteil: {r['ersparnis']} € Ersparnis")


def test_fuenftelregelung_splitting_konsistent():
    # Splitting muss durchgängig verwendet werden (2x Tarif(zvE/2)),
    # nicht nur für eine Seite des Vergleichs.
    r_einzeln = fuenftelregelung(20000, 15000, CFG24, splitting=False)
    r_splitting = fuenftelregelung(20000, 15000, CFG24, splitting=True)
    erwartet_normal = 2 * est_nach_tarif(35000 / 2, CFG24)
    assert abs(r_splitting["est_normal"] - erwartet_normal) < 0.01
    assert r_splitting["est_normal"] < r_einzeln["est_normal"], \
        "Splitting sollte bei gleichem zvE zu weniger Steuer führen"
    print("✅ Splitting-Tarif wird konsistent auf beide Vergleichsgrößen "
          "angewendet")


def test_fuenftelregelung_null_betrag_keine_wirkung():
    r = fuenftelregelung(40000, 0, CFG24, splitting=False)
    assert r["ersparnis"] == 0.0
    assert r["est_normal"] == r["est_fuenftel"]
    print("✅ Betrag=0 -> keine Ersparnis, beide Werte identisch")


def test_fuenftelregelung_negative_werte_werden_abgefangen():
    r = fuenftelregelung(-5000, -1000, CFG24, splitting=False)
    assert r["est_normal"] >= 0 and r["est_fuenftel"] >= 0
    print("✅ Negative Eingaben führen nicht zu negativer/kaputter Steuer")


if __name__ == "__main__":
    test_fuenftelregelung_nie_schlechter_als_normal()
    test_fuenftelregelung_exakt_gleich_in_linearer_tarifzone()
    test_fuenftelregelung_bringt_vorteil_beim_zonenwechsel()
    test_fuenftelregelung_splitting_konsistent()
    test_fuenftelregelung_null_betrag_keine_wirkung()
    test_fuenftelregelung_negative_werte_werden_abgefangen()
    print("🎉 Alle Fünftelregelung-Tests bestanden.")
