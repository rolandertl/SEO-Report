import pandas as pd
import plotly.graph_objects as go

from core.context import ReportContext
from core.config import DEV_MODE, CI_COLORS, SISTRIX_BACKLINKS_LIVE
from services.sistrix import call as sistrix_call


def _fmt_int_eu(v: int) -> str:
    return f"{int(v):,}".replace(",", ".")


def _domain_variants(domain: str) -> list[str]:
    d = (domain or "").strip().lower()
    d = d.replace("https://", "").replace("http://", "").split("/")[0]
    if d.startswith("www."):
        d = d[4:]
    return [d] if d else []


def _api_error(data) -> str | None:
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return str(data[0].get("error_message") or data[0].get("message") or "")
    if isinstance(data, dict):
        err = data.get("error")
        if isinstance(err, list) and err and isinstance(err[0], dict):
            msg = err[0].get("error_message") or err[0].get("message")
            if msg:
                return str(msg)
        for key in ("error", "error_message", "message"):
            if data.get(key):
                return str(data.get(key))
    return None


def _walk(obj):
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk(v)


def _num(v, default=0):
    f = _to_float(v)
    if f is None:
        return default
    return int(round(f))


def _pct(v, default=0.0):
    f = _to_float(v)
    return default if f is None else float(f)


def _to_float(v):
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if not s:
        return None
    s = s.replace("%", "").replace(" ", "")
    # de/en Tausender-/Dezimaltrennzeichen robust behandeln
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        if s.count(",") == 1 and len(s.split(",")[-1]) <= 2:
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")
    try:
        return float(s)
    except Exception:
        return None


def _collect_numeric_fields(data) -> list[tuple[str, float]]:
    rows: list[tuple[str, float]] = []
    for d in _walk(data):
        if not isinstance(d, dict):
            continue
        for k, v in d.items():
            if isinstance(v, (dict, list)):
                continue
            f = _to_float(v)
            if f is None:
                continue
            rows.append((str(k).lower(), f))
    return rows


def _pick_numeric_by_fragments(
    data,
    include_any: tuple[str, ...],
    exclude_any: tuple[str, ...] = (),
    default=0,
) -> int:
    candidates: list[float] = []
    for key, val in _collect_numeric_fields(data):
        if not any(fragment in key for fragment in include_any):
            continue
        if any(fragment in key for fragment in exclude_any):
            continue
        if val < 0:
            continue
        candidates.append(val)
    if not candidates:
        return default
    return _num(max(candidates), default=default)


def _extract_overview_num(data: dict, key: str) -> int | None:
    answer = data.get("answer")
    if isinstance(answer, list) and answer and isinstance(answer[0], dict):
        answer = answer[0]
    if not isinstance(answer, dict):
        return None

    section = answer.get(key)
    if isinstance(section, list) and section and isinstance(section[0], dict):
        if section[0].get("num") is not None:
            return _num(section[0].get("num"))
    if isinstance(section, dict) and section.get("num") is not None:
        return _num(section.get("num"))
    return None


def _extract_distribution(data, kind: str, max_items: int = 6) -> pd.DataFrame:
    candidates: list[tuple[str, float]] = []
    kind_l = kind.lower()
    marker = "tld" if kind_l == "tld" else "country"

    def parse_row(item, default_label_key: str):
        if not isinstance(item, dict):
            return
        keys_l = {str(k).lower(): k for k in item.keys()}
        label = (
            item.get(keys_l.get(default_label_key, ""))
            or item.get(keys_l.get("name", ""))
            or item.get(keys_l.get("key", ""))
            or item.get(keys_l.get("label", ""))
            or item.get(keys_l.get("code", ""))
        )
        value = (
            item.get(keys_l.get("percent", ""))
            or item.get(keys_l.get("percentage", ""))
            or item.get(keys_l.get("share", ""))
            or item.get(keys_l.get("value", ""))
            or item.get(keys_l.get("count", ""))
        )
        if not label or value is None:
            return
        candidates.append((str(label).lower().strip("."), _pct(value, 0.0)))

    def walk_container(obj, parent_key: str = ""):
        if isinstance(obj, dict):
            for k, v in obj.items():
                k_l = str(k).lower()
                if marker in k_l:
                    if isinstance(v, list):
                        for item in v:
                            parse_row(item, default_label_key=marker)
                    elif isinstance(v, dict):
                        for inner_k, inner_v in v.items():
                            if isinstance(inner_v, (int, float, str)):
                                candidates.append((str(inner_k).lower().strip("."), _pct(inner_v, 0.0)))
                            elif isinstance(inner_v, dict):
                                parse_row(inner_v, default_label_key=marker)
                walk_container(v, parent_key=k_l)
        elif isinstance(obj, list):
            for item in obj:
                walk_container(item, parent_key=parent_key)

    walk_container(data)

    if not candidates:
        return pd.DataFrame(columns=["label", "value"])

    df = pd.DataFrame(candidates, columns=["label", "value"])
    df = df.groupby("label", as_index=False)["value"].max().sort_values("value", ascending=False)
    df = df[df["value"] > 0].head(max_items)
    return df.reset_index(drop=True)


