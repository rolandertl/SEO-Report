import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date, datetime
from dateutil.relativedelta import relativedelta
from jinja2 import Environment, FileSystemLoader
import requests

from services.sistrix import call as sistrix_call
from services.llm import generate_comment
from services.pdf import html_to_pdf

# ----------------------------
# Streamlit config
# ----------------------------
st.set_page_config(page_title="SEO-Report", layout="wide")
st.title("SEO-Report")
st.caption("Google.at · Mobile")


# ----------------------------
# Helpers
# ----------------------------
def require_secrets() -> bool:
    """Return True if secrets are available, else show a helpful error."""
    needed = ["SISTRIX_API_KEY", "OPENAI_API_KEY"]
    missing = [k for k in needed if k not in st.secrets]
    if missing:
        st.error(
            "Secrets fehlen: "
            + ", ".join(missing)
            + "\n\nLege eine Datei `.streamlit/secrets.toml` an mit:\n"
            + 'SISTRIX_API_KEY="..."\nOPENAI_API_KEY="..."'
        )
        return False
    return True


def safe_domain(raw: str) -> str:
    """Normalize domain input a bit (remove protocol/path)."""
    if not raw:
        return ""
    d = raw.strip().lower()
    d = d.replace("https://", "").replace("http://", "")
    d = d.split("/")[0]
    return d


def parse_sistrix_timeseries(data: dict) -> pd.DataFrame:
    """
    Robustly extract a timeseries of {date, value} from SISTRIX JSON.
    We walk the JSON and collect dicts containing 'date' and 'value' (or 'visibilityindex').
    """
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

    # typical top-level container is "answer"
    walk(data.get("answer", data))

    df = pd.DataFrame(rows).drop_duplicates()
    if df.empty:
        return df

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).sort_values("date")
    return df


def render_report_html(domain: str, start_date: date, end_date: date, chart_html: str, comment: str) -> str:
    env = Environment(loader=FileSystemLoader("templates"))
    tpl = env.get_template("report.html")
    return tpl.render(
        title="SEO-Report",
        domain=domain,
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        chart_html=chart_html,
        comment=comment,
    )


# ----------------------------
# Data fetching (cached)
# ----------------------------
@st.cache_data(show_spinner=False)
def fetch_credits() -> dict:
    api_key = st.secrets["SISTRIX_API_KEY"]
    return sistrix_call("credits", api_key=api_key, params={})

from dateutil.relativedelta import relativedelta

@st.cache_data(show_spinner=False)
def fetch_visibility_history(domain: str, start_date: date, end_date: date) -> pd.DataFrame:
    """
    Fetch visibility index in chunks (monthly) to avoid timeouts.
    """
    api_key = st.secrets["SISTRIX_API_KEY"]
    all_parts = []

    cur = date(start_date.year, start_date.month, 1)
    end_month = date(end_date.year, end_date.month, 1)

    while cur <= end_month:
        # choose a representative date within the month (15th) – tends to work well
        mid = date(cur.year, cur.month, min(15, 28))

        data = sistrix_call(
            "domain.visibilityindex",
            api_key=api_key,
            params={
                "domain": domain,
                "country": "at",
                "mobile": "1",
                "date": mid.isoformat(),  # monthly point request
            },
        )

        df_part = parse_sistrix_timeseries(data)
        if not df_part.empty:
            all_parts.append(df_part)

        cur = (cur + relativedelta(months=1))

    if not all_parts:
        return pd.DataFrame(columns=["date", "value"])

    df = pd.concat(all_parts, ignore_index=True).drop_duplicates()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).sort_values("date")

    # final filter to exact range
    df = df[(df["date"].dt.date >= start_date) & (df["date"].dt.date <= end_date)]
    return df



# ----------------------------
# Sidebar UI
# ----------------------------
with st.sidebar:
    domain_raw = st.text_input("Domain", placeholder="z.B. example.at")

    col1, col2 = st.columns(2)

    today = date.today()

    # letzter abgeschlossener Monat (Vormonat)
    last_completed_month_end = (today.replace(day=1) - relativedelta(days=1))
    last_completed_month_start = last_completed_month_end.replace(day=1)

    # 1. des 3. vollkommen vergangenen Monats
    default_from = (last_completed_month_start - relativedelta(months=2))
    default_to = last_completed_month_end

    start_date = col1.date_input("Zeitraum von", value=default_from)
    end_date = col2.date_input("Zeitraum bis", value=default_to)

    run = st.button("Report generieren", type="primary")
# ----------------------------
# Main flow
# ----------------------------
if not require_secrets():
    st.stop()

domain = safe_domain(domain_raw)

