import math
import pandas as pd

from core.context import ReportContext
from core.config import DEV_MODE, SISTRIX_RANKING_BLOCKS_LIVE
from services.sistrix_keyword_domain import fetch_keyword_domain_snapshot
from components.charts import table_chart


def _pick_int(value, default=0):
    try:
        return int(float(value))
    except Exception:
        return default


def _pick_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def _extract_rows(data: dict) -> list[dict]:
    rows = []

    def walk(obj):
        if isinstance(obj, dict):
            kw = obj.get("kw") or obj.get("keyword")
            pos = obj.get("position")
            url = obj.get("url")
            traffic = obj.get("traffic")
            sv = obj.get("sv") or obj.get("search_volume") or obj.get("search")

            if kw and pos is not None:
                rows.append(
                    {
                        "kw": str(kw),
                        "position": _pick_float(pos, 999.0),
                        "traffic": _pick_float(traffic, 0.0),
                        "sv": _pick_int(sv, 0),
                        "url": str(url or ""),
                    }
                )

            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for v in obj:
                walk(v)

    walk(data)
    return rows


def _fetch_rankings(ctx: ReportContext, api_key: str) -> tuple[pd.DataFrame, str]:
    try:
        df = fetch_keyword_domain_snapshot(ctx, api_key, ctx.end_date, limit=120)
    except Exception as e:
        raise RuntimeError(str(e))

    rows = _extract_rows({"rows": df.to_dict(orient="records")})
    if rows:
        return pd.DataFrame(rows), "SISTRIX keyword.domain.seo (address_object, weekly snapshot)"
    raise RuntimeError("Keine SISTRIX-Daten verfügbar")


def _interest_score(position: float, sv: int, traffic: float) -> float:
    pos_factor = 1.0 / max(position, 1.0)
    vol = sv if sv > 0 else (traffic * 100.0)
    return pos_factor * math.log1p(vol)


def build_interesting_rankings_block(ctx: ReportContext, sistrix_api_key: str, openai_api_key: str) -> dict:
    use_fake = DEV_MODE and not SISTRIX_RANKING_BLOCKS_LIVE

    try:
        # --------------------------
        # Daten laden
        # --------------------------
        if use_fake:
            fake = [
                {"kw": "lipödem behandlung", "position": 3, "sv": 2400, "traffic": 2.1, "url": f"https://www.{ctx.domain}/behandlung-lipoedem"},
                {"kw": "lipo clinic wien", "position": 2, "sv": 1300, "traffic": 1.7, "url": f"https://www.{ctx.domain}/"},
                {"kw": "lipödem symptome", "position": 7, "sv": 1900, "traffic": 1.2, "url": f"https://www.{ctx.domain}/lipo-lexikon"},
                {"kw": "lymphdrainage lipödem", "position": 6, "sv": 900, "traffic": 0.9, "url": f"https://www.{ctx.domain}/lipo-lexikon"},
                {"kw": "lipödem stadium 2", "position": 4, "sv": 1000, "traffic": 1.0, "url": f"https://www.{ctx.domain}/lipo-lexikon"},
                {"kw": "lipödem ernährung", "position": 8, "sv": 700, "traffic": 0.7, "url": f"https://www.{ctx.domain}/team"},
                {"kw": "lipödem therapie", "position": 9, "sv": 850, "traffic": 0.8, "url": f"https://www.{ctx.domain}/behandlung-lipoedem"},
                {"kw": "lipödem kompression", "position": 5, "sv": 600, "traffic": 0.6, "url": f"https://www.{ctx.domain}/lipo-lexikon"},
                {"kw": "lipödem operation", "position": 10, "sv": 1100, "traffic": 0.9, "url": f"https://www.{ctx.domain}/kontakt"},
                {"kw": "lipödem arzt wien", "position": 1, "sv": 500, "traffic": 1.5, "url": f"https://www.{ctx.domain}/"},
            ]
            df = pd.DataFrame(fake)
            source_line = "Quelle: Demo-Daten"
        else:
            df, source_line = _fetch_rankings(ctx, sistrix_api_key)

        # --------------------------
        # Scoring & Top 10 Auswahl
        # --------------------------
        df["score"] = df.apply(
            lambda r: _interest_score(float(r["position"]), int(r.get("sv", 0)), float(r.get("traffic", 0.0))),
            axis=1,
        )
        df = df.sort_values("score", ascending=False).head(10).reset_index(drop=True)

        # --------------------------
        # Tabelle bauen
        # --------------------------
        headers = ["Keyword", "Pos.", "URL"]
        table_rows = []
        for _, r in df.iterrows():
            table_rows.append(
                [
                    str(r["kw"]),
                    str(int(round(float(r["position"])))),
                    str(r.get("url", "")),
                ]
            )

        fig = table_chart(headers=headers, rows=table_rows, column_widths=[0.30, 0.05, 0.65])

        pre_html = (
            "<div style='font-size:14px; line-height:1.6; margin-top:6px;'>"
            "Hier zeigen wir Suchbegriffe mit besonderer Bedeutung für Ihre Website – entweder weil sie bereits sehr gut "
            "platziert sind oder weil sie ein hohes Suchvolumen haben. So erkennen Sie auf einen Blick, wo Sie besonders "
            "sichtbar sind und wo großes Potenzial liegt."
            "</div>"
            "<div style='margin-top:8px; color:#666; font-size:12px; font-style:italic;'>"
            "Quelle: Auswertung mit dem SEO-Tool SISTRIX (Google.at, Mobile)."
            "</div>"
        )

        return {
            "id": "interesting_rankings",
            "title": "Interessante Rankings",
            "accent_token": "COLOR_4",
            "pre_html": pre_html,
            "fig": fig,
            "comment_title": "Einordnung",
            "comment": (
                "Diese Auswahl zeigt, bei welchen Suchanfragen Ihre Website bereits besonders gut sichtbar ist "
                "oder ein starkes Nachfragepotenzial besitzt. Damit erkennen wir schnell, welche Themen heute "
                "schon tragen und in welchen Bereichen sich gezielte weitere Optimierungen besonders lohnen."
            ),
        }

    except Exception as e:
        # NIEMALS None zurückgeben – immer ein Dict
        return {
            "id": "interesting_rankings",
            "title": "Interessante Rankings",
            "accent_token": "COLOR_4",
            "error": f"Fehler im Modul Interessante Rankings: {e}",
        }
