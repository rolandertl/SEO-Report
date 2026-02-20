import pandas as pd
import requests
from dateutil.relativedelta import relativedelta
from datetime import timedelta

from core.context import ReportContext
from core.config import BRAND, CI_COLORS
from components.charts import area_chart
from services.sistrix import call as sistrix_call
from core.config import DEV_MODE, SISTRIX_VISIBILITY_LIVE
import random



def _parse_sistrix_timeseries(data: dict) -> pd.DataFrame:
    rows = []

    def walk(obj):
        if isinstance(obj, dict):
            if "date" in obj and ("value" in obj or "visibilityindex" in obj):
                v = obj.get("value", obj.get("visibilityindex"))
                try:
                    rows.append({"date": obj["date"], "value": float(v)})
                except Exception:
                    pass
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for v in obj:
                walk(v)

    walk(data.get("answer", data))

    df = pd.DataFrame(rows).drop_duplicates()
    if df.empty:
        return df

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).sort_values("date")
    return df


def fetch_visibility_monthly_points(ctx: ReportContext, sistrix_api_key: str) -> pd.DataFrame:
    """
    Stabiler Abruf ohne history=1 Timeouts:
    wöchentliche Punkte (Montag) via date=, um den SISTRIX-Verlauf besser zu treffen.
    """
    all_parts = []

    # Wochenbasiert (wie SISTRIX-Kurven typischerweise dargestellt)
    cur = ctx.start_date - timedelta(days=ctx.start_date.weekday())
    end = ctx.end_date

    while cur <= end:

        data = sistrix_call(
            "domain.visibilityindex",
            api_key=sistrix_api_key,
            params={
                "domain": ctx.domain,
                "country": ctx.country,
                "mobile": "1",
                "date": cur.isoformat(),
            },
        )

        df_part = _parse_sistrix_timeseries(data)
        if not df_part.empty:
            all_parts.append(df_part)

        cur = cur + timedelta(days=7)

    if not all_parts:
        return pd.DataFrame(columns=["date", "value"])

    df = pd.concat(all_parts, ignore_index=True).drop_duplicates()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).sort_values("date")
    df = df[(df["date"].dt.date >= ctx.start_date) & (df["date"].dt.date <= ctx.end_date)]
    return df


