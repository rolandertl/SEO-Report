import pandas as pd
from datetime import date

from core.context import ReportContext
from core.config import UBERALL_LIVE_MODE, CI_COLORS
from components.charts import area_chart, table_chart
from services.uberall import get as uberall_get
from metrics.uberall_presence import _resolve_location


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
    return f"""<div style="display:flex; gap:14px; margin-top:14px;">{cards}</div>"""


def _num(v) -> float | None:
    try:
        return float(v)
    except Exception:
        return None


def _fetch_insights(ctx: ReportContext, loc_id: str, uberall_api_key: str) -> pd.DataFrame:
    # Offizieller Dashboard-Endpoint laut Doku:
    # type=GOOGLE + metrics aus Enum (BUSINESS_IMPRESSIONS_*, QUERIES_*, ACTIONS_* ...)
    metric_sets = [
        [
            "BUSINESS_IMPRESSIONS_DESKTOP_SEARCH",
            "BUSINESS_IMPRESSIONS_MOBILE_SEARCH",
            "BUSINESS_IMPRESSIONS_DESKTOP_MAPS",
            "BUSINESS_IMPRESSIONS_MOBILE_MAPS",
            "ACTIONS_WEBSITE",
            "ACTIONS_PHONE",
            "ACTIONS_DRIVING_DIRECTIONS",
        ],
        ["QUERIES_DIRECT", "QUERIES_INDIRECT", "QUERIES_CHAIN", "VIEWS_MAPS", "ACTIONS_WEBSITE", "ACTIONS_PHONE", "ACTIONS_DRIVING_DIRECTIONS"],
        ["VIEWS_SEARCH", "VIEWS_MAPS", "ACTIONS_WEBSITE", "ACTIONS_PHONE", "ACTIONS_DRIVING_DIRECTIONS"],
    ]
    base_params = {
        "group": "MONTH",
        "startDate": ctx.start_date.isoformat(),
        "endDate": ctx.end_date.isoformat(),
    }
    # Endpoint-Varianten bei unterschiedlichen API-Gateways/Accounts.
    request_variants = []
    for metrics in metric_sets:
        request_variants.extend(
            [
                {**base_params, "locationIds": str(loc_id), "type": "GOOGLE", "metrics": metrics},
                {**base_params, "locationIds": [int(loc_id)], "type": "GOOGLE", "metrics": metrics},
                {**base_params, "locationId": str(loc_id), "type": "GOOGLE", "metrics": metrics},
            ]
        )

    data = None
    for p in request_variants:
        try:
            data = uberall_get("dashboard/insights-data", api_key=uberall_api_key, params=p)
        except Exception:
            continue
        if isinstance(data, dict):
            has_data_rows = bool(data.get("data") or ((data.get("response") or {}).get("data")))
            has_metric_rows = bool(((data.get("response") or {}).get("metrics")))
            if has_data_rows or has_metric_rows:
                break

    rows = []
    if isinstance(data, dict):
        # Shape A: {"data":[{"date":..., ...}]}
        metric_rows = data.get("data") or ((data.get("response") or {}).get("data") or [])
        if isinstance(metric_rows, list) and metric_rows:
            for row in metric_rows:
                if not isinstance(row, dict):
                    continue
                d = row.get("date") or row.get("period")
                if not d:
                    continue
                # Mögliche direkte Felder in data-rows
                bis_d = _num(row.get("BUSINESS_IMPRESSIONS_DESKTOP_SEARCH")) or 0.0
                bis_m = _num(row.get("BUSINESS_IMPRESSIONS_MOBILE_SEARCH")) or 0.0
                bim_d = _num(row.get("BUSINESS_IMPRESSIONS_DESKTOP_MAPS")) or 0.0
                bim_m = _num(row.get("BUSINESS_IMPRESSIONS_MOBILE_MAPS")) or 0.0
                qd = _num(row.get("QUERIES_DIRECT")) or 0.0
                qi = _num(row.get("QUERIES_INDIRECT")) or 0.0
                qc = _num(row.get("QUERIES_CHAIN")) or 0.0
                vs = _num(row.get("VIEWS_SEARCH")) or 0.0
                search_val = (bis_d + bis_m) if (bis_d + bis_m) > 0 else ((qd + qi + qc) if (qd + qi + qc) > 0 else vs)
                maps_val = (bim_d + bim_m) if (bim_d + bim_m) > 0 else (_num(row.get("VIEWS_MAPS")) or 0.0)
                rows.append(
                    {
                        "date": d,
                        "search_impr": search_val,
                        "maps_impr": maps_val,
                        "clicks": (
                            (_num(row.get("ACTIONS_WEBSITE")) or 0.0)
                            + (_num(row.get("ACTIONS_PHONE")) or 0.0)
                            + (_num(row.get("ACTIONS_DRIVING_DIRECTIONS")) or 0.0)
                        ),
                    }
                )

        # Shape B (alt/anderes Dashboard): {"response":{"metrics":[{"name":"...", "data":[{period,count},...]},...]}}
        if not rows:
            metrics_container = ((data.get("response") or {}).get("metrics") or [])
            if isinstance(metrics_container, list) and metrics_container:
                by_period: dict[str, dict] = {}
                name_map = {
                    # Preferred business impressions
                    "BUSINESS_IMPRESSIONS_DESKTOP_SEARCH": "search_impr",
                    "BUSINESS_IMPRESSIONS_MOBILE_SEARCH": "search_impr",
                    "BUSINESS_IMPRESSIONS_DESKTOP_MAPS": "maps_impr",
                    "BUSINESS_IMPRESSIONS_MOBILE_MAPS": "maps_impr",
                    # Google Search Signals
                    "QUERIES_DIRECT": "search_impr",
                    "QUERIES_INDIRECT": "search_impr",
                    "QUERIES_CHAIN": "search_impr",
                    "VIEWS_SEARCH": "search_impr",
                    # Google Maps Signals
                    "VIEWS_MAPS": "maps_impr",
                    # Click/Action Signals
                    "ACTIONS_WEBSITE": "clicks",
                    "ACTIONS_PHONE": "clicks",
                    "ACTIONS_DRIVING_DIRECTIONS": "clicks",
                }
                for metric in metrics_container:
                    if not isinstance(metric, dict):
                        continue
                    m_name = str(metric.get("name") or "")
                    target = name_map.get(m_name)
                    if not target:
                        continue
                    for point in metric.get("data") or []:
                        if not isinstance(point, dict):
                            continue
                        period = point.get("period") or point.get("date")
                        count = _num(point.get("count"))
                        if not period or count is None:
                            continue
                        bucket = by_period.setdefault(
                            str(period),
                            {"date": str(period), "search_impr": 0.0, "maps_impr": 0.0, "clicks": 0.0},
                        )
                        # Bei Klicks können mehrere Teilmetriken kommen -> addieren
                        bucket[target] = float(bucket.get(target, 0.0)) + float(count)
                rows = list(by_period.values())

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    df = df.groupby("date", as_index=False)[["search_impr", "maps_impr", "clicks"]].sum()
    df["total_impr"] = df["search_impr"] + df["maps_impr"]

    return df[["date", "search_impr", "maps_impr", "clicks", "total_impr"]]


