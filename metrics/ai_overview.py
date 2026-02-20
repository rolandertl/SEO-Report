import requests
import re
from html import escape
from core.context import ReportContext
from core.config import OPENAI_LIVE_MODE


def _build_intro_html(domain: str) -> str:
    return f"""
<div style='font-size:14px; line-height:1.65; margin-top:6px;'>
  Um zu analysieren, wie präsent und greifbar Ihre Marke im digitalen Raum ist, haben wir eine KI-gestützte Auswertung durchgeführt.
  Dabei haben wir der KI gezielt generische Fragen zu Ihrem Unternehmen gestellt – basierend auf Ihrer Domain.<br><br>
  Ziel dieser Analyse ist es, herauszufinden:<br>
  • Welche Informationen öffentlich verfügbar sind<br>
  • Wie Ihr Unternehmen beschrieben und eingeordnet wird<br>
  • Wie Ihre Marke aus externer Perspektive wahrgenommen wird<br>
  • Wie stark Ihre digitale Präsenz im Vergleich zu ähnlichen Unternehmen wirkt<br><br>
  Die folgenden Fragen wurden gestellt:<br>
  „Was ist über das Unternehmen mit der Domain <strong>{domain}</strong> allgemein bekannt?
  Bitte beschreibe kurz, was dieses Unternehmen laut öffentlich verfügbaren Informationen anbietet.“<br>
  „Wie wird das Unternehmen mit der Domain <strong>{domain}</strong> typischerweise wahrgenommen
  (z. B. Positionierung, Zielgruppe, Spezialisierung), sofern Informationen verfügbar sind?“<br>
  „Wie ist der allgemeine Ruf des Unternehmens mit der Domain <strong>{domain}</strong>, basierend auf öffentlich verfügbaren Informationen?
  Falls keine belastbaren Informationen vorliegen, bitte entsprechend vermerken.“<br><br>
  Die anschließenden Antworten geben einen Überblick darüber, was eine KI – stellvertretend für viele moderne Such- und Assistenzsysteme –
  über Ihr Unternehmen weiß.
</div>
"""


def _build_prompt(domain: str) -> str:
    return (
        f"Analysiere das Unternehmen mit der Domain {domain}.\n"
        "Verwende ausschließlich öffentlich bekannte Informationen.\n"
        "Wenn keine ausreichenden Informationen verfügbar sind, weise ausdrücklich darauf hin.\n"
        "Wichtig: Formuliere kurz und kompakt. Maximal 3 kurze Bulletpoints pro Abschnitt.\n"
        "Gesamtlänge: maximal 120 Wörter.\n"
        "Keine langen Einleitungen, keine Wiederholungen, keine methodischen Erklärungen.\n"
        "Gib die Antwort strukturiert in folgenden Punkten aus:\n"
        "1. Unternehmensbeschreibung\n"
        "2. Wahrgenommene Positionierung\n"
        "3. Reputation / Ruf"
    )


def _call_openai_once(api_key: str, domain: str) -> str:
    prompt = _build_prompt(domain)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    # 1) Primär: Responses API mit Web-Search Tool (Live-Internet).
    #    Genau ein API-Call für die gesamte KI-Overview.
    try:
        r = requests.post(
            "https://api.openai.com/v1/responses",
            headers=headers,
            json={
                "model": "gpt-4.1",
                "tools": [{"type": "web_search_preview"}],
                "input": prompt,
                "temperature": 0.2,
            },
            timeout=90,
        )
        if r.status_code < 400:
            data = r.json()
            text = data.get("output_text")
            if isinstance(text, str) and text.strip():
                return text.strip()

            # Robuster Fallback, falls output_text nicht direkt gesetzt ist.
            chunks = []
            for item in data.get("output", []) or []:
                for c in item.get("content", []) or []:
                    t = c.get("text")
                    if t:
                        chunks.append(str(t))
            if chunks:
                return "\n".join(chunks).strip()

        # Wenn Responses/Web-Search nicht verfügbar ist, gehen wir auf Chat-Fallback.
    except Exception:
        pass

    # 2) Fallback: Chat Completions ohne Webzugriff
    #    (liefert zumindest strukturierten Text, falls Web-Tool im Account nicht freigeschaltet ist).
    r = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers=headers,
        json={
            "model": "gpt-5-mini",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
        },
        timeout=60,
    )
    r.raise_for_status()
    data = r.json()
    return (
        data.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
        .strip()
    )


