"""
Einfacher Modus – geführter Schritt-für-Schritt-Wizard für Steuer-Laien,
die sich in der Tab-Ansicht (Experten-Modus) überfordert fühlen. Nutzt
dieselben Kernfunktionen wie der Experten-Modus (render_dokumente_tab,
render_crypto_tab, berechne_veranlagung, build_summary, sowie die
core.fragebogen_ui-Bausteine) – nur mit wenigen Feldern gleichzeitig auf
dem Bildschirm und großen Ja/Nein-Fragen statt Fachformularen.

Deckt inzwischen (Ausbaustufe 8, "Schritt für Schritt, nicht nur die
Hauptpunkte") dieselben Themen wie der Experten-Modus ab: Fahrtkosten,
Homeoffice, Stammdaten, Verlustvorträge, Behinderung/Pflege/Unterhalt,
Riester – jeweils als eigener, fokussierter Schritt bzw. hinter einer
Ja/Nein-Weiche versteckt, damit wer nicht betroffen ist, einfach mit
"Nein" weiterklickt."""

import streamlit as st

from .checks import run_checks
from .crypto_ui import render_crypto_tab
from .dokumente_ui import render_dokumente_tab
from .elster_export import build_summary, export_json, render_elster_help
from .fragebogen_ui import (hat_behinderung_pflege_unterhalt,
                            hat_riester, hat_verlustvortrag,
                            render_behinderung_pflege_unterhalt,
                            render_fahrtkosten_homeoffice, render_riester,
                            render_stammdaten, render_verlustvortraege)
from .jahr_zuordnung import docs_im_jahr
from .veranlagung import berechne_veranlagung

_SCHRITTE = ["Start", "Belege", "Grunddaten", "Fahrtkosten & Homeoffice",
            "Kapitalerträge & Krypto", "Weitere Vorteile", "Stammdaten",
            "Ergebnis", "Fertig"]


def _fmt(v):
    return f"{v:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def _aktive(interview: dict) -> tuple:
    return ("P1", "P2") if interview.get("zusammenveranlagung", True) \
        else ("P1",)


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
        _schritt_grunddaten(interview)
    elif idx == 3:
        _schritt_fahrtkosten(cfg, interview, personen)
    elif idx == 4:
        _schritt_kapital_krypto(cfg, api_key, model, interview, personen)
    elif idx == 5:
        _schritt_weitere_vorteile(interview, personen)
    elif idx == 6:
        _schritt_stammdaten(interview, personen)
    elif idx == 7:
        _schritt_ergebnis(cfg, interview)
    else:
        _schritt_fertig(cfg, interview, erklaermodus)


