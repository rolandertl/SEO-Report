import pandas as pd
from datetime import timedelta

from core.context import ReportContext
from core.config import DEV_MODE, CI_COLORS, SISTRIX_KEYWORD_PROFILE_LIVE
from services.sistrix import call as sistrix_call
from components.charts import dual_area_chart


def _domain_variants(domain: str) -> list[str]:
    d = (domain or "").strip().lower()
    d = d.replace("https://", "").replace("http://", "").split("/")[0]
    if d.startswith("www."):
        d = d[4:]
    return [d] if d else []


def _api_hint(data) -> str:
    if isinstance(data, list):
        if data and isinstance(data[0], dict):
            msg = data[0].get("error_message") or data[0].get("message")
            if msg:
                return str(msg)
        return "Unerwartetes Antwortformat (Liste)"
    if isinstance(data, dict):
        for key in ("error", "error_message", "message"):
            if key in data and data.get(key):
                return str(data.get(key))
        return "Keine Daten im erwarteten Format"
    return "Unerwartetes Antwortformat"


def _parse_sistrix_series(data) -> pd.DataFrame:
    rows = []

    def walk(obj):
        if isinstance(obj, dict):
            d = obj.get("date") or obj.get("datetime") or obj.get("time")
            v = obj.get("value") or obj.get("count") or obj.get("amount")
            if d is not None and v is not None:
                try:
                    rows.append({"date": pd.to_datetime(d), "value": float(v)})
                except Exception:
                    pass
            for v2 in obj.values():
                walk(v2)
        elif isinstance(obj, list):
            for v2 in obj:
                walk(v2)

    walk(data)

    if not rows:
        return pd.DataFrame(columns=["date", "value"])

    df = pd.DataFrame(rows).dropna(subset=["date"])
    df = df.sort_values("date").drop_duplicates(subset=["date"], keep="last").reset_index(drop=True)
    return df


def _fetch_series_history(endpoint: str, ctx: ReportContext, api_key: str) -> tuple[pd.DataFrame, object]:
    last_payload = None
    last_error = None
    for dom in _domain_variants(ctx.domain):
        for dom_key in ("domain", "address_object"):
            params = {
                dom_key: dom,
                "country": ctx.country,
                "mobile": "true",
                "history": "true",
                "format": "json",
                "limit": "24",
            }
            try:
                data = sistrix_call(endpoint, api_key=api_key, params=params)
            except Exception as e:
                last_error = e
                continue
            last_payload = data
            df = _parse_sistrix_series(data)
            if not df.empty:
                return df, data
    return pd.DataFrame(columns=["date", "value"]), (last_payload or {"error_message": str(last_error)} if last_error else last_payload)


def _fetch_series_weekly(endpoint: str, ctx: ReportContext, api_key: str) -> tuple[pd.DataFrame, object]:
    last_payload = None
    last_error = None
    rows = []

    start_monday = ctx.start_date - timedelta(days=ctx.start_date.weekday())
    end = ctx.end_date

    for dom in _domain_variants(ctx.domain):
        cur = start_monday
        rows.clear()
        while cur <= end:
            params = {
                "address_object": dom,
                "country": ctx.country,
                "mobile": "true",
                "date": cur.isoformat(),
                "format": "json",
                "limit": "1",
            }
            try:
                data = sistrix_call(endpoint, api_key=api_key, params=params)
            except Exception as e:
                last_error = e
                cur += timedelta(days=7)
                continue
            last_payload = data
            df = _parse_sistrix_series(data)
            if not df.empty:
                val = float(df.iloc[-1]["value"])
                rows.append({"date": pd.to_datetime(cur), "value": val})
            cur += timedelta(days=7)

        if rows:
            out = pd.DataFrame(rows).sort_values("date").drop_duplicates("date", keep="last").reset_index(drop=True)
            return out, last_payload

    return pd.DataFrame(columns=["date", "value"]), (last_payload or {"error_message": str(last_error)} if last_error else last_payload)


def _fetch_kwcount_series(endpoint: str, ctx: ReportContext, api_key: str) -> tuple[pd.DataFrame, str]:
    df_hist, payload_hist = _fetch_series_history(endpoint, ctx, api_key)
    if not df_hist.empty:
        return df_hist, "history"

    # Wenn history zwar antwortet, aber keine Daten enthält, vermeiden wir
    # den teuren Wochen-Fallback (spart massiv Credits bei No-Data-Domains).
    if payload_hist:
        hint = _api_hint(payload_hist)
        raise RuntimeError(f"{endpoint}: {hint}")

    df_week, payload_week = _fetch_series_weekly(endpoint, ctx, api_key)
    if not df_week.empty:
        return df_week, "weekly-date"

    hint = _api_hint(payload_week or {})
    raise RuntimeError(f"{endpoint}: {hint}")


