import math
import pandas as pd
from urllib.parse import urlparse

from core.context import ReportContext
from core.config import UBERALL_LIVE_MODE, GOOGLE_PLACES_LIVE_MODE, CI_COLORS
from services.google_places import fetch_rating_and_review_count
from services.insites import get_report as insites_get_report
from services.uberall import get as uberall_get
from metrics.uberall_insights import _fetch_insights, _fetch_customer_feedback, _fetch_profile_completeness
from components.charts import area_chart, table_chart


def _fmt_int_eu(v: int) -> str:
    return f"{int(v):,}".replace(",", ".")


def _kpi_cards_html(items):
    cards = ""
    for label, value in items:
        cards += f"""
<div style="flex:1; border:1px solid rgba(0,0,0,0.08); border-radius:12px; overflow:hidden;">
  <div style="background:rgba(0,0,0,0.03); padding:10px 14px; font-weight:700;">{label}</div>
  <div style="padding:18px 14px; font-size:30px; font-weight:800; text-align:center;">{value}</div>
</div>
"""
    return f"""<div style="display:flex; gap:14px; margin-top:10px;">{cards}</div>"""


def _norm_domain(value: str | None) -> str:
    s = (value or "").strip().lower()
    if not s:
        return ""
    if "://" not in s:
        s = "https://" + s
    p = urlparse(s)
    host = (p.netloc or p.path).split("/")[0].strip().lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _extract_locations(payload) -> list[dict]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("locations", "items", "objects", "results", "data"):
        v = payload.get(key)
        if isinstance(v, list):
            return [x for x in v if isinstance(x, dict)]
    for key in ("response", "result", "answer"):
        v = payload.get(key)
        if isinstance(v, dict):
            out = _extract_locations(v)
            if out:
                return out
    return []


def _extract_location_one(payload) -> dict | None:
    if isinstance(payload, dict):
        if payload.get("id"):
            return payload
        for key in ("location", "data", "response", "result", "answer"):
            v = payload.get(key)
            if isinstance(v, dict):
                hit = _extract_location_one(v)
                if hit:
                    return hit
            elif isinstance(v, list):
                for item in v:
                    if isinstance(item, dict) and item.get("id"):
                        return item
    return None


def _find_location_by_domain(domain: str, uberall_api_key: str, max_per_page: int = 500) -> dict | None:
    target = _norm_domain(domain)
    if not target:
        return None

    offset = 0
    while True:
        params = [
            ("fieldMask", "id"),
            ("fieldMask", "name"),
            ("fieldMask", "website"),
            ("fieldMask", "profileCompleteness"),
            ("fieldMask", "listingQualityScore"),
            ("max", str(max_per_page)),
            ("offset", str(offset)),
        ]
        data = uberall_get("locations", api_key=uberall_api_key, params=params)
        rows = _extract_locations(data)
        if not rows:
            break

        for row in rows:
            website = row.get("website")
            if _norm_domain(website) == target:
                return row

        if len(rows) < max_per_page:
            break
        offset += max_per_page

    return None


