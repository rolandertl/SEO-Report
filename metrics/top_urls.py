import pandas as pd

from core.context import ReportContext
from core.config import CI_COLORS, CHART_PALETTES, DEV_MODE, SISTRIX_TOP_URLS_LIVE
from components.charts import donut_chart
from services.sistrix import call as sistrix_call
from services.sistrix_keyword_domain import fetch_keyword_domain_snapshot


def _build_colored_list_html(urls: list[str], values: list[float], colors: list[str]) -> str:
    html = "<div style='margin-top:18px;'>"
    for url, v, c in zip(urls, values, colors):
        html += f"""
<div style="display:flex; align-items:center; gap:10px; padding:10px 0; border-bottom:1px solid rgba(0,0,0,0.06);">
    <span style="width:12px; height:12px; border-radius:999px; background:{c}; display:inline-block;"></span>
    <span style="font-size:14px; color:#404041;"><strong>{url}</strong></span>
    <span style="margin-left:auto; font-size:14px; color:#404041; font-weight:700;">{v:.1f}%</span>
</div>
"""
    html += "</div>"
    return html


def _fake_top_urls(ctx: ReportContext) -> tuple[list[str], list[float]]:
    urls = [
        f"www.{ctx.domain}/",
        f"www.{ctx.domain}/leistungen",
        f"www.{ctx.domain}/team",
        f"www.{ctx.domain}/kontakt",
        f"www.{ctx.domain}/blog",
        f"www.{ctx.domain}/ueber-uns",
    ]
    values = [42.0, 20.0, 14.0, 10.0, 8.0, 6.0]
    return urls, values


def _extract_top100_from_domain_urls(data: dict, top_n: int = 6) -> tuple[list[str], list[float]]:
    rows: list[dict] = []

    def pick_count(obj: dict) -> float | None:
        for key in ("top100", "top_100", "kwcount", "keyword_count", "count", "value"):
            v = obj.get(key)
            if v is None:
                continue
            try:
                f = float(v)
            except Exception:
                continue
            if f >= 0:
                return f
        return None

    def walk(obj):
        if isinstance(obj, dict):
            url = (obj.get("url") or obj.get("path") or "").strip()
            if url:
                cnt = pick_count(obj)
                if cnt is not None:
                    rows.append({"url": url, "top100": cnt})
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for x in obj:
                walk(x)

    walk(data)
    if not rows:
        return [], []

    df = pd.DataFrame(rows)
    grouped = df.groupby("url", as_index=False)["top100"].sum().sort_values("top100", ascending=False).head(top_n)
    total = float(grouped["top100"].sum()) or 1.0
    urls = grouped["url"].tolist()
    values = [round((float(v) / total) * 100.0, 1) for v in grouped["top100"].tolist()]
    return urls, values


def _api_hint(data: dict) -> str:
    if isinstance(data, list):
        if data and isinstance(data[0], dict):
            msg = data[0].get("error_message") or data[0].get("message")
            if msg:
                return str(msg)
        return "Unerwartetes Antwortformat (Liste)"
    if not isinstance(data, dict):
        return "Unerwartetes Antwortformat"
    for key in ("error", "error_message", "message"):
        if key in data and data.get(key):
            return str(data.get(key))
    top_keys = ",".join(list(data.keys())[:8])
    return f"Keine URL-Daten gefunden (Antwort-Keys: {top_keys})"


def _domain_variants(domain: str) -> list[str]:
    d = (domain or "").strip().lower()
    d = d.replace("https://", "").replace("http://", "").split("/")[0]
    if d.startswith("www."):
        d = d[4:]
    return [d] if d else []


def _looks_like_domain_not_found(data) -> bool:
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and "domain not found" in str(item.get("error_message", "")).lower():
                return True
    if isinstance(data, dict):
        msg = str(data.get("error_message", "")).lower()
        return "domain not found" in msg
    return False


def _fetch_top_urls_live(ctx: ReportContext, sistrix_api_key: str, top_n: int = 6) -> tuple[list[str], list[float]]:
    last_error_payload = None

    for dom in _domain_variants(ctx.domain):
        base_common = {
            "country": ctx.country,
            "mobile": "true",
            "format": "json",
        }

        # 1) domain.urls mit domain-Parameter
        data_urls = sistrix_call(
            "domain.urls",
            api_key=sistrix_api_key,
            params={**base_common, "domain": dom, "num": "200"},
        )
        if not _looks_like_domain_not_found(data_urls):
            urls, values = _extract_top100_from_domain_urls(data_urls, top_n=top_n)
            if urls:
                return urls, values
        else:
            last_error_payload = data_urls

        # 2) Fallback: aus keyword.domain.seo (zentral gecacht) ableiten
        try:
            df = fetch_keyword_domain_snapshot(ctx, sistrix_api_key, ctx.end_date, limit=120)
        except Exception as e:
            last_error_payload = {"error_message": str(e)}
            df = pd.DataFrame()
        if df.empty:
            continue

        grouped = (
            df.groupby("url", as_index=False)
            .agg(
                top100=("url", "count"),
                top10=("position", lambda s: int((s <= 10).sum())),
                traffic=("traffic", "sum"),
            )
            .sort_values(["top100", "traffic"], ascending=[False, False])
        )
        top = grouped.head(top_n).copy()
        total_top100 = float(top["top100"].sum()) or 1.0
        urls = top["url"].tolist()
        values = [round((float(v) / total_top100) * 100.0, 1) for v in top["top100"].tolist()]
        if urls:
            return urls, values

    raise RuntimeError(_api_hint(last_error_payload or {}))


def build_top_urls_block(ctx: ReportContext, sistrix_api_key: str, openai_api_key: str) -> dict:
    use_fake = DEV_MODE and not SISTRIX_TOP_URLS_LIVE

    if use_fake:
        urls, values = _fake_top_urls(ctx)
        source_line = "Quelle: Demo-Daten"
    else:
        try:
            urls, values = _fetch_top_urls_live(ctx, sistrix_api_key, top_n=6)
            source_line = "Quelle: SISTRIX keyword.domain.seo (Top-URLs nach Anzahl Top-100-Keywords)"
        except Exception as e:
            return {
                "id": "top_urls",
                "title": "Top URLs",
                "accent_token": "COLOR_2",
                "error": f"SISTRIX-Fehler bei Top URLs: {e}",
            }

    palette_tokens = CHART_PALETTES["top_urls_5"]
    palette_colors = [CI_COLORS[t] for t in palette_tokens]
    while len(palette_colors) < len(urls):
        palette_colors.append(CI_COLORS["COLOR_6"])

    fig = donut_chart(labels=urls, values=values, colors=palette_colors[: len(urls)])
    fig.update_traces(domain={"x": [0.0, 0.86]}, selector=dict(type="pie"))
    pre_html = (
        "<div style='font-size:14px; line-height:1.6; margin-top:14px;'>"
        "Top URLs zeigt die Seiten Ihrer Website, die den größten Anteil an den Top-100-Rankings tragen "
        "und damit wesentlich zur organischen Sichtbarkeit beitragen."
        "</div>"
        + _build_colored_list_html(urls, values, palette_colors[: len(urls)])
        + f"<div style='margin-top:12px; margin-bottom:26px; color:#666; font-size:12px;'>{source_line}</div>"
    )

    return {
        "id": "top_urls",
        "title": "Top URLs",
        "accent_token": "COLOR_2",
        "pre_html": pre_html,
        "fig": fig,
        "kpis": {
            "top_1": urls[0] if urls else "",
            "top_1_value": values[0] if values else 0,
        },
    }