def _schritt_start(api_key):
    st.title("👋 Willkommen bei deinem Steuer-Assistenten!")
    st.markdown(
        "Wir gehen das gemeinsam **Schritt für Schritt** durch:\n\n"
        "1. 📄 Du lädst deine Belege hoch (Fotos oder PDFs reichen).\n"
        "2. ❓ Ein paar Grunddaten (Kirche, Kinder, Bundeswehr …).\n"
        "3. 🚗 Fahrtkosten & Homeoffice.\n"
        "4. ₿ Kapitalerträge & Krypto.\n"
        "5. 🎁 Weitere Vorteile, falls relevant (Behinderung, Riester, "
        "Verlustvorträge …).\n"
        "6. 🪪 Stammdaten für ELSTER.\n"
        "7. 💶 Du siehst dein voraussichtliches Ergebnis.\n"
        "8. ✅ Du bekommst eine fertige Hilfe für ELSTER.\n\n"
        "Du brauchst kein Steuer-Wissen – wir erklären alles unterwegs, "
        "was nicht auf dich zutrifft, überspringst du einfach mit "
        "**Nein**, und du kannst jederzeit einen Schritt zurückgehen."
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


def _schritt_grunddaten(interview):
    st.title("❓ Schritt 2: Ein paar Grunddaten")
    st.markdown("Beantworte einfach mit **Ja** oder **Nein**.")

    c1, c2 = st.columns(2)
    with c1:
        interview["kirchensteuerpflichtig"] = st.radio(
            "⛪ Zahlst du Kirchensteuer?", ["Nein", "Ja"],
            index=1 if interview.get("kirchensteuerpflichtig") else 0,
            horizontal=True, key="wz_kirche") == "Ja"
        interview["kirchensteuerpflichtig_beantwortet"] = True
        interview["hat_bundeswehr"] = st.radio(
            "🎖️ Bekommst du Übergangsgebührnisse von der Bundeswehr?",
            ["Nein", "Ja"],
            index=1 if interview.get("hat_bundeswehr", True) else 0,
            horizontal=True, key="wz_bw") == "Ja"
    with c2:
        interview["hat_kinder"] = st.radio(
            "👶 Hast du Kinder?", ["Nein", "Ja"],
            index=1 if interview.get("hat_kinder") else 0,
            horizontal=True, key="wz_kinder") == "Ja"
        if interview["hat_kinder"]:
            interview["kinder_anzahl"] = st.number_input(
                "Wie viele Kinder (mit Kindergeld-Anspruch)?", 0, 15,
                int(interview.get("kinder_anzahl") or 0),
                key="wz_kinder_anzahl",
                help="Wirkt auf die zumutbare Belastung (§ 33 Abs. 3 EStG) "
                     "und die Riester-Kinderzulage.")
        interview["auslandsbezug"] = st.radio(
            "🌍 Wohnsitz oder Einkünfte im Ausland (z. B. Österreich)?",
            ["Nein", "Ja"], index=1 if interview.get("auslandsbezug") else 0,
            horizontal=True, key="wz_ausland") == "Ja"

    st.divider()
    _nav()


def _schritt_fahrtkosten(cfg, interview, personen):
    st.title("🚗 Schritt 3: Fahrtkosten & Homeoffice")
    st.markdown("Diese Angaben senken automatisch deine Steuer über die "
               "Werbungskosten – trag sie gerne ein, auch grob geschätzt.")
    render_fahrtkosten_homeoffice(interview, personen, _aktive(interview),
                                  key_prefix="wz_")
    st.caption(
        "💡 Das zählt automatisch nur, wenn es zusammen mit anderen "
        f"Werbungskosten über dem Pauschbetrag von "
        f"{cfg['arbeitnehmer_pauschbetrag']:,.0f} € liegt – das prüft "
        "das Tool für dich, du musst hier nichts vergleichen."
        .replace(",", "."))
    st.divider()
    _nav()


def _schritt_kapital_krypto(cfg, api_key, model, interview, personen):
    st.title("₿ Schritt 4: Kapitalerträge & Krypto")
    c1, c2 = st.columns(2)
    with c1:
        interview["hat_etf"] = st.radio(
            "📈 Hast du ETFs/Fonds im Depot?", ["Nein", "Ja"],
            index=1 if interview.get("hat_etf") else 0,
            horizontal=True, key="wz_etf") == "Ja"
        interview["guenstigerpruefung"] = st.checkbox(
            "Günstigerprüfung für Kapitalerträge beantragen",
            value=bool(interview.get("guenstigerpruefung", True)),
            key="wz_guenstiger",
            help="Kann nie schaden – das Finanzamt prüft automatisch, ob "
                 "dein persönlicher Steuersatz günstiger ist als die "
                 "pauschale Abgeltungsteuer (25 %).")
    with c2:
        interview["hat_krypto_verkauft"] = st.radio(
            f"₿ Hast du in {cfg['jahr']} Krypto verkauft oder getauscht?",
            ["Nein", "Ja"],
            index=1 if interview.get("hat_krypto_verkauft") else 0,
            horizontal=True, key="wz_krypto") == "Ja"

    if interview["hat_krypto_verkauft"]:
        with st.expander("🪙 Deine Krypto-Verkäufe eintragen", expanded=True):
            docs = docs_im_jahr(st.session_state.docs, cfg["jahr"])
            render_crypto_tab(cfg, api_key, model, interview, personen, docs)
    else:
        st.caption("Kein Problem – dann überspringen wir die Anlage SO "
                  "komplett.")

    st.divider()
    _nav()


def _schritt_weitere_vorteile(interview, personen):
    st.title("🎁 Schritt 5: Weitere Steuervorteile")
    st.markdown("Diese Punkte treffen nicht auf jeden zu – einfach mit "
               "**Nein** überspringen, wenn nicht relevant.")
    aktive = _aktive(interview)

    st.subheader("🏭 Betrieb / Nebengewerbe")
    hat_betrieb = any(interview.get(f"hat_betrieb_{p}") for p in aktive)
    betrieb_ja = st.radio(
        "Hast du Einnahmen aus einem Betrieb, Nebengewerbe, "
        "Photovoltaik/Energieverkauf oder freiberuflicher Tätigkeit?",
        ["Nein", "Ja"], index=1 if hat_betrieb else 0,
        horizontal=True, key="wz_betrieb") == "Ja"
    if betrieb_ja:
        cols = st.columns(len(aktive))
        for col, p in zip(cols, aktive):
            interview[f"hat_betrieb_{p}"] = col.checkbox(
                personen[p], value=bool(interview.get(f"hat_betrieb_{p}")),
                key=f"wz_hb_{p}")
        st.info("➡️ Für Betriebe gibt es einen eigenen, ausführlichen "
               "Bereich mit Einnahmen/Ausgaben/Abschreibungen – wechsle "
               "dafür oben in der Seitenleiste in den **🛠️ Experten-"
               "Modus** und öffne den Tab '🏭 3 · Betrieb'.")
    else:
        for p in aktive:
            interview[f"hat_betrieb_{p}"] = False

    st.divider()
    st.subheader("📉 Verlustvorträge")
    verlust_ja = st.radio(
        "Hast du Verlustvorträge aus Vorjahren (steht im Steuerbescheid, "
        "z. B. 'verbleibender Verlustvortrag')?",
        ["Nein", "Ja"], index=1 if hat_verlustvortrag(interview) else 0,
        horizontal=True, key="wz_verlust") == "Ja"
    if verlust_ja:
        render_verlustvortraege(interview, key_prefix="wz_")

    st.divider()
    st.subheader("🦽 Behinderung, Pflege & Unterhalt")
    beh_ja = st.radio(
        "Liegt bei dir/deinem Partner eine Behinderung vor, pflegst du "
        "einen Angehörigen oder zahlst du Unterhalt an eine bedürftige "
        "Person?",
        ["Nein", "Ja"],
        index=1 if hat_behinderung_pflege_unterhalt(interview) else 0,
        horizontal=True, key="wz_beh") == "Ja"
    if beh_ja:
        render_behinderung_pflege_unterhalt(interview, personen, aktive,
                                            key_prefix="wz_")

    st.divider()
    st.subheader("💰 Riester-Rente")
    riester_ja = st.radio(
        "Zahlst du in einen Riester-Vertrag ein?",
        ["Nein", "Ja"], index=1 if hat_riester(interview, aktive) else 0,
        horizontal=True, key="wz_riester") == "Ja"
    if riester_ja:
        render_riester(interview, personen, aktive, key_prefix="wz_")

    st.divider()
    _nav()


def _schritt_stammdaten(interview, personen):
    st.title("🪪 Schritt 6: Stammdaten für ELSTER")
    st.markdown("Diese Angaben brauchst du für den ELSTER-Hauptvordruck – "
               "ohne sie ist deine Eingabehilfe später unvollständig.")
    render_stammdaten(interview, personen, _aktive(interview),
                      key_prefix="wz_")
    st.divider()
    _nav()


def _schritt_ergebnis(cfg, interview):
    st.title("💶 Schritt 7: Dein voraussichtliches Ergebnis")
    docs = docs_im_jahr(st.session_state.docs, cfg["jahr"])
    v = berechne_veranlagung(docs, cfg, interview)

    if not v["hat_lsb"]:
        st.warning("Wir brauchen mindestens deine **Lohnsteuerbescheinigung**, "
                   "um ein Ergebnis zu schätzen. Geh zurück zu Schritt 1 "
                   "und lade sie hoch.")
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
            for w in v["warnhinweise"]:
                st.caption("⚠️ " + w)

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