def _extract_feedback_payload(data: dict) -> dict:
    if not isinstance(data, dict):
        return {}
    if any(k in data for k in ("averageRating", "numberOfReviews", "reviewResponseRate", "totalRatingCount")):
        return data
    for key in ("data", "response", "answer", "result"):
        child = data.get(key)
        if isinstance(child, dict) and any(
            k in child
            for k in (
                "averageRating",
                "numberOfReviews",
                "reviewResponseRate",
                "averageRatingByPeriod",
                "interactionCountByPeriod",
                "totalRatingCount",
            )
        ):
            return child
    return {}


def _to_float(v, default=None):
    try:
        return float(v)
    except Exception:
        return default


def _to_int(v, default=None):
    try:
        return int(round(float(v)))
    except Exception:
        return default


def _normalize_response_rate(v) -> int | None:
    f = _to_float(v, None)
    if f is None:
        return None
    # API kann 0..1 oder 0..100 liefern.
    if 0 <= f <= 1:
        f = f * 100.0
    return max(0, min(100, int(round(f))))


def _fetch_customer_feedback(ctx: ReportContext, loc_id: str, uberall_api_key: str) -> dict:
    # Bewertungen und Antwortrate sollen als Gesamtwert angezeigt werden,
    # unabhängig vom SEO-Report-Zeitraum.
    _ = ctx
    base_params = {
        "startDate": "2000-01-01",
        "endDate": date.today().isoformat(),
    }

    # 1) Primär: customer-feedback (enthält repliedCount/ratingCount für Antwortrate)
    feedback = {}
    # Wichtige Erkenntnis aus dem Live-Abgleich:
    # customer-feedback mit type=GOOGLE liefert für einzelne Locations
    # teils nur einen Teilbestand der Reviews. Die Uberall-Dashboard-Werte
    # für Rating, Anzahl Reviews und Antwortrate entsprechen hier der
    # Aggregation OHNE type-Filter, aber mit locationIds.
    feedback_variants = [
        {**base_params, "locationIds": str(loc_id)},
        {**base_params, "locationIds": [int(loc_id)]},
        {**base_params, "locationIds": str(loc_id), "type": "GOOGLE"},
        {**base_params, "locationIds": [int(loc_id)], "type": "GOOGLE"},
    ]
    for p in feedback_variants:
        try:
            data = uberall_get("dashboard/customer-feedback", api_key=uberall_api_key, params=p)
        except Exception:
            continue
        payload = _extract_feedback_payload(data)
        if isinstance(payload, dict) and payload:
            feedback = payload
            break

    average_rating = _to_float(feedback.get("averageRating"), None)
    number_of_reviews = _to_int(feedback.get("numberOfReviews") or feedback.get("ratingCount"), None)
    response_rate_pct = _normalize_response_rate(
        feedback.get("reviewResponseRate") or feedback.get("responseRate") or feedback.get("answerRate")
    )
    if response_rate_pct is None:
        replied = _to_float(feedback.get("repliedCount"), None)
        total = _to_float(feedback.get("ratingCount"), None)
        if replied is not None and total and total > 0:
            response_rate_pct = int(round((replied / total) * 100.0))

    # 2) Ergänzend: by-period für stabile Rating/Review-Fallbacks
    by_period = {}
    by_period_variants = [
        {**base_params, "locationIds": str(loc_id)},
        {**base_params, "locationIds": [int(loc_id)]},
        {**base_params, "locationId": str(loc_id)},
    ]
    for p in by_period_variants:
        try:
            data = uberall_get("dashboard/customer-feedback-by-period", api_key=uberall_api_key, params=p)
        except Exception:
            continue
        payload = _extract_feedback_payload(data)
        if isinstance(payload, dict) and payload:
            by_period = payload
            break

    # Response-Format aus echtem Endpoint:
    # averageRatingByPeriod[{period,value}], interactionCountByPeriod[{period,count}], totalRatingCount
    if average_rating is None:
        ratings = by_period.get("averageRatingByPeriod") or []
        counts = by_period.get("interactionCountByPeriod") or []
        count_by_period = {}
        for c in counts:
            if not isinstance(c, dict):
                continue
            period = c.get("period")
            cnt = _to_float(c.get("count"), 0.0)
            if period:
                count_by_period[str(period)] = max(0.0, cnt or 0.0)
        weighted_sum = 0.0
        total_weight = 0.0
        for r in ratings:
            if not isinstance(r, dict):
                continue
            period = str(r.get("period") or "")
            val = _to_float(r.get("value"), None)
            if val is None:
                continue
            w = count_by_period.get(period, 1.0)
            weighted_sum += val * w
            total_weight += w
        if total_weight > 0:
            average_rating = weighted_sum / total_weight

    if number_of_reviews is None:
        number_of_reviews = _to_int(by_period.get("totalRatingCount"), None)
    if number_of_reviews is None:
        # Fallback: Summe aus interactionCountByPeriod
        counts = by_period.get("interactionCountByPeriod") or []
        number_of_reviews = int(
            round(sum(_to_float(c.get("count"), 0.0) for c in counts if isinstance(c, dict)))
        ) if counts else None

    if response_rate_pct is None:
        # Optionaler Fallback über per-period Raten
        rr_rows = (
            by_period.get("reviewResponseRateByPeriod")
            or by_period.get("responseRateByPeriod")
            or feedback.get("reviewResponseRateByPeriod")
            or feedback.get("responseRateByPeriod")
            or []
        )
        vals = []
        for r in rr_rows:
            if not isinstance(r, dict):
                continue
            v = _normalize_response_rate(r.get("value") or r.get("rate"))
            if v is not None:
                vals.append(v)
        if vals:
            response_rate_pct = int(round(sum(vals) / len(vals)))

    return {
        "average_rating": average_rating,
        "number_of_reviews": number_of_reviews,
        "review_response_rate_pct": response_rate_pct,
    }