def _fallback_dist_from_domains(ctx: ReportContext) -> tuple[pd.DataFrame, pd.DataFrame]:
    tld = ctx.domain.split(".")[-1] if "." in ctx.domain else "at"
    tld_df = pd.DataFrame(
        {"label": [tld, "com", "org", "net"], "value": [55.0, 25.0, 12.0, 8.0]}
    )
    country_df = pd.DataFrame(
        {"label": ["at", "de", "us", "gb"], "value": [48.0, 22.0, 18.0, 12.0]}
    )
    return tld_df, country_df


def _fetch_links_overview(ctx: ReportContext, api_key: str) -> dict:
    last_payload = None
    for dom in _domain_variants(ctx.domain):
        # Für links.overview ist "domain" die verlässlichste Variante.
        payload = sistrix_call(
            "links.overview",
            api_key=api_key,
            params={"domain": dom, "format": "json"},
        )
        err = (_api_error(payload) or "").lower()
        if "domain not found" in err:
            last_payload = payload
            continue
        if _extract_overview_num(payload, "total") is not None or _extract_overview_num(payload, "domains") is not None:
            return payload
        last_payload = payload

    # Fallback: host probieren
    for dom in _domain_variants(ctx.domain):
        payload = sistrix_call(
            "links.overview",
            api_key=api_key,
            params={"host": dom, "format": "json"},
        )
        if _extract_overview_num(payload, "total") is not None or _extract_overview_num(payload, "domains") is not None:
            return payload
        last_payload = payload

    if last_payload is not None:
        raise RuntimeError(_api_error(last_payload) or "domain not found")
    raise RuntimeError("Keine Daten von links.overview erhalten.")


def _kpi_overview_html(ref_domains: int, links_total: int, hostnames: int, ips: int, networks: int) -> str:
    return f"""
<div style="display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-top:10px;">
  <div style="border:1px solid rgba(0,0,0,0.08); border-radius:12px; overflow:hidden;">
    <div style="background:rgba(0,0,0,0.03); padding:10px 14px; font-weight:700;">Verweisende Domains</div>
    <div style="padding:20px 14px; font-size:40px; font-weight:800; text-align:center;">{_fmt_int_eu(ref_domains)}</div>
  </div>

  <div style="border:1px solid rgba(0,0,0,0.08); border-radius:12px; overflow:hidden;">
    <div style="background:rgba(0,0,0,0.03); padding:10px 14px; font-weight:700;">Link-Profil</div>
    <div style="padding:10px 14px;">
      <div style="display:flex; justify-content:space-between; padding:8px 0; border-bottom:1px solid rgba(0,0,0,0.06);"><span>Anzahl Links</span><strong>{_fmt_int_eu(links_total)}</strong></div>
      <div style="display:flex; justify-content:space-between; padding:8px 0; border-bottom:1px solid rgba(0,0,0,0.06);"><span>Hostnamen</span><strong>{_fmt_int_eu(hostnames)}</strong></div>
      <div style="display:flex; justify-content:space-between; padding:8px 0; border-bottom:1px solid rgba(0,0,0,0.06);"><span>IPs</span><strong>{_fmt_int_eu(ips)}</strong></div>
      <div style="display:flex; justify-content:space-between; padding:8px 0;"><span>Netzwerke</span><strong>{_fmt_int_eu(networks)}</strong></div>
    </div>
  </div>
</div>
"""


