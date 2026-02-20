from core.config import UBERALL_LIVE_MODE
from core.context import ReportContext
from services.uberall import get as uberall_get



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


def _find_first_list(obj):
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for key in ("locations", "items", "objects", "results", "data", "response", "answer"):
            v = obj.get(key)
            if isinstance(v, list):
                return v
            if isinstance(v, dict):
                nested = _find_first_list(v)
                if nested:
                    return nested
    return []


def _extract_location(raw: dict) -> dict | None:
    if not isinstance(raw, dict):
        return None

    if raw.get("id") and any(k in raw for k in ("name", "listings", "address", "streetAndNo")):
        return raw

    for key in ("location", "data", "response", "answer", "result"):
        child = raw.get(key)
        if isinstance(child, dict):
            candidate = _extract_location(child)
            if candidate:
                return candidate

    rows = _find_first_list(raw)
    for item in rows:
        if isinstance(item, dict) and item.get("id"):
            return item

    return None


def _resolve_location(uberall_input: dict, uberall_api_key: str) -> tuple[dict | None, str]:
    location_id = (uberall_input or {}).get("location_id", "").strip()
    name = (uberall_input or {}).get("name", "").strip()
    street = (uberall_input or {}).get("street", "").strip()
    postal_code = (uberall_input or {}).get("postal_code", "").strip()

    if location_id:
        data = uberall_get(f"locations/{location_id}", api_key=uberall_api_key)
        location = _extract_location(data)
        return location, f"Firmendaten Manager Location-ID: {location_id}"

    # Fallback über Locations-Suche (best effort)
    params = {}
    if name:
        params["name"] = name
    if postal_code:
        params["zip"] = postal_code

    data = uberall_get("locations", api_key=uberall_api_key, params=params)
    rows = _find_first_list(data)

    if street:
        street_l = street.lower()
        for row in rows:
            if not isinstance(row, dict):
                continue
            hay = " ".join(
                [
                    str(row.get("streetAndNo", "")),
                    str(row.get("street", "")),
                    str(row.get("addressLine1", "")),
                ]
            ).lower()
            if street_l and street_l.split(" ")[0] in hay:
                return row, "Firmendaten Manager Presence-Check (Name/Adresse)"

    if rows and isinstance(rows[0], dict):
        return rows[0], "Firmendaten Manager Presence-Check (Name/Adresse)"

    return None, "Firmendaten Manager Presence-Check"


def _extract_listings(location: dict) -> list[dict]:
    for key in ("listings", "listingStatuses", "directories"):
        val = location.get(key)
        if isinstance(val, list):
            return [x for x in val if isinstance(x, dict)]
    return []


def _platform_name(item: dict) -> str:
    for key in ("directoryName", "directoryType", "publisher", "name", "type"):
        val = item.get(key)
        if val:
            return str(val)
    return "Unbekannte Plattform"


def _status_name(item: dict) -> str:
    for key in ("status", "syncStatus", "claimStatus", "state"):
        val = item.get(key)
        if val:
            return str(val)
    return "UNKNOWN"