def _fetch_profile_completeness(loc_id: str, uberall_api_key: str) -> int | None:
    variants = [
        {"locationIds": str(loc_id)},
        {"locationIds": [int(loc_id)]},
        {"locationId": str(loc_id)},
    ]
    for p in variants:
        try:
            data = uberall_get("dashboard/profile-completeness", api_key=uberall_api_key, params=p)
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        r = data.get("response")
        if isinstance(r, dict):
            val = r.get("averageProfileCompleteness")
            try:
                return max(0, min(100, int(round(float(val)))))
            except Exception:
                pass
        try:
            val = data.get("averageProfileCompleteness")
            return max(0, min(100, int(round(float(val)))))
        except Exception:
            pass
    return None


def _fake_insights(ctx: ReportContext) -> pd.DataFrame:
    dates = pd.date_range(start=ctx.start_date, end=ctx.end_date, freq="MS")
    rows = []
    s = 1200
    m = 650
    c = 140
    for i, d in enumerate(dates):
        s += (i % 4) * 60 - 30
        m += (i % 3) * 40 - 20
        c += (i % 5) * 8 - 4
        rows.append(
            {
                "date": d,
                "search_impr": max(0, s),
                "maps_impr": max(0, m),
                "clicks": max(0, c),
                "total_impr": max(0, s + m),
            }
        )
    return pd.DataFrame(rows)


