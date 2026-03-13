import pandas as pd
from datetime import date

from core.context import ReportContext
from core.config import DEV_MODE, SISTRIX_RANKING_BLOCKS_LIVE
from services.sistrix_keyword_domain import fetch_keyword_domain_snapshot
from components.charts import table_chart


MAX_NEWCOMERS = 20
MAX_WINNERS = 20
MAX_LOSERS = 5


def _fmt_eu(d: date) -> str:
    return d.strftime("%d.%m.%Y")


def _fetch_snapshot(ctx: ReportContext, api_key: str, dt: date) -> pd.DataFrame:
    try:
        raw = fetch_keyword_domain_snapshot(ctx, api_key, dt, limit=120, from_pos=1, to_pos=100)
    except Exception as e:
        raise RuntimeError(str(e))
    if raw.empty:
        raise RuntimeError("Keine SISTRIX-Daten für Snapshot erhalten.")
    return (
        raw.sort_values(["kw", "position"])
        .drop_duplicates("kw", keep="first")
        .rename(columns={"position": "pos"})
        .reset_index(drop=True)
    )


def _short_url(u: str) -> str:
    if not u:
        return ""
    # nur Pfad, damit die Tabelle im PDF nicht explodiert
    for prefix in ("https://", "http://"):
        if u.startswith(prefix):
            u = u[len(prefix):]
    # Domain entfernen, wenn vorhanden
    parts = u.split("/", 1)
    return "/" + parts[1] if len(parts) > 1 else "/"


def _block(
    title: str,
    accent_token: str,
    intro_html: str,
    headers: list[str],
    rows: list[list[str]],
    comment: str,
    table_height: int | None = None,
) -> dict:
    width_map = {
        3: [0.30, 0.05, 0.65],
        5: [0.25, 0.07, 0.07, 0.07, 0.54],
    }
    fig = table_chart(headers=headers, rows=rows, column_widths=width_map.get(len(headers)))
    if table_height is not None:
        fig.update_layout(height=table_height)
    return {
        "id": title.lower().replace(" ", "_"),
        "title": title,
        "accent_token": accent_token,
        "pre_html": intro_html,
        "fig": fig,
        "comment_title": "Einordnung",
        "comment": comment,
    }


def build_newcomers_block(ctx: ReportContext, sistrix_api_key: str, openai_api_key: str) -> dict:
    use_fake = DEV_MODE and not SISTRIX_RANKING_BLOCKS_LIVE

    if use_fake:
        rows = [
            ["lipödem wien", "12", "/behandlung-lipoedem"],
            ["lipödem arzt", "8", "/"],
            ["lipödem therapie", "19", "/lipo-lexikon"],
        ]
        intro = (
            "<div style='font-size:14px; line-height:1.6; margin-top:6px;'>"
            "Hier sehen Sie Suchbegriffe, für die Ihre Website im gewählten Zeitraum neu in den Google-Suchergebnissen erscheint. "
            "Das bedeutet, dass Ihre Seite zu weiteren Suchanfragen sichtbar geworden ist. "
            "Die Übersicht zeigt, bei welchen zusätzlichen Suchanfragen Ihre Website aktuell auffindbar ist."
            "</div>"
        )
        return _block(
            "Neu hinzugewonnene Google-Rankings",
            "COLOR_2",
            intro,
            ["Keyword", "Pos. aktuell", "URL"],
            rows,
            "Diese neu hinzugewonnenen Rankings zeigen, dass Ihre Website für zusätzliche Suchanfragen bei Google "
            "sichtbar geworden ist. Das ist ein positives Signal für den Ausbau Ihrer thematischen Reichweite und "
            "ein Hinweis darauf, dass sich Inhalte und Optimierungen Schritt für Schritt in neuen Suchfeldern etablieren.",
        )

    try:
        df_start = _fetch_snapshot(ctx, sistrix_api_key, ctx.start_date)
        df_end = _fetch_snapshot(ctx, sistrix_api_key, ctx.end_date)
    except Exception as e:
        return {"id": "newcomers", "title": "Neu hinzugewonnene Google-Rankings", "accent_token": "COLOR_2", "error": f"SISTRIX-Fehler bei Neueinsteiger: {e}"}

    if df_end.empty:
        return {"id": "newcomers", "title": "Neu hinzugewonnene Google-Rankings", "accent_token": "COLOR_2", "error": "Keine Daten von SISTRIX erhalten."}

    start_set = set(df_start["kw"].tolist()) if not df_start.empty else set()
    newcomers = df_end[~df_end["kw"].isin(start_set)].copy()

    # nach „Impact“ sortieren: Traffic absteigend, dann Position
    newcomers = newcomers.sort_values(["traffic", "pos"], ascending=[False, True]).head(MAX_NEWCOMERS)

    rows = [[r.kw, str(int(round(r.pos))), _short_url(r.url)] for r in newcomers.itertuples(index=False)]

    intro = (
        "<div style='font-size:14px; line-height:1.6; margin-top:6px;'>"
        "Hier sehen Sie Suchbegriffe, für die Ihre Website im gewählten Zeitraum neu in den Google-Suchergebnissen erscheint. "
        "Das bedeutet, dass Ihre Seite zu weiteren Suchanfragen sichtbar geworden ist. "
        "Die Übersicht zeigt, bei welchen zusätzlichen Suchanfragen Ihre Website aktuell auffindbar ist."
        "</div>"
        f"<div style='margin-top:8px; color:#666; font-size:12px;'>Start: {_fmt_eu(ctx.start_date)}<br>Ende: {_fmt_eu(ctx.end_date)}</div>"
    )

    return _block(
        "Neu hinzugewonnene Google-Rankings",
        "COLOR_2",
        intro,
        ["Keyword", "Pos. aktuell", "URL"],
        rows,
        "Diese neu hinzugewonnenen Rankings zeigen, dass Ihre Website für zusätzliche Suchanfragen bei Google "
        "sichtbar geworden ist. Das ist ein positives Signal für den Ausbau Ihrer thematischen Reichweite und "
        "ein Hinweis darauf, dass sich Inhalte und Optimierungen Schritt für Schritt in neuen Suchfeldern etablieren.",
    )