def _format_ai_answer_html(answer: str) -> str:
    raw_lines = [ln.strip() for ln in (answer or "").splitlines()]
    lines = [ln for ln in raw_lines if ln]
    if not lines:
        return "<div style='font-size:14px; line-height:1.5;'>Keine Antwort erhalten.</div>"

    # Fall "2." + nächste Zeile als Titel in eine Zeile zusammenziehen.
    normalized = []
    i = 0
    while i < len(lines):
        cur = lines[i]
        if re.match(r"^\d+\.$", cur) and i + 1 < len(lines):
            normalized.append(f"{cur} {lines[i + 1]}")
            i += 2
            continue
        normalized.append(cur)
        i += 1

    sections: list[tuple[str, list[str]]] = []
    current_title = ""
    current_items: list[str] = []

    def flush():
        nonlocal current_title, current_items
        if current_title or current_items:
            sections.append((current_title or "Antwort", current_items[:]))
        current_title = ""
        current_items = []

    for ln in normalized:
        m = re.match(r"^(\d+)\.\s*(.+)$", ln)
        if m:
            flush()
            title = m.group(2).strip().strip("*")
            current_title = f"{m.group(1)}. {title}"
            continue

        bullet = re.sub(r"^[\-\*\u2022o]+\s*", "", ln).strip()
        current_items.append(bullet if bullet else ln)

    flush()

    html_parts = ["<div style='font-size:14px; line-height:1.45;'>"]
    for idx, (title, items) in enumerate(sections):
        mt = "0" if idx == 0 else "8px"
        html_parts.append(f"<div style='font-weight:700; margin:{mt} 0 4px 0;'>{escape(title)}</div>")
        if items:
            html_parts.append("<ul style='margin:0 0 2px 18px; padding:0;'>")
            for it in items:
                html_parts.append(f"<li style='margin:2px 0;'>{escape(it)}</li>")
            html_parts.append("</ul>")
    html_parts.append("</div>")
    return "".join(html_parts)


def build_ai_overview_block(ctx: ReportContext, openai_api_key: str) -> dict:
    domain = ctx.domain
    intro_html = _build_intro_html(domain)

    if not OPENAI_LIVE_MODE:
        return {
            "id": "ai_overview",
            "title": "KI-Overview – Wie sichtbar ist Ihre Marke aus Sicht einer KI?",
            "accent_token": "COLOR_4",
            "pre_html": (
                intro_html
                + "<div style='margin-top:12px; color:#666;'>"
                "KI-Overview ist im Dev-Modus deaktiviert. Für Live-Daten bitte REPORT_MODE auf \"live\" setzen."
                "</div>"
            ),
        }

    if not openai_api_key:
        return {
            "id": "ai_overview",
            "title": "KI-Overview – Wie sichtbar ist Ihre Marke aus Sicht einer KI?",
            "accent_token": "COLOR_4",
            "error": "OpenAI API-Key fehlt für die KI-Overview.",
        }

    try:
        answer = _call_openai_once(openai_api_key, domain)
    except Exception as e:
        return {
            "id": "ai_overview",
            "title": "KI-Overview – Wie sichtbar ist Ihre Marke aus Sicht einer KI?",
            "accent_token": "COLOR_4",
            "error": f"OpenAI-Fehler bei KI-Overview: {e}",
        }

    response_html = (
        "<div style='margin-top:14px; border:1px solid rgba(0,0,0,0.10); border-radius:12px; padding:14px 16px; "
        "background:rgba(0,0,0,0.02);'>"
        "<div style='font-weight:700; margin-bottom:8px;'>KI-Antwort</div>"
        + _format_ai_answer_html(answer)
        + "</div>"
    )

    outro_html = (
        "<div style='font-size:14px; line-height:1.65; margin-top:12px;'>"
        "Diese KI-Sichtbarkeit ist ein zunehmend relevanter Faktor, da immer mehr Nutzer Informationen "
        "nicht nur über klassische Suchmaschinen, sondern über KI-Systeme abrufen.<br><br>"
        "Die Ergebnisse helfen uns zu verstehen,<br>"
        "• ob Ihre Marke klar positioniert ist,<br>"
        "• ob ausreichend öffentlich zugängliche Informationen vorhanden sind,<br>"
        "• und wo Potenzial für stärkere digitale Präsenz besteht."
        "</div>"
    )

    return {
        "id": "ai_overview",
        "title": "KI-Overview – Wie sichtbar ist Ihre Marke aus Sicht einer KI?",
        "accent_token": "COLOR_4",
        "pre_html": intro_html + response_html + outro_html,
    }