def _gauge_html(percent: int, directories_found: int | None = None, directories_total: int = 36) -> str:
    pct = max(0, min(100, int(percent)))
    theta_deg = 180 - (pct * 1.8)
    theta = math.radians(theta_deg)

    cx = 120
    cy = 120
    r = 96
    needle_len = 66
    nx = cx + (math.cos(theta) * needle_len)
    ny = cy - (math.sin(theta) * needle_len)

    def pt(deg: float) -> tuple[float, float]:
        rad = math.radians(deg)
        return (cx + (math.cos(rad) * r), cy - (math.sin(rad) * r))

    def arc_path(start_deg: float, end_deg: float) -> str:
        x1, y1 = pt(start_deg)
        x2, y2 = pt(end_deg)
        return f"M {x1:.2f} {y1:.2f} A {r} {r} 0 0 1 {x2:.2f} {y2:.2f}"

    base_arc = arc_path(180, 0)
    segment_count = 6
    gap_deg = 2.6
    seg_span = (180.0 - (gap_deg * (segment_count - 1))) / segment_count
    seg_colors = ["#FF4D5A", "#FF5A49", "#FF7A2F", "#F2AD2E", "#A8CE16", "#87C30A"]
    seg_paths = []
    cur_start = 180.0
    for i in range(segment_count):
        cur_end = cur_start - seg_span
        seg_paths.append((arc_path(cur_start, cur_end), seg_colors[i]))
        cur_start = cur_end - gap_deg

    seg_svg = "".join(
        f"<path d='{p}' stroke='{c}' stroke-width='16' fill='none' stroke-linecap='round'/>"
        for p, c in seg_paths
    )
    if directories_found is not None:
        directories_value = (
            "<div style='margin-top:10px; font-size:44px; font-weight:800; line-height:1;'>"
            f"{_fmt_int_eu(directories_found)}"
            f"<span style='font-size:26px; font-weight:700; color:#666;'> / {_fmt_int_eu(directories_total)}</span>"
            "</div>"
            "<div style='margin-top:8px; color:#666;'>konsistente Listings gefunden</div>"
        )
    else:
        directories_value = "<div style='margin-top:10px; color:#666;'>nicht verfügbar</div>"

    heading_style = "font-size:28px; font-weight:700; margin:0 0 12px 0; line-height:1.2;"

    return (
        "<div style='margin-top:10px; display:grid; grid-template-columns:1fr 1fr 1fr; gap:14px;'>"
        "<div style='border:1px solid rgba(0,0,0,0.08); border-radius:12px; padding:14px;'>"
        f"<div style='{heading_style}'>Profilvollständigkeit</div>"
        "<div style='display:flex; align-items:center; gap:16px;'>"
        "<div style='width:250px; max-width:100%;'>"
        "<svg viewBox='0 0 240 140' style='width:100%; height:auto; display:block;'>"
        f"<path d='{base_arc}' stroke='#E9EEF5' stroke-width='20' fill='none' stroke-linecap='round'/>"
        f"{seg_svg}"
        "<g stroke='#C8CED8' stroke-width='2.2'>"
        "<line x1='24' y1='120' x2='34' y2='120' />"
        "<line x1='120' y1='24' x2='120' y2='34' />"
        "<line x1='216' y1='120' x2='206' y2='120' />"
        "</g>"
        f"<line x1='{cx}' y1='{cy}' x2='{nx:.2f}' y2='{ny:.2f}' stroke='#31343A' stroke-width='4.5' stroke-linecap='round' />"
        "<circle cx='120' cy='120' r='8' fill='#FFFFFF' stroke='#31343A' stroke-width='2.5'/>"
        "</svg>"
        "</div>"
        "<div>"
        f"<div style='font-size:52px; font-weight:800; line-height:1;'>{pct}%</div>"
        "<div style='color:#666; margin-top:6px;'>Vollständigkeit des Profils</div>"
        "</div>"
        "</div>"
        "</div>"
        "<div style='border:1px solid rgba(0,0,0,0.08); border-radius:12px; padding:14px;'>"
        f"<div style='{heading_style}'>Lokale Verzeichnisse</div>"
        f"{directories_value}"
        "</div>"
        "<div style='border:1px solid rgba(0,0,0,0.08); border-radius:12px; padding:14px;'></div>"
        "</div>"
    )


def _star_rating_html(rating: float, review_count: int) -> str:
    r = max(0.0, min(5.0, float(rating)))
    fill_pct = (r / 5.0) * 100.0
    return f"""
<div style="border:1px solid rgba(0,0,0,0.08); border-radius:12px; padding:14px;">
  <div style="font-weight:700; margin-bottom:8px;">Google Bewertungen</div>
  <div style="font-size:46px; font-weight:800; line-height:1;">{r:.1f}</div>
  <div style="position:relative; display:inline-block; font-size:32px; line-height:1; margin-top:6px;">
    <span style="color:#D4D8E0;">★★★★★</span>
    <span style="
      position:absolute; left:0; top:0; width:{fill_pct:.1f}%; overflow:hidden; white-space:nowrap; color:#F5B301;
    ">★★★★★</span>
  </div>
  <div style="margin-top:8px; color:#666;">{_fmt_int_eu(review_count)} Bewertungen</div>
</div>
"""