def _dual_donut(tlds: pd.DataFrame, countries: pd.DataFrame):
    colors = [CI_COLORS["COLOR_1"], CI_COLORS["COLOR_2"], CI_COLORS["COLOR_3"], CI_COLORS["COLOR_5"], CI_COLORS["COLOR_4"], CI_COLORS["COLOR_6"]]
    fig = go.Figure()

    fig.add_trace(
        go.Pie(
            labels=tlds["label"].tolist(),
            values=tlds["value"].tolist(),
            hole=0.62,
            marker=dict(colors=colors[: len(tlds)]),
            textinfo="percent",
            showlegend=False,
            domain=dict(x=[0.06, 0.40], y=[0.08, 0.86]),
        )
    )
    fig.add_trace(
        go.Pie(
            labels=[str(x).upper() for x in countries["label"].tolist()],
            values=countries["value"].tolist(),
            hole=0.62,
            marker=dict(colors=colors[: len(countries)]),
            textinfo="percent",
            showlegend=False,
            domain=dict(x=[0.50, 0.84], y=[0.08, 0.86]),
        )
    )

    fig.update_layout(
        height=290,
        margin=dict(l=20, r=40, t=60, b=4),
        showlegend=False,
        paper_bgcolor="white",
        annotations=[
            dict(text="TLDs", x=0.23, y=1.12, xref="paper", yref="paper", showarrow=False, font=dict(size=24)),
            dict(text="Länder", x=0.67, y=1.12, xref="paper", yref="paper", showarrow=False, font=dict(size=24)),
        ],
    )
    return fig


def _dual_donut_pdf(tlds: pd.DataFrame, countries: pd.DataFrame):
    colors = [CI_COLORS["COLOR_1"], CI_COLORS["COLOR_2"], CI_COLORS["COLOR_3"], CI_COLORS["COLOR_5"], CI_COLORS["COLOR_4"], CI_COLORS["COLOR_6"]]
    fig = go.Figure()

    fig.add_trace(
        go.Pie(
            labels=tlds["label"].tolist(),
            values=tlds["value"].tolist(),
            hole=0.62,
            marker=dict(colors=colors[: len(tlds)]),
            textinfo="percent",
            showlegend=False,
            domain=dict(x=[0.20, 0.80], y=[0.54, 0.98]),
        )
    )
    fig.add_trace(
        go.Pie(
            labels=[str(x).upper() for x in countries["label"].tolist()],
            values=countries["value"].tolist(),
            hole=0.62,
            marker=dict(colors=colors[: len(countries)]),
            textinfo="percent",
            showlegend=False,
            domain=dict(x=[0.20, 0.80], y=[0.02, 0.46]),
        )
    )

    fig.update_layout(
        height=620,
        margin=dict(l=30, r=30, t=70, b=10),
        showlegend=False,
        paper_bgcolor="white",
        annotations=[
            dict(text="TLDs", x=0.50, y=1.02, xref="paper", yref="paper", showarrow=False, font=dict(size=24)),
            dict(text="Länder", x=0.50, y=0.50, xref="paper", yref="paper", showarrow=False, font=dict(size=24)),
        ],
    )
    return fig


def _single_donut_pdf(title: str, df: pd.DataFrame, uppercase_labels: bool = False):
    colors = [CI_COLORS["COLOR_1"], CI_COLORS["COLOR_2"], CI_COLORS["COLOR_3"], CI_COLORS["COLOR_5"], CI_COLORS["COLOR_4"], CI_COLORS["COLOR_6"]]
    labels = [str(x).upper() if uppercase_labels else str(x) for x in df["label"].tolist()]
    fig = go.Figure(
        data=[
            go.Pie(
                labels=labels,
                values=df["value"].tolist(),
                hole=0.62,
                marker=dict(colors=colors[: len(df)]),
                textinfo="percent",
                showlegend=False,
                domain=dict(x=[0.22, 0.78], y=[0.08, 0.88]),
            )
        ]
    )
    fig.update_layout(
        height=290,
        margin=dict(l=50, r=50, t=84, b=8),
        showlegend=False,
        paper_bgcolor="white",
        annotations=[
            dict(text=title, x=0.50, y=1.08, xref="paper", yref="paper", showarrow=False, font=dict(size=24)),
        ],
    )
    return fig