def build_visibility_block(ctx: ReportContext, sistrix_api_key: str, openai_api_key: str) -> dict:

    use_fake = DEV_MODE and not SISTRIX_VISIBILITY_LIVE

    if use_fake:
        # --------------------------
        # FAKE DATA GENERATION
        # --------------------------
        import pandas as pd

        dates = pd.date_range(start=ctx.start_date, end=ctx.end_date, freq="MS")
        base = 1.2

        values = []
        for i in range(len(dates)):
            base += random.uniform(-0.1, 0.25)
            values.append(round(base, 3))

        df = pd.DataFrame({
            "date": dates,
            "value": values
        })

        start_val = df.iloc[0]["value"]
        end_val = df.iloc[-1]["value"]
        delta_pct = (end_val - start_val) / start_val * 100

        fig = area_chart(
            df=df,
            x_col="date",
            y_col="value",
            line_color=CI_COLORS[BRAND["primary"]],
            fill_rgba="rgba(238, 49, 107, 0.15)",
            value_decimals=4,
            y_tickformat=".4f",

        )

        comment = (
            "Die Sichtbarkeit zeigt im gewählten Zeitraum eine positive Entwicklung. "
            "Leichte Schwankungen sind im SEO normal, insgesamt ist jedoch eine klare "
            "Stabilisierung und Tendenz nach oben erkennbar. "
            "Unsere laufenden Optimierungsmaßnahmen greifen sichtbar und werden "
            "die Entwicklung weiter unterstützen."
        )

        pre_html = (
            "<div style='font-size:14px; line-height:1.6; margin-top:6px;'>"
            "<strong>Performance Ihrer Website in den Google-Suchergebnissen (Mobile, AT)</strong><br>"
            "Diese Grafik zeigt die Sichtbarkeit Ihrer Domain in den organischen Google-Ergebnissen. "
            "Der Wert basiert auf einer laufenden Auswertung relevanter Suchbegriffe und macht sichtbar, "
            "wie sich Ihre Präsenz im gewählten Zeitraum entwickelt hat – und ob unsere SEO-Maßnahmen Wirkung zeigen.<br><br>"
            f"<strong>Aktueller Wert:</strong> {end_val:.4f} · "
            f"<strong>Startwert:</strong> {start_val:.4f} · "
            f"<strong>Veränderung:</strong> {delta_pct:+.2f}%<br>"
            "<span style='font-size:12px; font-style:italic; color:#666;'>"
            "Der Wert basiert auf dem Sichtbarkeitsindex des SEO-Tools SISTRIX für Google.at (Mobile)."
            "</span>"
            "</div>"
        )

        return {
            "id": "visibility",
            "title": "Sichtbarkeitsindex",
            "pre_html": pre_html,
            "df": df,
            "fig": fig,
            "comment_title": "Erklärung der Sichtbarkeitskurve",
            "comment": comment,
            "kpis": {
                "start_value": start_val,
                "end_value": end_val,
                "delta_pct": round(delta_pct, 2),
            },
        }

    # --------------------------
    # LIVE MODE (SISTRIX)
    # --------------------------
    try:
        df = fetch_visibility_monthly_points(ctx, sistrix_api_key)
    except requests.exceptions.ReadTimeout:
        return {
            "id": "visibility",
            "title": "Sichtbarkeitsindex",
            "error": "SISTRIX Timeout beim Laden des Sichtbarkeitsindex.",
        }
    except Exception as e:
        return {
            "id": "visibility",
            "title": "Sichtbarkeitsindex",
            "error": f"SISTRIX-Fehler beim Laden des Sichtbarkeitsindex: {e}",
        }

    if df.empty or len(df) < 1:
        return {
            "id": "visibility",
            "title": "Sichtbarkeitsindex",
            "error": "Keine Sichtbarkeitsdaten im gewählten Zeitraum gefunden.",
        }

    start_val = float(df.iloc[0]["value"])
    end_val = float(df.iloc[-1]["value"])
    delta_pct = (end_val - start_val) / start_val * 100 if start_val != 0 else 0.0
    max_val = float(df["value"].max()) if not df.empty else 0.0
    value_decimals = 5 if max_val < 0.001 else 4
    y_tickformat = ".5f" if max_val < 0.001 else ".4f"

    fig = area_chart(
        df=df,
        x_col="date",
        y_col="value",
        line_color=CI_COLORS[BRAND["primary"]],
        fill_rgba="rgba(238, 49, 107, 0.15)",
        value_decimals=value_decimals,
        y_tickformat=y_tickformat,
    )

    if delta_pct >= 0:
        comment = (
            f"Gute Entwicklung: Ihre Website gewinnt an Sichtbarkeit (+{delta_pct:.2f}%). "
            "Das bedeutet mehr Chancen, von potenziellen Kund:innen gefunden zu werden. "
            "Zwischenzeitliche Ausschläge sind im SEO-Alltag normal – entscheidend ist der positive Gesamttrend."
        )
    else:
        comment = (
            f"Die Kurve ist zuletzt etwas zurückgegangen ({delta_pct:.2f}%). "
            "Das kommt bei Google immer wieder vor und ist kein Grund zur Sorge. "
            "Wir prüfen genau, woran es liegt, und setzen gezielt Maßnahmen, um wieder Wachstum zu erzielen."
        )

    pre_html = (
        "<div style='font-size:14px; line-height:1.6; margin-top:6px;'>"
        "<strong>Performance Ihrer Website in den Google-Suchergebnissen (Mobile, AT)</strong><br>"
        "Diese Grafik zeigt die Sichtbarkeit Ihrer Domain in den organischen Google-Ergebnissen. "
        "Der Wert basiert auf einer laufenden Auswertung relevanter Suchbegriffe und macht sichtbar, "
        "wie sich Ihre Präsenz im gewählten Zeitraum entwickelt hat – und ob unsere SEO-Maßnahmen Wirkung zeigen.<br><br>"
        f"<strong>Aktueller Wert:</strong> {end_val:.{value_decimals}f} · "
        f"<strong>Startwert:</strong> {start_val:.{value_decimals}f} · "
        f"<strong>Veränderung:</strong> {delta_pct:+.2f}%<br>"
        "<span style='font-size:12px; font-style:italic; color:#666;'>"
        "Der Wert basiert auf dem Sichtbarkeitsindex des SEO-Tools SISTRIX für Google.at (Mobile)."
        "</span>"
        "</div>"
    )

    return {
        "id": "visibility",
        "title": "Sichtbarkeitsindex",
        "pre_html": pre_html,
        "df": df,
        "fig": fig,
        "comment_title": "Erklärung der Sichtbarkeitskurve",
        "comment": comment,
        "kpis": {
            "start_value": start_val,
            "end_value": end_val,
            "delta_pct": round(delta_pct, 2),
        },
    }
