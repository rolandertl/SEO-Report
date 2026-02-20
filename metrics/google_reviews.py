from core.context import ReportContext
from services.google_places import fetch_rating_and_review_count


def _kpi_cards_html(items):
    cards = ""
    for label, value in items:
        cards += f"""
<div style="flex:1; border:1px solid rgba(0,0,0,0.08); border-radius:12px; overflow:hidden;">
  <div style="background:rgba(0,0,0,0.03); padding:10px 14px; font-weight:700;">{label}</div>
  <div style="padding:18px 14px; font-size:30px; font-weight:800; text-align:center;">{value}</div>
</div>
"""
    return f"""<div style="display:flex; gap:14px; margin-top:14px;">{cards}</div>"""


def _stars(n: float) -> str:
    return f"{n:.1f} / 5"


def build_google_reviews_block(
    ctx: ReportContext,
    uberall_input: dict,
    google_places_api_key: str = "",
) -> dict:
    name = (uberall_input or {}).get("name", "").strip()
    street = (uberall_input or {}).get("street", "").strip()
    postal_code = (uberall_input or {}).get("postal_code", "").strip()

    stats = None
    reason = ""
    missing_required = (not name) or (not street)

    if not google_places_api_key:
        reason = "Google Places API-Key fehlt"
    elif missing_required:
        reason = "Werte nur verfügbar, wenn Unternehmensname und Straße + Hausnummer ausgefüllt sind."
    else:
        try:
            stats = fetch_rating_and_review_count(
                google_places_api_key,
                name=name,
                street=street,
                postal_code=postal_code,
            )
        except Exception as e:
            stats = None
            reason = f"Google Places Anfrage fehlgeschlagen: {e}"

    if stats is None:
        if not reason:
            reason = "Kein Google Places Treffer für die Suchdaten gefunden"
        rating_text = "nicht verfügbar"
        count_text = "nicht verfügbar"
        source_line = f"Quelle: {reason}"
    else:
        rating, count = stats
        rating_text = _stars(rating)
        count_text = str(count)
        source_line = "Quelle: Google Places API (öffentlich)"

    pre_html = (
        "<div style='font-size:14px; line-height:1.6; margin-top:6px;'>"
        "Google Bewertungen zeigt die öffentlich sichtbaren Google-Signale zu Reputation und Kundenfeedback."
        "</div>"
        + _kpi_cards_html(
            [
                ("Ø Rating", rating_text),
                ("Anzahl Reviews", count_text),
            ]
        )
        + f"<div style='margin-top:8px; color:#666; font-size:12px;'>{source_line}</div>"
    )

    return {
        "id": "google_reviews",
        "title": "Google Bewertungen",
        "accent_token": "COLOR_2",
        "pre_html": pre_html,
        "comment_title": "Einordnung",
        "comment": "Dieser Block dient als separater Vergleich der Google-only Bewertungsdaten.",
    }