def _legend_html(title: str, df: pd.DataFrame, uppercase_labels: bool = False) -> str:
    colors = [
        CI_COLORS["COLOR_1"],
        CI_COLORS["COLOR_2"],
        CI_COLORS["COLOR_3"],
        CI_COLORS["COLOR_5"],
        CI_COLORS["COLOR_4"],
        CI_COLORS["COLOR_6"],
    ]
    items = []
    for i, r in enumerate(df.itertuples(index=False)):
        label = str(r.label).upper() if uppercase_labels else str(r.label)
        items.append(
            f"<div style='display:flex;align-items:center;gap:8px;margin:2px 0;font-size:13px;'>"
            f"<span style='width:10px;height:10px;border-radius:99px;background:{colors[i % len(colors)]};display:inline-block;'></span>"
            f"<span>{label}</span>"
            f"<span style='margin-left:auto;color:#666;'>{float(r.value):.2f}%</span>"
            f"</div>"
        )
    return (
        f"<div style='border:1px solid rgba(0,0,0,0.08);border-radius:10px;padding:8px 10px;'>"
        f"<div style='font-weight:700;margin-bottom:4px;font-size:15px;'>{title}</div>{''.join(items)}</div>"
    )


def build_backlinks_block(ctx: ReportContext, sistrix_api_key: str, openai_api_key: str) -> dict:
    use_fake = DEV_MODE and not SISTRIX_BACKLINKS_LIVE

    if use_fake:
        links_total = 181
        ref_domains = 169
        hostnames = 172
        ips = 31
        networks = 28
        tlds, countries = _fallback_dist_from_domains(ctx)
        source_line = "Quelle: Demo-Daten"
    else:
        try:
            data = _fetch_links_overview(ctx, sistrix_api_key)
        except Exception as e:
            if "domain not found" in str(e).lower():
                tlds, countries = _fallback_dist_from_domains(ctx)
                pre_html = (
                    "<div style='font-size:14px; line-height:1.6; margin-top:6px;'>"
                    "Für diese Domain konnten in SISTRIX keine auswertbaren Backlink-Daten gefunden werden."
                    "</div>"
                    + _kpi_overview_html(
                        ref_domains=0,
                        links_total=0,
                        hostnames=0,
                        ips=0,
                        networks=0,
                    )
                    + "<div style='margin-top:8px; color:#666; font-size:12px;'>Quelle: SISTRIX links.overview (nicht verfügbar)</div>"
                )
                fig = _dual_donut(tlds=tlds, countries=countries)
                post_html = (
                    "<div style='display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-top:6px;'>"
                    + _legend_html("TLDs", tlds, uppercase_labels=False)
                    + _legend_html("Länder", countries, uppercase_labels=True)
                    + "</div>"
                )
                return {
                    "id": "backlinks",
                    "title": "Backlink-Übersicht",
                    "accent_token": "COLOR_5",
                    "pre_html": pre_html,
                    "fig": fig,
                    "pdf_fig": _single_donut_pdf("TLDs", tlds, uppercase_labels=False),
                    "pdf_mid_html": (
                        "<div style='margin-top:8px; margin-bottom:22px;'>"
                        + _legend_html("TLDs", tlds, uppercase_labels=False)
                        + "</div>"
                    ),
                    "post_html": post_html,
                    "pdf_post_fig": _single_donut_pdf("Länder", countries, uppercase_labels=True),
                    "pdf_post_html": (
                        "<div style='margin-top:8px;'>"
                        + _legend_html("Länder", countries, uppercase_labels=True)
                        + "</div>"
                    ),
                    "comment_title": "Einordnung",
                    "comment": "Für diese Domain sind aktuell keine belastbaren Backlink-Daten in SISTRIX verfügbar.",
                    "kpis": {
                        "backlinks": 0,
                        "referring_domains": 0,
                        "hostnames": 0,
                        "ips": 0,
                        "networks": 0,
                    },
                }
            return {
                "id": "backlinks",
                "title": "Backlink-Übersicht",
                "accent_token": "COLOR_5",
                "error": f"SISTRIX-Fehler bei Backlinks: {e}",
            }

        # Primär: exakt nach links.overview-Schema mappen
        links_total = _extract_overview_num(data, "total")
        ref_domains = _extract_overview_num(data, "domains")
        hostnames = _extract_overview_num(data, "hosts")
        networks = _extract_overview_num(data, "networks")
        ips = _extract_overview_num(data, "class_c")

        # Fallback: generische Heuristik, falls API-Format abweicht
        if links_total is None:
            links_total = _pick_numeric_by_fragments(
                data,
                include_any=("link", "backlink", "linkpop", "total"),
                exclude_any=("percent", "share", "ratio", "rate", "tld", "country", "host", "domain"),
                default=0,
            )
        if ref_domains is None:
            ref_domains = _pick_numeric_by_fragments(
                data,
                include_any=("refdomain", "ref_domain", "referring_domain", "linking_domain", "domainpop", "refdom", "domains"),
                exclude_any=("percent", "share", "ratio", "rate"),
                default=0,
            )
        if hostnames is None:
            hostnames = _pick_numeric_by_fragments(
                data,
                include_any=("host",),
                exclude_any=("percent", "share", "ratio", "rate"),
                default=0,
            )
        if ips is None:
            ips = _pick_numeric_by_fragments(
                data,
                include_any=("ips", "ip", "class_c"),
                exclude_any=("percent", "share", "ratio", "rate"),
                default=0,
            )
        if networks is None:
            networks = _pick_numeric_by_fragments(
                data,
                include_any=("network", "subnet", "cblock"),
                exclude_any=("percent", "share", "ratio", "rate"),
                default=0,
            )

        tlds = _extract_distribution(data, kind="tld", max_items=6)
        countries = _extract_distribution(data, kind="country", max_items=6)
        if tlds.empty or countries.empty:
            fallback_tlds, fallback_countries = _fallback_dist_from_domains(ctx)
            if tlds.empty:
                tlds = fallback_tlds
            if countries.empty:
                countries = fallback_countries

        source_line = "Quelle: SISTRIX links.overview"

        # Falls einzelne Werte weiterhin fehlen, direkter Zugriff auf answer[0]-Schema.
        answer0 = None
        ans = data.get("answer")
        if isinstance(ans, list) and ans and isinstance(ans[0], dict):
            answer0 = ans[0]
        if answer0:
            if links_total == 0 and isinstance(answer0.get("total"), list) and answer0["total"]:
                links_total = _num(answer0["total"][0].get("num"), default=0)
            if ref_domains == 0 and isinstance(answer0.get("domains"), list) and answer0["domains"]:
                ref_domains = _num(answer0["domains"][0].get("num"), default=0)
            if hostnames == 0 and isinstance(answer0.get("hosts"), list) and answer0["hosts"]:
                hostnames = _num(answer0["hosts"][0].get("num"), default=0)
            if networks == 0 and isinstance(answer0.get("networks"), list) and answer0["networks"]:
                networks = _num(answer0["networks"][0].get("num"), default=0)
            if ips == 0 and isinstance(answer0.get("class_c"), list) and answer0["class_c"]:
                ips = _num(answer0["class_c"][0].get("num"), default=0)

    pre_html = (
        "<div style='font-size:14px; line-height:1.6; margin-top:6px;'>"
        "Die Backlink-Übersicht zeigt, wie Ihre Domain extern verlinkt wird: "
        "Anzahl und Qualität der Linkquellen sowie deren Verteilung nach TLDs und Ländern."
        "</div>"
        + _kpi_overview_html(
            ref_domains=ref_domains,
            links_total=links_total,
            hostnames=hostnames,
            ips=ips,
            networks=networks,
        )
        + f"<div style='margin-top:8px; color:#666; font-size:12px;'>{source_line}</div>"
    )

    fig = _dual_donut(tlds=tlds, countries=countries)
    post_html = (
        "<div style='display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-top:6px;'>"
        + _legend_html("TLDs", tlds, uppercase_labels=False)
        + _legend_html("Länder", countries, uppercase_labels=True)
        + "</div>"
    )
    comment = (
        "Die Linkstruktur zeigt die aktuelle Offpage-Basis der Domain. "
        "Wichtig für die nächsten Schritte sind vor allem ein stetiger Ausbau verweisender Domains "
        "und eine ausgewogene Verteilung der Linkquellen."
    )

    return {
        "id": "backlinks",
        "title": "Backlink-Übersicht",
        "accent_token": "COLOR_5",
        "pre_html": pre_html,
        "fig": fig,
        "pdf_fig": _single_donut_pdf("TLDs", tlds, uppercase_labels=False),
        "pdf_mid_html": (
            "<div style='margin-top:8px; margin-bottom:22px;'>"
            + _legend_html("TLDs", tlds, uppercase_labels=False)
            + "</div>"
        ),
        "post_html": post_html,
        "pdf_post_fig": _single_donut_pdf("Länder", countries, uppercase_labels=True),
        "pdf_post_html": (
            "<div style='margin-top:8px;'>"
            + _legend_html("Länder", countries, uppercase_labels=True)
            + "</div>"
        ),
        "comment_title": "Einordnung",
        "comment": comment,
        "kpis": {
            "backlinks": links_total,
            "referring_domains": ref_domains,
            "hostnames": hostnames,
            "ips": ips,
            "networks": networks,
        },
    }
