"""
Einfacher Modus – geführter Schritt-für-Schritt-Wizard für Steuer-Laien,
die sich in der Tab-Ansicht (Experten-Modus) überfordert fühlen. Nutzt
dieselben Kernfunktionen wie der Experten-Modus (render_dokumente_tab,
render_crypto_tab, berechne_veranlagung, build_summary) – nur mit
weniger Feldern gleichzeitig auf dem Bildschirm und großen Ja/Nein-Fragen
statt Fachformularen.
"""

import streamlit as st

from .checks import run_checks
from .crypto_ui import render_crypto_tab
from .dokumente_ui import render_dokumente_tab
from .elster_export import build_summary, export_json, render_elster_help
from .jahr_zuordnung import docs_im_jahr
from .veranlagung import berechne_veranlagung

_SCHRITTE = ["Start", "Belege", "Fragen", "Ergebnis", "Fertig"]


def _fmt(v):
    return f"{v:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def _nav(weiter_ok: bool = True, weiter_text: str = "Weiter →"):
    idx = st.session_state.wizard_step
    c1, _mitte, c3 = st.columns([1, 3, 1])
    with c1:
        if idx > 0 and st.button("← Zurück", use_container_width=True):
            st.session_state.wizard_step -= 1
            st.rerun()
    with c3:
        if idx < len(_SCHRITTE) - 1 and weiter_ok and st.button(
                weiter_text, type="primary", use_container_width=True):
            st.session_state.wizard_step += 1
            st.rerun()


def render_wizard(cfg: dict, api_key: str, model: str, interview: dict,
                  personen: dict, erklaermodus: bool):
    st.session_state.setdefault("wizard_step", 0)
    idx = max(0, min(st.session_state.wizard_step, len(_SCHRITTE) - 1))
    st.session_state.wizard_step = idx

    st.progress(idx / (len(_SCHRITTE) - 1))
    st.caption(f"Schritt {idx + 1} von {len(_SCHRITTE)} · {_SCHRITTE[idx]}")

    if idx == 0:
        _schritt_start(api_key)
    elif idx == 1:
        _schritt_belege(cfg, api_key, model, personen, erklaermodus)
    elif idx == 2:
        _schritt_fragen(cfg, api_key, model, interview, personen)
    elif idx == 3:
        _schritt_ergebnis(cfg, interview)
    else:
        _schritt_fertig(cfg, interview, erklaermodus)


def _schritt_start(api_key):
    st.title("👋 Willkommen bei deinem Steuer-Assistenten!")
    st.markdown(
        "Wir gehen das gemeinsam in **4 einfachen Schritten** durch:\n\n"
        "1. 📄 Du lädst deine Belege hoch (Fotos oder PDFs reichen).\n"
        "2. ❓ Du beantwortest ein paar kurze Ja/Nein-Fragen.\n"
        "3. 💶 Du siehst dein voraussichtliches Ergebnis.\n"
        "4. ✅ Du bekommst eine fertige Hilfe für ELSTER.\n\n"
        "Du brauchst kein Steuer-Wissen – wir erklären alles unterwegs, "
        "und du kannst jederzeit einen Schritt zurückgehen."
    )
    if not api_key:
        st.info("💡 Trage links in der Seitenleiste zuerst deinen "
                "**Anthropic API-Key** ein – damit können Belege automatisch "
                "gelesen werden.")
    if st.button("Los geht's! →", type="primary"):
        st.session_state.wizard_step = 1
        st.rerun()


def _schritt_belege(cfg, api_key, model, personen, erklaermodus):
    st.title("📄 Schritt 1: Belege hochladen")
    render_dokumente_tab(cfg, api_key, model, personen, erklaermodus)
    st.divider()
    _nav()