def build_winners_block(ctx: ReportContext, sistrix_api_key: str, openai_api_key: str) -> dict:
    use_fake = DEV_MODE and not SISTRIX_RANKING_BLOCKS_LIVE

    if use_fake:
        rows = [
            ["lipödem behandlung", "9", "3", "+6", "/behandlung-lipoedem"],
            ["lipödem symptome", "14", "7", "+7", "/lipo-lexikon"],
        ]
        intro = (
            "<div style='font-size:14px; line-height:1.6; margin-top:6px;'>"
            "Diese Suchbegriffe haben ihre Position bei Google im gewählten Zeitraum verbessert. "
            "Sie zeigen, wo Ihre Website spürbar an Sichtbarkeit gewonnen und sich im Wettbewerbsumfeld "
            "weiter nach vorne entwickelt hat. Besonders erfreulich ist dabei, wenn wichtige oder stark "
            "nachgefragte Themen unter den Gewinnern sind – denn bessere Platzierungen bedeuten eine "
            "stärkere Präsenz bei relevanten Suchanfragen."
            "</div>"
        )
        return _block(
            "Ranking-Gewinner",
            "COLOR_3",
            intro,
            ["Keyword", "Pos. vorher", "Pos. aktuell", "Δ", "URL"],
            rows,
            "Die positiven Positionsveränderungen unterstreichen die insgesamt gute Entwicklungsrichtung. "
            "Sie zeigen, in welchen Themenbereichen Ihre Website aktuell an Stärke gewinnt und weiter an "
            "Relevanz aufbaut. Diese Dynamik ist eine wichtige Grundlage, um erreichte Verbesserungen zu "
            "stabilisieren und weitere Potenziale Schritt für Schritt zu erschließen.",
        )

    try:
        df_start = _fetch_snapshot(ctx, sistrix_api_key, ctx.start_date)
        df_end = _fetch_snapshot(ctx, sistrix_api_key, ctx.end_date)
    except Exception as e:
        return {"id": "winners", "title": "Ranking-Gewinner", "accent_token": "COLOR_3", "error": f"SISTRIX-Fehler bei Gewinnern: {e}"}

    if df_start.empty or df_end.empty:
        return {"id": "winners", "title": "Ranking-Gewinner", "accent_token": "COLOR_3", "error": "Zu wenig Daten von SISTRIX erhalten."}

    merged = df_end.merge(df_start, on="kw", suffixes=("_end", "_start"))
    merged["delta"] = merged["pos_start"] - merged["pos_end"]  # positiv = besser

    winners = merged[merged["delta"] > 0].copy()
    winners = winners.sort_values(["delta", "traffic_end"], ascending=[False, False]).head(MAX_WINNERS)

    rows = []
    for r in winners.itertuples(index=False):
        rows.append(
            [
                r.kw,
                str(int(round(r.pos_start))),
                str(int(round(r.pos_end))),
                f"+{int(round(r.delta))}",
                _short_url(r.url_end),
            ]
        )

    intro = (
        "<div style='font-size:14px; line-height:1.6; margin-top:6px;'>"
        "Diese Suchbegriffe haben ihre Position bei Google im gewählten Zeitraum verbessert. "
        "Sie zeigen, wo Ihre Website spürbar an Sichtbarkeit gewonnen und sich im Wettbewerbsumfeld "
        "weiter nach vorne entwickelt hat. Besonders erfreulich ist dabei, wenn wichtige oder stark "
        "nachgefragte Themen unter den Gewinnern sind – denn bessere Platzierungen bedeuten eine "
        "stärkere Präsenz bei relevanten Suchanfragen."
        "</div>"
        f"<div style='margin-top:8px; color:#666; font-size:12px;'>Start: {_fmt_eu(ctx.start_date)}<br>Ende: {_fmt_eu(ctx.end_date)}</div>"
    )

    return _block(
        "Ranking-Gewinner",
        "COLOR_3",
        intro,
        ["Keyword", "Pos. vorher", "Pos. aktuell", "Δ", "URL"],
        rows,
        "Die positiven Positionsveränderungen unterstreichen die insgesamt gute Entwicklungsrichtung. "
        "Sie zeigen, in welchen Themenbereichen Ihre Website aktuell an Stärke gewinnt und weiter an "
        "Relevanz aufbaut. Diese Dynamik ist eine wichtige Grundlage, um erreichte Verbesserungen zu "
        "stabilisieren und weitere Potenziale Schritt für Schritt zu erschließen.",
    )