def build_uberall_insights_block(ctx: ReportContext, uberall_input: dict, uberall_api_key: str = "") -> dict:
    location_id = (uberall_input or {}).get("location_id", "").strip()
    name = (uberall_input or {}).get("name", "").strip()
    street = (uberall_input or {}).get("street", "").strip()
    postal_code = (uberall_input or {}).get("postal_code", "").strip()

    if not location_id:
        pre_html = (
            "<div style='font-size:14px; line-height:1.6; margin-top:6px;'>"
            "Dieser Abschnitt zeigt die Entwicklung Ihrer lokalen Google-Reichweite: "
            "Impressionen in Suche/Maps sowie daraus entstehende Interaktionsklicks."
            "</div>"
            + _kpi_cards_html(
                [
                    ("Suche Impressions", "nicht verfügbar"),
                    ("Maps Impressions", "nicht verfügbar"),
                    ("Klicks", "nicht verfügbar"),
                ]
            )
            + "<div style='margin-top:8px; color:#666; font-size:12px;'>Quelle: Kein Firmendaten Manager gefunden</div>"
        )

        return {
            "id": "uberall_insights",
            "title": "Google Präsenz – Impressions & Klicks",
            "accent_token": "COLOR_2",
            "pre_html": pre_html,
            "comment_title": "Einordnung",
            "comment": "Diese Auswertung setzt den Einsatz des EDELWEISS Digital Firmendaten Managers voraus.",
        }

    if UBERALL_LIVE_MODE and not uberall_api_key:
        return {
            "id": "uberall_insights",
            "title": "Google Präsenz – Impressions & Klicks",
            "accent_token": "COLOR_2",
            "error": "Firmendaten Manager Live ist aktiv, aber UBERALL_API_KEY fehlt in den Secrets.",
        }

    use_live = UBERALL_LIVE_MODE and bool(uberall_api_key)

    if not use_live:
        df = _fake_insights(ctx)
        source_label = "Demo-Daten"
    else:
        try:
            location, source_label = _resolve_location(uberall_input, uberall_api_key)
            if not location:
                return {
                    "id": "uberall_insights",
                    "title": "Google Präsenz – Impressions & Klicks",
                    "accent_token": "COLOR_2",
                    "error": "Firmendaten Manager: Standort konnte nicht gefunden werden (prüfe Location-ID).",
                }

            loc_id = str(location.get("id") or location_id)
            df = _fetch_insights(ctx, loc_id, uberall_api_key)
            if df.empty:
                return {
                    "id": "uberall_insights",
                    "title": "Google Präsenz – Impressions & Klicks",
                    "accent_token": "COLOR_2",
                    "error": "Firmendaten Manager Insights: keine auswertbaren Daten für den Zeitraum erhalten.",
                }
        except Exception as e:
            return {
                "id": "uberall_insights",
                "title": "Google Präsenz – Impressions & Klicks",
                "accent_token": "COLOR_2",
                "error": f"Firmendaten Manager Insights-Fehler: {e}",
            }

    # KPI-Karten sollen Zeitraum-Summen zeigen (nicht nur letzter Monat).
    search_impr = int(df["search_impr"].sum())
    maps_impr = int(df["maps_impr"].sum())
    clicks = int(df["clicks"].sum())

    pre_html = (
        "<div style='font-size:14px; line-height:1.6; margin-top:6px;'>"
        "Dieser Abschnitt zeigt die Entwicklung Ihrer lokalen Google-Reichweite: "
        "Impressionen in Suche/Maps sowie daraus entstehende Interaktionsklicks."
        "</div>"
        + _kpi_cards_html(
            [
                ("Suche Impressions", _fmt_int_eu(search_impr)),
                ("Maps Impressions", _fmt_int_eu(maps_impr)),
                ("Klicks", _fmt_int_eu(clicks)),
            ]
        )
        + f"<div style='margin-top:8px; color:#666; font-size:12px;'>Quelle: {source_label}</div>"
    )

    fig = area_chart(
        df=df,
        x_col="date",
        y_col="total_impr",
        line_color=CI_COLORS["COLOR_2"],
        fill_rgba="rgba(0,185,228,0.18)",
    )

    table_rows = []
    for _, r in df.tail(12).iterrows():
        table_rows.append(
            [
                pd.to_datetime(r["date"]).strftime("%Y-%m"),
                str(int(r["search_impr"])),
                str(int(r["maps_impr"])),
                str(int(r["clicks"])),
            ]
        )

    post_fig = table_chart(
        headers=["Monat", "Suche-Impr.", "Maps-Impr.", "Klicks"],
        rows=table_rows,
    )

    comment = (
        "Die Google-Präsenzdaten zeigen, wie sich Reichweite und Interaktionen in den lokalen Kanälen entwickeln. "
        "Für die operative Steuerung beobachten wir Suche/Maps-Impressions und Klicks gemeinsam."
    )

    return {
        "id": "uberall_insights",
        "title": "Google Präsenz – Impressions & Klicks",
        "accent_token": "COLOR_2",
        "pre_html": pre_html,
        "fig": fig,
        "post_fig": post_fig,
        "comment_title": "Einordnung",
        "comment": comment,
    }