def _response_rate_html(percent: int | None) -> str:
    pct = 0 if percent is None else max(0, min(100, int(percent)))
    label = "nicht verfügbar" if percent is None else f"{pct}%"
    desc = "Wert aktuell nicht im API-Response enthalten." if percent is None else "Antwortrate"
    return f"""
<div style="border:1px solid rgba(0,0,0,0.08); border-radius:12px; padding:14px;">
  <div style="font-weight:700; margin-bottom:8px;">Antwortrate auf Bewertungen</div>
  <div style="display:flex; align-items:center; gap:18px;">
    <div style="
      width:120px; height:120px; border-radius:50%;
      background:conic-gradient({CI_COLORS['COLOR_4']} 0 {pct*3.6}deg, #ECEAF7 {pct*3.6}deg 360deg);
      display:grid; place-items:center;
    ">
      <div style="width:88px; height:88px; border-radius:50%; background:white; display:grid; place-items:center; font-weight:800; font-size:22px;">
        {label}
      </div>
    </div>
    <div style="color:#666;">{desc}</div>
  </div>
</div>
"""


def _status_chip(ok: bool) -> str:
    bg = "#2DBE8D" if ok else "#F04E6E"
    label = "✓" if ok else "✕"
    return (
        f"<span style='display:inline-grid; place-items:center; width:24px; height:24px; "
        f"border-radius:999px; background:{bg}; color:white; font-size:15px; font-weight:800;'>{label}</span>"
    )


def _mobile_row(title: str, description: str, ok: bool) -> str:
    return (
        "<div style='display:flex; gap:12px; align-items:flex-start; padding:10px 0; border-bottom:1px solid rgba(0,0,0,0.06);'>"
        f"{_status_chip(ok)}"
        "<div>"
        f"<div style='font-size:20px; font-weight:700; line-height:1.2;'>{title}</div>"
        f"<div style='margin-top:4px; color:#555; line-height:1.5;'>{description}</div>"
        "</div>"
        "</div>"
    )


def _mobile_audit_html(mobile_data: dict | None) -> str:
    m = mobile_data or {}
    has_horizontal_scroll = bool(m.get("has_horizontal_scroll"))
    has_small_text = bool(m.get("has_small_text"))
    has_small_links = bool(m.get("has_small_links"))
    has_viewport = bool(m.get("has_viewport_optimised_for_mobile"))
    screenshot_url = str(m.get("mobile_screenshot_url") or "").strip()

    phone_bg = "https://audit.edelweiss-digital.at/images/insites-brand/mobile-background.svg"
    screenshot_html = (
        f"<img src='{screenshot_url}' alt='Mobil-Screenshot' "
        "style='width:206px; height:364px; border-radius:18px; display:block;'/>"
        if screenshot_url
        else (
            "<div style='width:206px; height:364px; border-radius:18px; background:rgba(0,0,0,0.06); "
            "display:grid; place-items:center; color:#666; text-align:center; padding:8px;'>Kein Screenshot verfügbar</div>"
        )
    )

    checks_html = (
        _mobile_row(
            "Passt zur Bildschirmweite",
            "Eine mobile Website sollte frei von horizontalem Scrollen sein, um die Nutzer nicht zu verwirren.",
            not has_horizontal_scroll,
        )
        + _mobile_row(
            "Text auf dem Smartphone lesbar",
            "Der Text sollte groß genug sein, um auf einem Handy gelesen zu werden, ohne hineinzoomen zu müssen.",
            not has_small_text,
        )
        + _mobile_row(
            "Links zum Antippen groß genug",
            "Links auf einer Website sollten groß genug sein, um sie auf einem typischen mobilen Bildschirm antippen zu können.",
            not has_small_links,
        )
        + _mobile_row(
            "Viewport ist festgelegt",
            "Durch Einstellen des Viewports wird die Website in einer geeigneten Größe geladen.",
            has_viewport,
        )
    )

    return (
        "<div style='margin-top:22px;'>"
        "<div style='font-size:30px; font-weight:700; margin:0 0 8px 0; padding-bottom:6px; border-bottom:2px solid rgba(238,49,107,1);'>Mobile Darstellung</div>"
        "<div style='font-size:14px; line-height:1.6; margin-top:8px;'>"
        "Die mobile Nutzererfahrung ist ein zentraler Qualitätsfaktor. Diese Auswertung zeigt, "
        "wie gut Ihre Website auf Smartphones technisch und visuell funktioniert."
        "</div>"
        "<div style='display:grid; grid-template-columns:260px 1fr; gap:26px; align-items:start; margin-top:14px;'>"
        f"<div style=\"margin:0 auto; width:220px; padding:28px 0; display:flex; align-items:center; justify-content:center; background:url('{phone_bg}') center center / contain no-repeat;\">{screenshot_html}</div>"
        f"<div>{checks_html}</div>"
        "</div>"
        "</div>"
    )