def build_uberall_presence_block(ctx: ReportContext, uberall_input: dict, uberall_api_key: str = "") -> dict:
    """
    Uberall Local Presence.
    SISTRIX/OpenAI bleiben im DEV_MODE; Uberall kann separat live laufen.
    """
    location_id = (uberall_input or {}).get("location_id", "").strip()
    name = (uberall_input or {}).get("name", "").strip()
    street = (uberall_input or {}).get("street", "").strip()
    postal_code = (uberall_input or {}).get("postal_code", "").strip()

    if not location_id:
        cards = [
            ("Presence Score", "nicht verfügbar"),
            ("Sichtbarkeit", "nicht verfügbar"),
        ]

        pre_html = (
            "<div style='font-size:14px; line-height:1.6; margin-top:6px;'>"
            "Dieser Abschnitt zeigt, wie konsistent und vollständig Ihre Unternehmensdaten "
            "in zentralen Verzeichnissen gepflegt sind."
            "</div>"
            + _kpi_cards_html(cards)
            + "<div style='margin-top:8px; color:#666; font-size:12px;'>Quelle: Kein Firmendaten Manager gefunden</div>"
        )

        return {
            "id": "uberall_presence",
            "title": "Firmendaten Manager – Online Presence",
            "accent_token": "COLOR_5",
            "pre_html": pre_html,
            "comment_title": "Einordnung",
            "comment": "Diese Auswertung setzt den Einsatz des EDELWEISS Digital Firmendaten Managers voraus.",
        }

    if UBERALL_LIVE_MODE and not uberall_api_key:
        return {
            "id": "uberall_presence",
            "title": "Firmendaten Manager – Online Presence",
            "accent_token": "COLOR_5",
            "error": "Firmendaten Manager Live ist aktiv, aber UBERALL_API_KEY fehlt in den Secrets.",
        }

    use_live = UBERALL_LIVE_MODE and bool(uberall_api_key)

    if not use_live:
        cards = [
            ("Presence Score", "82/100"),
            ("Sichtbarkeit", "+12%"),
        ]

        info_line = ""
        if location_id:
            info_line = f"<div style='margin-top:8px; color:#666; font-size:12px;'>Quelle: Firmendaten Manager Location-ID: <strong>{location_id}</strong></div>"
        else:
            info_line = (
                "<div style='margin-top:8px; color:#666; font-size:12px;'>Quelle: Firmendaten Manager Presence-Check (Name/Adresse)</div>"
            )

        pre_html = (
            "<div style='font-size:14px; line-height:1.6; margin-top:6px;'>"
            "Dieser Abschnitt zeigt, wie konsistent und vollständig Ihre Unternehmensdaten "
            "über wichtige Verzeichnisse und Plattformen hinweg gepflegt sind."
            "</div>"
            + _kpi_cards_html(cards)
            + info_line
        )

        comment = (
            "Die lokale Online-Präsenz wirkt insgesamt sehr solide. Besonders positiv ist, dass die wichtigsten Profile bereits "
            "gut abgedeckt sind – das stärkt die lokale Auffindbarkeit. Die wenigen offenen Punkte sind typische Details, "
            "die wir gezielt bereinigen, um die Konsistenz weiter zu verbessern."
        )

        return {
            "id": "uberall_presence",
            "title": "Firmendaten Manager – Online Presence",
            "accent_token": "COLOR_5",
            "pre_html": pre_html,
            "comment_title": "Einordnung",
            "comment": comment,
        }

    try:
        location, source_label = _resolve_location(uberall_input, uberall_api_key)
        if not location:
            return {
                "id": "uberall_presence",
                "title": "Firmendaten Manager – Online Presence",
                "accent_token": "COLOR_5",
                "error": "Firmendaten Manager: Standort konnte nicht gefunden werden (prüfe Location-ID).",
            }

        listings = _extract_listings(location)
        total = len(listings)

        active_states = {"LIVE", "ACTIVE", "PUBLISHED", "SYNCED", "MATCHED"}
        good = 0

        for item in listings:
            status = _status_name(item).upper()
            if status in active_states:
                good += 1
        profile_score = int(
            float(
                location.get("profileCompleteness")
                or location.get("listingQualityScore")
                or (100 * good / total if total else 0)
            )
        )
        visibility = int(round(100 * good / total, 0)) if total else 0

        cards = [
            ("Presence Score", f"{profile_score}/100"),
            ("Sichtbarkeit", f"{visibility}%"),
        ]

        pre_html = (
            "<div style='font-size:14px; line-height:1.6; margin-top:6px;'>"
            "Dieser Abschnitt zeigt, wie konsistent und vollständig Ihre Unternehmensdaten "
            "über wichtige Verzeichnisse und Plattformen hinweg gepflegt sind."
            "</div>"
            + _kpi_cards_html(cards)
            + f"<div style='margin-top:8px; color:#666; font-size:12px;'>Quelle: {source_label}</div>"
        )

        comment = (
            "Die Presence-Werte basieren auf den aktuellen Firmendaten Manager Daten. "
            "Besonders wichtig sind konsistente aktive Listings in den relevanten Verzeichnissen. "
            "Offene Status prüfen wir gezielt, um die lokale Auffindbarkeit weiter zu stabilisieren."
        )

        return {
            "id": "uberall_presence",
            "title": "Firmendaten Manager – Online Presence",
            "accent_token": "COLOR_5",
            "pre_html": pre_html,
            "comment_title": "Einordnung",
            "comment": comment,
        }
    except Exception as e:
        return {
            "id": "uberall_presence",
            "title": "Firmendaten Manager – Online Presence",
            "accent_token": "COLOR_5",
            "error": f"Firmendaten Manager Live-Fehler: {e}",
        }