def _kpi_cards_html(top100: int, top10: int) -> str:
    return f"""
<div style="display:flex; gap:16px; margin-top:30px;">
  <div style="flex:1; border:1px solid rgba(0,0,0,0.08); border-radius:12px; overflow:hidden;">
    <div style="background:rgba(0,0,0,0.03); padding:10px 14px; font-weight:700;">Top-100-Keywords</div>
    <div style="padding:18px 14px; font-size:34px; font-weight:800; text-align:center;">{top100}</div>
  </div>

  <div style="flex:1; border:1px solid rgba(0,0,0,0.08); border-radius:12px; overflow:hidden;">
    <div style="background:rgba(0,0,0,0.03); padding:10px 14px; font-weight:700;">Keyword-Profil</div>
    <div style="padding:0;">
      <div style="display:flex; justify-content:space-between; padding:12px 14px; border-top:1px solid rgba(0,0,0,0.06);">
        <span>Top-10</span><strong>{top10}</strong>
      </div>
      <div style="display:flex; justify-content:space-between; padding:12px 14px; border-top:1px solid rgba(0,0,0,0.06);">
        <span>Top-100</span><strong>{top100}</strong>
      </div>
    </div>
  </div>
</div>
"""


def build_keyword_profile_block(ctx: ReportContext, sistrix_api_key: str, openai_api_key: str) -> dict:
    use_fake = DEV_MODE and not SISTRIX_KEYWORD_PROFILE_LIVE

    if use_fake:
        dates = pd.date_range(start=ctx.start_date, end=ctx.end_date, freq="W-MON")
        base100, base10 = 140, 70
        top100_series, top10_series = [], []
        for i in range(len(dates)):
            base100 += (i % 5) - 1
            base10 += (i % 3) - 1
            top100_series.append(max(0, base100))
            top10_series.append(max(0, base10))
        df = pd.DataFrame({"date": dates, "top100": top100_series, "top10": top10_series})
        top100 = int(df["top100"].iloc[-1])
        top10 = int(df["top10"].iloc[-1])
        source_line = "Quelle: SISTRIX Keywordverlauf"
    else:
        try:
            df100, mode100 = _fetch_kwcount_series("domain.kwcount.seo", ctx, sistrix_api_key)
            df10, mode10 = _fetch_kwcount_series("domain.kwcount.seo.top10", ctx, sistrix_api_key)
        except Exception as e:
            return {
                "id": "keyword_profile",
                "title": "Wo und wie oft Ihre Website bei Google erscheint",
                "accent_token": "COLOR_3",
                "error": f"SISTRIX-Fehler bei Keyword-Profil: {e}",
            }

        df100 = df100.rename(columns={"value": "top100"})
        df10 = df10.rename(columns={"value": "top10"})
        df = pd.merge(df100, df10, on="date", how="inner").sort_values("date").reset_index(drop=True)
        df = df[(df["date"].dt.date >= ctx.start_date) & (df["date"].dt.date <= ctx.end_date)]

        if df.empty:
            return {
                "id": "keyword_profile",
                "title": "Wo und wie oft Ihre Website bei Google erscheint",
                "accent_token": "COLOR_3",
                "error": "SISTRIX lieferte keine gemeinsamen Top-100/Top-10 Zeitreihen im gewählten Zeitraum.",
            }

        top100 = int(round(float(df["top100"].iloc[-1])))
        top10 = int(round(float(df["top10"].iloc[-1])))
        source_line = "Quelle: SISTRIX Keywordverlauf"

    pre_html = (
        "<div style='font-size:14px; line-height:1.6; margin-top:6px;'>"
        "Die Zahlen zeigen, für wie viele Suchbegriffe Ihre Website gefunden wird – "
        "und bei wie vielen davon sie bereits ganz vorne mitspielt. "
        "So sehen Sie, ob wir Schritt für Schritt mehr Sichtbarkeit und bessere Platzierungen aufbauen."
        "</div>"
        + _kpi_cards_html(top100=top100, top10=top10)
        + f"<div style='margin-top:18px; margin-bottom:38px; color:#666; font-size:12px;'>{source_line}</div>"
    )

    fig = dual_area_chart(
        df=df,
        x_col="date",
        y1_col="top100",
        y2_col="top10",
        label1="Top-100",
        label2="Top-10",
        color1=CI_COLORS["COLOR_1"],
        color2=CI_COLORS["COLOR_2"],
        fill1="rgba(238,49,107,0.18)",
        fill2="rgba(0,185,228,0.18)",
    )

    comment = (
        "Die Grafik zeigt, wie sich Ihre Google-Präsenz in der Breite und an der Spitze entwickelt.<br>"
        "Top-100 bedeutet: Ihre Website ist grundsätzlich zu einem Thema auffindbar.<br>"
        "Top-10 bedeutet: Sie gehört bei wichtigen Suchanfragen zu den sichtbarsten Ergebnissen auf Seite 1.<br><br>"
        "So erkennen wir, ob wir Reichweite aufbauen und gleichzeitig zentrale Positionen stärken."
    )

    return {
        "id": "keyword_profile",
        "title": "Wo und wie oft Ihre Website bei Google erscheint",
        "accent_token": "COLOR_3",
        "pre_html": pre_html,
        "fig": fig,
        "comment_title": "Einordnung",
        "comment": comment,
        "kpis": {"top100": top100, "top10": top10},
    }