def _status_text_color(level: str) -> str:
    if level == "ok":
        return "#2DBE8D"
    if level == "warn":
        return "#F5A623"
    return "#F04E6E"


def _status_symbol(level: str) -> str:
    if level == "ok":
        return "✓"
    if level == "warn":
        return "!"
    return "✕"


def _status_badge(level: str) -> str:
    color = _status_text_color(level)
    return (
        f"<span style='display:inline-grid; place-items:center; width:22px; height:22px; "
        f"border-radius:999px; background:{color}; color:white; font-size:14px; font-weight:800;'>{_status_symbol(level)}</span>"
    )


def _quick_check_row(label: str, value_text: str, level: str) -> str:
    color = _status_text_color(level)
    return (
        "<div style='display:flex; align-items:center; justify-content:space-between; gap:12px; "
        "padding:12px 0; border-bottom:1px solid rgba(0,0,0,0.06);'>"
        "<div style='display:flex; align-items:center; gap:10px;'>"
        f"{_status_badge(level)}"
        f"<span style='font-size:17px; font-weight:700; color:#2F2F35;'>{label}</span>"
        "</div>"
        f"<div style='font-size:17px; font-weight:700; color:{color};'>{value_text}</div>"
        "</div>"
    )


def _technical_quick_check_html(insites_report: dict | None) -> str:
    r = insites_report or {}

    # Broken links
    bl = (r.get("broken_links") or {}).get("links_broken_count")
    try:
        broken_count = int(float(bl))
    except Exception:
        broken_count = None
    if broken_count is None:
        broken_value, broken_level = "nicht gefunden", "bad"
    elif broken_count == 0:
        broken_value, broken_level = "0", "ok"
    else:
        broken_value, broken_level = str(broken_count), "bad"

    # SSL
    ssl_obj = r.get("ssl") or {}
    ssl_has = ssl_obj.get("has_ssl")
    if ssl_has is None:
        ssl_has = (r.get("gdpr") or {}).get("ssl_detected")
    ssl_ok = bool(ssl_has is True)
    ssl_value = "Vorhanden" if ssl_ok else "nicht gefunden"
    ssl_level = "ok" if ssl_ok else "bad"

    # Sitemap
    sm = r.get("sitemap") or {}
    has_sitemap = sm.get("has_sitemap")
    sitemap_issues = sm.get("sitemap_issues")
    if has_sitemap is True and sitemap_issues is False:
        sitemap_value, sitemap_level = "Gültig", "ok"
    elif has_sitemap is True and sitemap_issues is True:
        sitemap_value, sitemap_level = "Gefunden, mit Fehlern", "warn"
    else:
        sitemap_value, sitemap_level = "nicht gefunden", "bad"

    # robots.txt
    robots_found = (r.get("bot_blocking") or {}).get("found_robots")
    robots_ok = bool(robots_found is True)
    robots_value = "gefunden" if robots_ok else "nicht gefunden"
    robots_level = "ok" if robots_ok else "bad"

    rows = (
        _quick_check_row("Broken links", broken_value, broken_level)
        + _quick_check_row("SSL-Verschlüsselung", ssl_value, ssl_level)
        + _quick_check_row("Sitemap", sitemap_value, sitemap_level)
        + _quick_check_row("Robots.txt", robots_value, robots_level)
    )

    return (
        "<div style='margin-top:22px;'>"
        "<div style='font-size:30px; font-weight:700; margin:0 0 8px 0; padding-bottom:6px; border-bottom:2px solid rgba(238,49,107,1);'>Technischer Quick-Check</div>"
        "<div style='font-size:14px; line-height:1.6; margin-top:8px;'>"
        "Ein kompakter Blick auf zentrale technische Grundlagen Ihrer Website."
        "</div>"
        f"<div style='margin-top:10px;'>{rows}</div>"
        "</div>"
    )


