from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from core.context import ReportContext
from services.sistrix import call as sistrix_call


_KEYWORD_CACHE: dict[tuple, pd.DataFrame] = {}
_KEYWORD_EMPTY: set[tuple] = set()
_KEYWORD_ERROR: dict[tuple, str] = {}


def _norm_domain(domain: str) -> str:
    d = (domain or "").strip().lower()
    d = d.replace("https://", "").replace("http://", "").split("/")[0]
    if d.startswith("www."):
        d = d[4:]
    return d


def _to_last_monday(d: date) -> str:
    monday = d - timedelta(days=d.weekday())
    return monday.isoformat()


def _extract_rows(data: dict) -> list[dict]:
    rows: list[dict] = []

    def walk(obj):
        if isinstance(obj, dict):
            kw = obj.get("kw") or obj.get("keyword")
            pos = obj.get("position")
            url = obj.get("url") or ""
            traffic = obj.get("traffic", 0)
            sv = obj.get("sv") or obj.get("search_volume") or obj.get("search")

            if kw and pos is not None:
                try:
                    pos_f = float(pos)
                except Exception:
                    pos_f = 999.0
                try:
                    traffic_f = float(traffic)
                except Exception:
                    traffic_f = 0.0
                try:
                    sv_i = int(float(sv)) if sv is not None else 0
                except Exception:
                    sv_i = 0

                rows.append(
                    {
                        "kw": str(kw),
                        "position": pos_f,
                        "url": str(url),
                        "traffic": traffic_f,
                        "sv": sv_i,
                    }
                )

            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for v in obj:
                walk(v)

    walk(data)
    return rows


def fetch_keyword_domain_snapshot(
    ctx: ReportContext,
    api_key: str,
    dt: date,
    *,
    limit: int = 120,
    from_pos: int = 1,
    to_pos: int = 100,
) -> pd.DataFrame:
    dom = _norm_domain(ctx.domain)
    week = _to_last_monday(dt)

    cache_key = (dom, ctx.country, week, int(limit), int(from_pos), int(to_pos))
    cached = _KEYWORD_CACHE.get(cache_key)
    if cached is not None:
        return cached.copy()
    if cache_key in _KEYWORD_EMPTY:
        msg = _KEYWORD_ERROR.get(cache_key, "Keine auswertbaren URL-Daten")
        raise RuntimeError(msg)

    last_error = None
    country_variants = [ctx.country]
    if ctx.country:
        country_variants.append("")

    for country in country_variants:
        for addr_key in ("address_object", "domain", "host"):
            for mobile in ("true", "false"):
                params = {
                    addr_key: dom,
                    "mobile": mobile,
                    "format": "json",
                    "limit": str(limit),
                    "from_pos": str(from_pos),
                    "to_pos": str(to_pos),
                    "date": week,
                }
                if country:
                    params["country"] = country
                try:
                    data = sistrix_call("keyword.domain.seo", api_key=api_key, params=params)
                except Exception as e:
                    last_error = e
                    continue

                rows = _extract_rows(data)
                if rows:
                    df = pd.DataFrame(rows)
                    _KEYWORD_CACHE[cache_key] = df
                    return df.copy()

                last_error = RuntimeError("Keine auswertbaren URL-Daten")

    if last_error is None:
        last_error = RuntimeError(
            f"Keine Ranking-Daten für Domain '{dom}' (country={ctx.country}, date={week}, Top-{to_pos})."
        )
    elif "Keine auswertbaren URL-Daten" in str(last_error):
        last_error = RuntimeError(
            f"Keine Ranking-Daten für Domain '{dom}' (country={ctx.country}, date={week}, Top-{to_pos})."
        )
    _KEYWORD_EMPTY.add(cache_key)
    _KEYWORD_ERROR[cache_key] = str(last_error)
    raise RuntimeError(str(last_error))