if run:
    if not domain:
        st.error("Bitte eine Domain eingeben.")
        st.stop()

    if start_date > end_date:
        st.error("Der Zeitraum ist ungültig (Startdatum ist nach dem Enddatum).")
        st.stop()

    # 1) quick connectivity / auth check
    with st.spinner("SISTRIX-Verbindung wird geprüft…"):
        try:
            _ = fetch_credits()
        except requests.exceptions.ReadTimeout:
            st.error("SISTRIX API Timeout beim Credits-Check. Bitte erneut versuchen.")
            st.stop()
        except Exception as e:
            st.error(f"SISTRIX-Fehler beim Credits-Check: {e}")
            st.stop()

    # 2) fetch history
    with st.spinner("Sichtbarkeitsdaten werden geladen…"):
        try:
            df = fetch_visibility_history(domain, start_date, end_date)
        except requests.exceptions.ReadTimeout:
            st.error("SISTRIX API Timeout beim Laden der Sichtbarkeit. Bitte erneut versuchen.")
            st.stop()
        except Exception as e:
            st.error(f"SISTRIX-Fehler beim Laden der Sichtbarkeit: {e}")
            st.stop()

   # df = filter_df_by_range(df_all, start_date, end_date)

    if df.empty:
        st.warning(
            "Keine Sichtbarkeitsdaten im gewählten Zeitraum gefunden.\n\n"
            "Tipp: Prüfe Domain-Schreibweise oder wähle einen größeren Zeitraum."
        )
        st.stop()

    # 3) chart
    import plotly.graph_objects as go

fig = go.Figure()

fig.add_trace(
    go.Scatter(
        x=df["date"],
        y=df["value"],
        mode="lines",
        line=dict(
            color="#EE316B",
            width=3
        ),
        fill="tozeroy",
        fillcolor="rgba(238, 49, 107, 0.15)",
        hovertemplate="%{y:.3f}<extra></extra>"
    )
)

fig.update_layout(
    height=380,
    margin=dict(l=10, r=10, t=10, b=10),
    plot_bgcolor="white",
    paper_bgcolor="white",
    xaxis=dict(
        showgrid=False,
        zeroline=False
    ),
    yaxis=dict(
        showgrid=True,
        gridcolor="rgba(0,0,0,0.05)",
        zeroline=False
    )
)


    st.subheader("Preview")
    st.plotly_chart(fig, use_container_width=True)

    # 4) build facts for LLM
    start_val = float(df.iloc[0]["value"])
    end_val = float(df.iloc[-1]["value"])
    delta_pct = (end_val - start_val) / start_val * 100 if start_val != 0 else None

    facts = {
        "market": "Google.at",
        "device": "Mobile",
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "start_value": round(start_val, 6),
        "end_value": round(end_val, 6),
        "delta_pct": round(delta_pct, 2) if delta_pct is not None else None,
        "note": "Sichtbarkeitsindex-Verlauf (SISTRIX).",
    }

    # 5) LLM comment
    with st.spinner("KI-Statement wird erstellt…"):
        try:
            comment = generate_comment(
                api_key=st.secrets["OPENAI_API_KEY"],
                title="Sichtbarkeitsindex (Google.at · Mobile)",
                facts=facts,
            )
        except Exception as e:
            # fallback: do not break report generation
            comment = (
                "KI-Statement konnte gerade nicht erzeugt werden. "
                "Bitte später erneut versuchen."
            )
            st.warning(f"LLM-Fehler: {e}")

    st.markdown("**Erklärung der Sichtbarkeitskurve:**")
    st.write(comment)

    # 6) Render HTML report
    chart_html = fig.to_html(include_plotlyjs="cdn", full_html=False)
    report_html = render_report_html(domain, start_date, end_date, chart_html, comment)

    # 7) Downloads
    st.download_button(
        "HTML herunterladen",
        data=report_html.encode("utf-8"),
        file_name=f"seo-report_{domain}_{start_date}_{end_date}.html",
        mime="text/html",
    )

    if st.button("PDF exportieren"):
        pdf_path = f"/tmp/seo-report_{domain}_{start_date}_{end_date}.pdf"
        with st.spinner("PDF wird erzeugt…"):
            try:
                html_to_pdf(report_html, pdf_path)
            except Exception as e:
                st.error(f"PDF-Export fehlgeschlagen: {e}")
                st.stop()

        with open(pdf_path, "rb") as f:
            st.download_button(
                "PDF herunterladen",
                data=f.read(),
                file_name=f"seo-report_{domain}_{start_date}_{end_date}.pdf",
                mime="application/pdf",
            )