def build_losers_block(ctx: ReportContext, sistrix_api_key: str, openai_api_key: str) -> dict:
    use_fake = DEV_MODE and not SISTRIX_RANKING_BLOCKS_LIVE

    if use_fake:
        rows = [
            ["lipödem operation", "6", "10", "-4", "/kontakt"],
            ["lipödem ernährung", "5", "8", "-3", "/team"],
        ]
        intro = (
            "<div style='font-size:14px; line-height:1.6; margin-top:6px;'>"
            "Wo es Gewinner gibt, gibt es auch einzelne Begriffe, die im betrachteten Zeitraum Positionen verloren haben. "
            "Solche Schwankungen sind bei Google völlig normal, da sich Rankings regelmäßig durch Wettbewerb, "
            "Updates oder saisonale Effekte verändern."
            "</div>"
        )
        return _block(
            "Ranking-Veränderungen mit Rückgang",
            "COLOR_6",
            intro,
            ["Keyword", "Pos. vorher", "Pos. aktuell", "Δ", "URL"],
            rows,
            "Ein Großteil dieser Bewegungen findet häufig in den hinteren Ranking-Bereichen statt und hat in der Praxis "
            "nur geringe Auswirkungen auf die Sichtbarkeit. Entscheidend ist der Gesamttrend – und der bleibt stabil. "
            "Wir behalten diese Entwicklungen im Blick und prüfen gezielt, wo Handlungsbedarf besteht.",
        )

    try:
        df_start = _fetch_snapshot(ctx, sistrix_api_key, ctx.start_date)
        df_end = _fetch_snapshot(ctx, sistrix_api_key, ctx.end_date)
    except Exception as e:
        return {"id": "losers", "title": "Ranking-Veränderungen mit Rückgang", "accent_token": "COLOR_6", "error": f"SISTRIX-Fehler bei Verlierern: {e}"}

    if df_start.empty or df_end.empty:
        return {"id": "losers", "title": "Ranking-Veränderungen mit Rückgang", "accent_token": "COLOR_6", "error": "Zu wenig Daten von SISTRIX erhalten."}

    merged = df_end.merge(df_start, on="kw", suffixes=("_end", "_start"))
    merged["delta"] = merged["pos_start"] - merged["pos_end"]  # negativ = schlechter

    losers = merged[merged["delta"] < 0].copy()
    losers = losers.sort_values(["delta", "traffic_end"], ascending=[True, False]).head(MAX_LOSERS)

    rows = []
    for r in losers.itertuples(index=False):
        rows.append(
            [
                r.kw,
                str(int(round(r.pos_start))),
                str(int(round(r.pos_end))),
                str(int(round(r.delta))),  # ist negativ
                _short_url(r.url_end),
            ]
        )

    intro = (
        "<div style='font-size:14px; line-height:1.6; margin-top:6px;'>"
        "Wo es Gewinner gibt, gibt es auch einzelne Begriffe, die im betrachteten Zeitraum Positionen verloren haben. "
        "Solche Schwankungen sind bei Google völlig normal, da sich Rankings regelmäßig durch Wettbewerb, "
        "Updates oder saisonale Effekte verändern."
        "</div>"
        f"<div style='margin-top:8px; color:#666; font-size:12px;'>Start: {_fmt_eu(ctx.start_date)}<br>Ende: {_fmt_eu(ctx.end_date)}</div>"
    )

    return _block(
        "Ranking-Veränderungen mit Rückgang",
        "COLOR_6",
        intro,
        ["Keyword", "Pos. vorher", "Pos. aktuell", "Δ", "URL"],
        rows,
        "Ein Großteil dieser Bewegungen findet häufig in den hinteren Ranking-Bereichen statt und hat in der Praxis "
        "nur geringe Auswirkungen auf die Sichtbarkeit. Entscheidend ist der Gesamttrend – und der bleibt stabil. "
        "Wir behalten diese Entwicklungen im Blick und prüfen gezielt, wo Handlungsbedarf besteht.",
        table_height=250,
    )