def _schritt_fragen(cfg, api_key, model, interview, personen):
    st.title("❓ Schritt 2: Ein paar kurze Fragen")
    st.markdown("Beantworte einfach mit **Ja** oder **Nein** – das war's.")

    c1, c2 = st.columns(2)
    with c1:
        interview["kirchensteuerpflichtig"] = st.radio(
            "⛪ Zahlst du Kirchensteuer?", ["Nein", "Ja"],
            index=1 if interview.get("kirchensteuerpflichtig") else 0,
            horizontal=True, key="wz_kirche") == "Ja"
        interview["kirchensteuerpflichtig_beantwortet"] = True
        interview["hat_kinder"] = st.radio(
            "👶 Hast du Kinder?", ["Nein", "Ja"],
            index=1 if interview.get("hat_kinder") else 0,
            horizontal=True, key="wz_kinder") == "Ja"
    with c2:
        interview["hat_bundeswehr"] = st.radio(
            "🎖️ Bekommst du Übergangsgebührnisse von der Bundeswehr?",
            ["Nein", "Ja"],
            index=1 if interview.get("hat_bundeswehr", True) else 0,
            horizontal=True, key="wz_bw") == "Ja"
        interview["hat_krypto_verkauft"] = st.radio(
            f"₿ Hast du in {cfg['jahr']} Krypto verkauft oder getauscht?",
            ["Nein", "Ja"],
            index=1 if interview.get("hat_krypto_verkauft") else 0,
            horizontal=True, key="wz_krypto") == "Ja"

    if interview["hat_krypto_verkauft"]:
        with st.expander("🪙 Deine Krypto-Verkäufe eintragen", expanded=True):
            render_crypto_tab(cfg, api_key, model, interview, personen)

    st.caption("Mehr Details (Fahrtkosten, Verlustvorträge, Stammdaten für "
               "ELSTER …) findest du jederzeit im **🛠️ Experten-Modus** "
               "in der Seitenleiste – für den Anfang reicht das hier.")
    st.divider()
    _nav()


def _schritt_ergebnis(cfg, interview):
    st.title("💶 Schritt 3: Dein voraussichtliches Ergebnis")
    docs = docs_im_jahr(st.session_state.docs, cfg["jahr"])
    v = berechne_veranlagung(docs, cfg, interview)

    if not v["hat_lsb"]:
        st.warning("Wir brauchen mindestens deine **Lohnsteuerbescheinigung**, "
                   "um ein Ergebnis zu schätzen. Geh einen Schritt zurück "
                   "und lade sie in Schritt 1 hoch.")
    else:
        erg = v["ergebnis"]
        if erg >= 0:
            st.success(f"## 🎉 Du bekommst voraussichtlich "
                       f"**{_fmt(erg)}** zurück!")
        else:
            st.warning(f"## 😬 Du musst voraussichtlich "
                       f"**{_fmt(abs(erg))}** nachzahlen.")
        st.caption("Das ist eine grobe Schätzung – der echte Bescheid vom "
                   "Finanzamt kann davon abweichen.")
        with st.expander("🧮 Wie kommt diese Zahl zustande?"):
            for schritt in v["schritte"]:
                st.markdown(f"- {schritt['text']}: **{_fmt(schritt['wert'])}**")

    st.divider()
    findings = run_checks(docs, cfg, interview)
    st.session_state.findings = findings
    fehler = [f for f in findings if f["level"] == "fehler"]
    if fehler:
        st.error(f"⚠️ {len(fehler)} wichtige Sache(n) bitte noch klären, "
                 "bevor du abgibst:")
        for f in fehler:
            st.markdown(f"- {f['text']}")
    elif v["hat_lsb"]:
        st.success("✅ Keine dringenden Probleme gefunden.")

    st.divider()
    _nav()


def _schritt_fertig(cfg, interview, erklaermodus):
    st.title("✅ Fertig! Hol dir deine ELSTER-Hilfe")
    docs = docs_im_jahr(st.session_state.docs, cfg["jahr"])
    if not docs and not interview.get("_crypto"):
        st.info("Du hast noch keine Belege hochgeladen – geh gerne zurück "
                "zu Schritt 1.")
        _nav(weiter_ok=False)
        return

    summary = build_summary(docs, cfg, interview)
    help_md = render_elster_help(summary, erklaeren=erklaermodus)
    st.balloons()
    st.markdown("Super gemacht! Lade dir jetzt deine persönliche "
                "Eingabehilfe herunter und trage die Werte bei "
                "**elster.de** ein.")
    c1, c2 = st.columns(2)
    with c1:
        st.download_button("⬇️ Meine ELSTER-Hilfe (zum Ausdrucken)", help_md,
                           file_name=f"elster_hilfe_{cfg['jahr']}.md",
                           mime="text/markdown", type="primary",
                           use_container_width=True)
    with c2:
        st.download_button(
            "⬇️ Rohdaten (JSON, für Fortgeschrittene)",
            export_json(summary, st.session_state.docs,
                        st.session_state.get("findings", [])),
            file_name=f"steuerdaten_{cfg['jahr']}.json",
            mime="application/json", use_container_width=True)
    with st.expander("📋 Alle Details anzeigen"):
        st.markdown(help_md)

    st.caption("⚠️ Dieses Tool ersetzt keine Steuerberatung (§ 5 StBerG). "
               "Alle Werte vor Abgabe in ELSTER gegenprüfen.")
    st.divider()
    _nav(weiter_ok=False)
