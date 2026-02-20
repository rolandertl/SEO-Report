# ==============================
# CI COLOR SYSTEM (AGENCY LEVEL)
# ==============================

# Single switch for the whole project:
# - "live": all integrations run live
# - "dev": all integrations run with fallback/demo behavior where implemented
REPORT_MODE = "live"

_IS_LIVE = REPORT_MODE.strip().lower() == "live"
DEV_MODE = not _IS_LIVE

# Derived integration modes (kept for backward compatibility in modules)
UBERALL_LIVE_MODE = _IS_LIVE
GOOGLE_PLACES_LIVE_MODE = _IS_LIVE
OPENAI_LIVE_MODE = _IS_LIVE
SISTRIX_VISIBILITY_LIVE = _IS_LIVE
SISTRIX_TOP_URLS_LIVE = _IS_LIVE
SISTRIX_KEYWORD_PROFILE_LIVE = _IS_LIVE
SISTRIX_RANKING_BLOCKS_LIVE = _IS_LIVE
SISTRIX_BACKLINKS_LIVE = _IS_LIVE

CI_COLORS = {
    "COLOR_1": "#EE316B",  # Pink (Primary)
    "COLOR_2": "#00B9E4",  # Blau
    "COLOR_3": "#9ADE29",  # Grün
    "COLOR_4": "#9F5CEA",  # Violett
    "COLOR_5": "#EEDC24",  # Gelb
    "COLOR_6": "#404041",  # Grau (Text / Neutral)
}

BRAND = {
    "primary": "COLOR_1",
    "accent": "COLOR_2",
    "success": "COLOR_3",
    "highlight": "COLOR_4",
    "warning": "COLOR_5",
    "text": "COLOR_6",
}

REPORT_META = {
    "title": "SEO-Report",
    "format": "A4",
    "orientation": "portrait",
}

CHART_PALETTES = {
    "top_urls_5": ["COLOR_1", "COLOR_2", "COLOR_3", "COLOR_5", "COLOR_4"],  # Pink, Blau, Grün, Gelb, Violett
}