def build_local_seo_fdm_block(
    ctx: ReportContext,
    uberall_input: dict,
    uberall_api_key: str = "",
    google_places_api_key: str = "",
    insites_api_key: str = "",
) -> dict:
    location_id = (uberall_input or {}).get("location_id", "").strip()
    name = (uberall_input or {}).get("name", "").strip()
    street = (uberall_input or {}).get("street", "").strip()
    postal_code = (uberall_input or {}).get("postal_code", "").strip()
    insites_report_id = (uberall_input or {}).get("insites_report_id", "").strip()

    profile_completeness = None
    source_label = "nicht verfügbar"
    df_insights = pd.DataFrame()
    has_fdm_profile = False
    uberall_feedback = {
        "average_rating": None,
        "number_of_reviews": None,
        "review_response_rate_pct": None,
    }
    directories_found_count = None
    directories_total = 36
    insites_mobile_data = {}
    insites_report = {}

    if insites_report_id and insites_api_key:
        try:
            insites_payload = insites_get_report(insites_report_id, insites_api_key)
            report = (insites_payload or {}).get("report") or {}
            lp = report.get("local_presence") or {}
            lpn = report.get("local_presence_normalised") or {}

            raw_found = lp.get("directories_listings_found_count")
            if raw_found is None:
                raw_found = lpn.get("directories_found_count")
            if raw_found is not None:
                directories_found_count = int(float(raw_found))

            raw_total = lp.get("directories_checked_count")
            if raw_total is None:
                raw_total = lpn.get("directories_tested_count")
            if raw_total is not None:
                directories_total = int(float(raw_total))
            insites_mobile_data = report.get("mobile") or {}
            insites_report = report
        except Exception:
            pass

    use_live = UBERALL_LIVE_MODE and bool(uberall_api_key)
    if use_live:
        try:
            location = None
            loc_id = ""
            # Default: immer zuerst Domain -> website Match.
            try:
                location = _find_location_by_domain(ctx.domain, uberall_api_key)
            except Exception:
                location = None

            # Optionaler manueller Override per expliziter ID.
            if location is None and location_id:
                loc_id = str(location_id)
                try:
                    location_payload = uberall_get(f"locations/{loc_id}", api_key=uberall_api_key)
                    location = _extract_location_one(location_payload) or {"id": loc_id}
                except Exception:
                    location = {"id": loc_id}

            if location:
                loc_id = str(location.get("id") or loc_id or location_id)
                profile_from_dashboard = _fetch_profile_completeness(loc_id, uberall_api_key)
                if profile_from_dashboard is not None:
                    profile_completeness = profile_from_dashboard
                if profile_completeness is None:
                    profile_completeness = int(
                        float(location.get("profileCompleteness") or location.get("listingQualityScore") or 0)
                    )

                df_insights = _fetch_insights(ctx, loc_id, uberall_api_key)
                uberall_feedback = _fetch_customer_feedback(ctx, loc_id, uberall_api_key)
                has_fdm_profile = True

                matched_name = str(location.get("name") or "nicht verfügbar")
                matched_website = str(location.get("website") or "nicht verfügbar")
                source_label = (
                    f"Gefundenes Unternehmensprofil: "
                    f"Unternehmensname: {matched_name} · "
                    f"Website: {matched_website} · "
                    f"Location-ID: {loc_id}"
                )
        except Exception:
            pass

    # Google presence KPIs
    if df_insights.empty or not has_fdm_profile:
        search_impr = None
        maps_impr = None
        clicks = None
        area_fig = None
        table_fig = None
    else:
        search_impr = int(df_insights["search_impr"].sum())
        maps_impr = int(df_insights["maps_impr"].sum())
        clicks = int(df_insights["clicks"].sum())
        area_fig = area_chart(
            df=df_insights,
            x_col="date",
            y_col="total_impr",
            line_color=CI_COLORS["COLOR_2"],
            fill_rgba="rgba(0,185,228,0.18)",
        )
        rows = []
        for _, r in df_insights.tail(12).iterrows():
            rows.append(
                [
                    pd.to_datetime(r["date"]).strftime("%Y-%m"),
                    str(int(r["search_impr"])),
                    str(int(r["maps_impr"])),
                    str(int(r["clicks"])),
                ]
            )
        table_fig = table_chart(headers=["Monat", "Suche-Impr.", "Maps-Impr.", "Klicks"], rows=rows)

    # Google reviews
    rating = None
    review_count = None
    review_source = "nicht verfügbar"
    if (
        has_fdm_profile
        and
        uberall_feedback.get("average_rating") is not None
        and uberall_feedback.get("number_of_reviews") is not None
    ):
        rating = float(uberall_feedback["average_rating"])
        review_count = int(uberall_feedback["number_of_reviews"])
        review_source = "Firmendaten Manager – customer-feedback-by-period"
    elif GOOGLE_PLACES_LIVE_MODE and google_places_api_key and name and street:
        try:
            rating, review_count = fetch_rating_and_review_count(
                google_places_api_key,
                name=name,
                street=street,
                postal_code=postal_code,
            )
            review_source = "Google Places API (öffentlich)"
        except Exception:
            pass

    pre_html = (
        "<div style='font-size:14px; line-height:1.6; margin-top:6px;'>"
        "Dieser Abschnitt fasst alle relevanten Local-SEO-Daten rund um Ihr Unternehmensprofil zusammen. "
        "Neben den Angaben aus dem Firmendaten-Manager fließen auch ergänzende Google-Signale ein, "
        "die für Ihre lokale Sichtbarkeit wichtig sind."
        "</div>"
    )

    if not has_fdm_profile:
        pre_html += (
            "<div style='margin-top:8px; color:#666; font-size:12px;'>"
            "Für diese Domain wurde kein passendes Firmendaten-Manager-Unternehmensprofil gefunden. "
            "Daher werden FDM-abhängige Kennzahlen in diesem Abschnitt ausgeblendet."
            "</div>"
        )
    else:
        pre_html += (
            "<div style='font-size:14px; line-height:1.6; margin-top:12px; font-weight:700;'>Profilvollständigkeit</div>"
            "<div style='font-size:14px; line-height:1.6; margin-top:4px;'>"
            "Ein vollständig gepflegtes Unternehmensprofil erhöht die Chance, bei lokalen Suchanfragen besser gefunden "
            "zu werden – und sorgt gleichzeitig für einen professionellen und vertrauenswürdigen ersten Eindruck bei "
            "potenziellen Kund:innen."
            "</div>"
        )
        pre_html += _gauge_html(
            profile_completeness,
            directories_found=directories_found_count,
            directories_total=directories_total,
        )
        pre_html += f"<div style='margin-top:8px; color:#666; font-size:12px;'>Quelle: {source_label}</div>"

    if has_fdm_profile:
        pre_html += (
            "<div style='font-size:14px; line-height:1.6; margin-top:12px; font-weight:700;'>"
            "Google Präsenz"
            "</div>"
            "<div style='font-size:14px; line-height:1.6; margin-top:4px;'>"
            "Die Werte geben einen Überblick darüber, wie oft Ihr Profil in der Suche und in Maps eingeblendet wurde "
            "und wie viele Personen darauf geklickt haben."
            "</div>"
            + _kpi_cards_html(
                [
                    ("Suche Impressions", _fmt_int_eu(search_impr) if search_impr is not None else "nicht verfügbar"),
                    ("Maps Impressions", _fmt_int_eu(maps_impr) if maps_impr is not None else "nicht verfügbar"),
                    ("Klicks", _fmt_int_eu(clicks) if clicks is not None else "nicht verfügbar"),
                ]
            )
        )

    response_card_html = (
        _response_rate_html(percent=uberall_feedback.get("review_response_rate_pct"))
        if has_fdm_profile
        else ""
    )
    grid_cols = "1fr 1fr" if has_fdm_profile else "1fr"
    post_html = (
        "<div style='margin-top: 0;'>"
        "<div style='font-size:30px; font-weight:700; margin:0 0 8px 0; padding-bottom:6px; border-bottom:2px solid rgba(238,49,107,1);'>Google Bewertungen</div>"
        "</div>"
        f"<div style='display:grid; grid-template-columns:{grid_cols}; gap:14px; margin-top:18px; margin-bottom:18px;'>"
        + (
            _star_rating_html(rating, int(review_count))
            if rating is not None and review_count is not None
            else (
                "<div style='border:1px solid rgba(0,0,0,0.08); border-radius:12px; padding:14px;'>"
                "<div style='font-weight:700; margin-bottom:8px;'>Google Bewertungen</div>"
                "<div style='color:#666;'>Werte verfügbar, wenn Unternehmensname und Straße + Hausnummer ausgefüllt sind.</div>"
                "</div>"
            )
        )
        + response_card_html
        + "</div>"
        + (
            f"<div style='margin-top:14px; color:#666; font-size:12px;'>Quelle Google Bewertungen: {review_source}</div>"
            if review_source
            else ""
        )
        + "<div style='font-size:14px; line-height:1.6; margin-top:12px;'>"
        "Google-Bewertungen sind einer der wichtigsten Vertrauensfaktoren im digitalen Raum. Für viele Interessierte sind sie der erste Eindruck Ihres Unternehmens – noch bevor die Website besucht oder Kontakt aufgenommen wird. Eine hohe Anzahl an Bewertungen und ein starkes Durchschnittsrating stärken Glaubwürdigkeit, beeinflussen Kaufentscheidungen positiv und wirken sich zudem direkt auf die lokale Sichtbarkeit bei Google aus."
        "</div>"
        + "<div style='font-size:14px; line-height:1.6; margin-top:10px;'>"
        "Ebenso entscheidend ist der professionelle Umgang mit Feedback. Zeitnahe und wertschätzende Antworten auf Bewertungen – insbesondere auf kritische Rückmeldungen – zeigen Kundennähe, Engagement und Serviceorientierung. Unternehmen, die aktiv reagieren, hinterlassen nicht nur einen besseren Eindruck, sondern stärken langfristig ihre Reputation und Kundenbindung."
        "</div>"
        + (_mobile_audit_html(insites_mobile_data) if insites_mobile_data else "")
        + (_technical_quick_check_html(insites_report) if insites_report else "")
    )

    return {
        "id": "local_seo_fdm",
        "title": "Local SEO – Auswertung Ihres Unternehmensprofils",
        "accent_token": "COLOR_2",
        "pre_html": pre_html,
        "fig": area_fig,
        "post_fig": table_fig,
        "post_html": post_html,
    }
