import streamlit as st
from datetime import date, datetime
from dateutil.relativedelta import relativedelta
from jinja2 import Environment, FileSystemLoader
from pathlib import Path
from urllib.parse import quote
import hashlib
import time
import hmac
from concurrent.futures import ThreadPoolExecutor

from core.context import ReportContext
from core.report_builder import build_report
from core.config import CI_COLORS, BRAND


st.set_page_config(page_title="SEO-Report", layout="wide")
# --- SESSION STATE INIT BEGIN ---
if "blocks" not in st.session_state:
    st.session_state["blocks"] = None

if "comment_overrides" not in st.session_state:
    st.session_state["comment_overrides"] = {}
if "report_title_override" not in st.session_state:
    st.session_state["report_title_override"] = "SEO-Report"
# --- SESSION STATE INIT END ---


def require_secrets() -> bool:
    needed = ["SISTRIX_API_KEY", "OPENAI_API_KEY", "APP_ACCESS_PIN"]
    missing = [k for k in needed if k not in st.secrets]
    if missing:
        st.error(
            "Secrets fehlen: "
            + ", ".join(missing)
            + "\n\nLege eine Datei `.streamlit/secrets.toml` an mit:\n"
            + 'SISTRIX_API_KEY="..."\nOPENAI_API_KEY="..."\nAPP_ACCESS_PIN="123456789"'
        )
        return False
    return True


def require_access_pin() -> bool:
    if "is_unlocked" not in st.session_state:
        st.session_state["is_unlocked"] = False

    if st.session_state["is_unlocked"]:
        return True

    expected_raw = str(st.secrets.get("APP_ACCESS_PIN", "")).strip()
    expected = "".join(ch for ch in expected_raw if ch.isdigit())
    if len(expected) != 9:
        st.error("APP_ACCESS_PIN in den Secrets ist ungültig. Bitte exakt 9 Ziffern setzen.")
        return False
    st.title("Zugriffsschutz")
    st.caption("Bitte 9-stellige PIN eingeben")
    c1, c2 = st.columns([2, 3])
    with c1:
        pin_raw = st.text_input("PIN", value="", type="password", max_chars=9)
    pin = "".join(ch for ch in (pin_raw or "") if ch.isdigit())
    if st.button("Freischalten", type="primary"):
        if len(pin.strip()) != 9 or not pin.strip().isdigit():
            st.error("Die PIN muss 9-stellig und numerisch sein.")
        elif hmac.compare_digest(pin.strip(), expected):
            st.session_state["is_unlocked"] = True
            st.rerun()
        else:
            st.error("PIN ist nicht korrekt.")

    return False


def safe_domain(raw: str) -> str:
    if not raw:
        return ""
    d = raw.strip().lower()
    d = d.replace("https://", "").replace("http://", "")
    d = d.split("/")[0]
    if d.startswith("www."):
        d = d[4:]
    return d


def default_date_range():
    """
    Default:
    - VON: 1. des 3. vollkommen vergangenen Monats
    - BIS: letzter Tag des letzten abgeschlossenen Monats
    Beispiel Mitte Februar:
      letzter abgeschlossener Monat = Jänner
      VON = 1. November
      BIS = 31. Jänner
    """
    today = date.today()
    last_completed_month_end = today.replace(day=1) - relativedelta(days=1)
    last_completed_month_start = last_completed_month_end.replace(day=1)
    default_from = last_completed_month_start - relativedelta(months=2)
    default_to = last_completed_month_end
    return default_from, default_to


def render_loading_card(line: str) -> str:
    return f"""
<style>
.report-loader {{
  border: 1px solid rgba(238, 49, 107, 0.25);
  border-radius: 14px;
  padding: 18px 18px 14px 18px;
  background: linear-gradient(180deg, rgba(238,49,107,0.06), rgba(0,185,228,0.05));
  margin: 8px 0 18px 0;
}}
.report-loader-head {{
  display: flex;
  align-items: center;
  gap: 12px;
}}
.report-loader-spinner {{
  width: 22px;
  height: 22px;
  border-radius: 50%;
  border: 3px solid rgba(64,64,65,0.2);
  border-top-color: #EE316B;
  animation: report-spin 0.85s linear infinite;
  flex: 0 0 auto;
}}
.report-loader-text {{
  font-size: 16px;
  font-weight: 600;
  color: #2f2f35;
  line-height: 1.35;
}}
.report-loader-bar {{
  margin-top: 12px;
  height: 6px;
  border-radius: 999px;
  overflow: hidden;
  background: rgba(64,64,65,0.12);
}}
.report-loader-bar-inner {{
  height: 100%;
  width: 36%;
  border-radius: 999px;
  background: linear-gradient(90deg, #EE316B, #00B9E4);
  animation: report-slide 1.8s ease-in-out infinite;
}}
@keyframes report-spin {{
  from {{ transform: rotate(0deg); }}
  to {{ transform: rotate(360deg); }}
}}
@keyframes report-slide {{
  0% {{ transform: translateX(-25%); }}
  50% {{ transform: translateX(155%); }}
  100% {{ transform: translateX(-25%); }}
}}
</style>
<div class="report-loader">
  <div class="report-loader-head">
    <div class="report-loader-spinner"></div>
    <div class="report-loader-text">{line}</div>
  </div>
  <div class="report-loader-bar"><div class="report-loader-bar-inner"></div></div>
</div>
"""


def render_report_html(domain: str, start_date: date, end_date: date, blocks: list[dict]) -> str:
    blocks = normalize_blocks(blocks)
    env = Environment(loader=FileSystemLoader("templates"))
    tpl = env.get_template("report.html")
    logo_data_uri = ""
    flower_logo_data_uri = ""
    logo_path = Path("assets/logo.svg")
    if logo_path.exists():
        svg = logo_path.read_text(encoding="utf-8")
        logo_data_uri = f"data:image/svg+xml;utf8,{quote(svg)}"
    flower_logo_path = Path("assets/blume.svg")
    if flower_logo_path.exists():
        flower_svg = flower_logo_path.read_text(encoding="utf-8")
        flower_logo_data_uri = f"data:image/svg+xml;utf8,{quote(flower_svg)}"

    blocks_for_template: list[dict] = []

    for b in blocks:
        overrides = st.session_state.get("comment_overrides", {})
        block_id = (b.get("id") or b.get("title") or "block").replace(" ", "_").lower()
        if block_id in overrides:
            b = {**b, "comment": overrides[block_id]}

        if not isinstance(b, dict):
            continue

        # Fehlerblöcke unverändert durchreichen
        if b.get("error"):
            blocks_for_template.append(b)
            continue

        fig = b.get("pdf_fig", b.get("fig"))
        chart_html = ""
        if fig is not None:
            chart_html = fig.to_html(include_plotlyjs="cdn", full_html=False)
        post_fig = b.get("pdf_post_fig", b.get("post_fig"))
        post_chart_html = ""
        mid_html = b.get("pdf_mid_html", b.get("mid_html", ""))
        post_html = b.get("pdf_post_html", b.get("post_html", ""))
        
        if post_fig is not None:
         post_chart_html = post_fig.to_html(include_plotlyjs="cdn", full_html=False)

        # Default: nicht bunt → nur 1 Akzentfarbe (primary)
        accent_token = b.get("accent_token", BRAND["primary"])
        accent_color = CI_COLORS.get(accent_token, CI_COLORS[BRAND["primary"]])

                # Override KI-Text (falls im UI bearbeitet)
        overrides = st.session_state.get("comment_overrides", {})
        block_id = b.get("id", b.get("title", "block")).replace(" ", "_").lower()
        if block_id in overrides:
            b = {**b, "comment": overrides[block_id]}
        
        blocks_for_template.append(
            {
                **b,
                "chart_html": chart_html,
                "accent_color": accent_color,
                "post_chart_html": post_chart_html,
                "mid_html": mid_html,
                "post_html": post_html,
            }
        )

    return tpl.render(
        title=st.session_state.get("report_title_override", "SEO-Report"),
        domain=domain,
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        blocks=blocks_for_template,
        toc_items=[toc_description(b.get("id", ""), b.get("title", "")) for b in blocks if toc_description(b.get("id", ""), b.get("title", ""))],
        colors=CI_COLORS,
        logo_data_uri=logo_data_uri,
        flower_logo_data_uri=flower_logo_data_uri,
    )


def pdf_toggle_key(section_id: str) -> str:
    return f"pdf_visible_{section_id}"


def pdf_section_visible(section_id: str) -> bool:
    key = pdf_toggle_key(section_id)
    if key not in st.session_state:
        st.session_state[key] = True
    return bool(st.session_state[key])


def toc_description(block_id: str, title: str) -> str:
    mapping = {
        "visibility": "Sichtbarkeitsindex – Entwicklung der organischen Sichtbarkeit.",
        "top_urls": "Top URLs – Stärkste Seiten nach Sichtbarkeitsbeitrag.",
        "keyword_profile": "Keyword-Verlauf – Entwicklung der rankenden Keywords.",
        "interesting_rankings": "Aktuelle Rankings – Wichtigste Positionen.",
        "ranking-gewinner": "Gewinner-Keywords – Positive Ranking-Entwicklung.",
        "ranking_gewinner": "Gewinner-Keywords – Positive Ranking-Entwicklung.",
        "neu_hinzugewonnene_google-rankings": "Neueinsteiger – Neue Rankings im Zeitraum.",
        "neu_hinzugewonnene_google_rankings": "Neueinsteiger – Neue Rankings im Zeitraum.",
        "ranking-veränderungen_mit_rückgang": "Verlierer – Rückläufige Positionen.",
        "ranking-veränderungen-mit-rückgang": "Verlierer – Rückläufige Positionen.",
        "ranking_veränderungen_mit_rückgang": "Verlierer – Rückläufige Positionen.",
        "local_seo_summary": "Local SEO – Profilvollständigkeit, Verzeichnisse und Bewertungsverteilung.",
        "google_presence": "Google Präsenz – Impressionen, Klicks und Verlauf.",
        "google_reviews": "Google Bewertungen – Rating, Anzahl und Antwortrate.",
        "technical_quick_check": "Technischer Quick-Check – Broken Links, SSL, Sitemap und robots.txt.",
        "mobile_display": "Mobile Darstellung – Smartphone-Check und Nutzerfreundlichkeit.",
        "ai_overview": "KI-Overview – Sichtbarkeit der Marke aus KI-Perspektive.",
        "backlinks": "Backlinks – Entwicklung des Linkprofils.",
    }
    if block_id in mapping:
        return mapping[block_id]
    title_map = {
        "Ranking-Gewinner": "Gewinner-Keywords – Positive Ranking-Entwicklung.",
        "Neu hinzugewonnene Google-Rankings": "Neueinsteiger – Neue Rankings im Zeitraum.",
        "Ranking-Veränderungen mit Rückgang": "Verlierer – Rückläufige Positionen.",
    }
    return title_map.get(title, "")


def normalize_blocks(blocks: list[dict] | None) -> list[dict]:
    normalized: list[dict] = []
    for b in blocks or []:
        if not isinstance(b, dict):
            continue
        if b.get("id") != "local_seo_fdm":
            normalized.append(b)
            continue

        normalized.extend(
            [
                {
                    "id": "local_seo_summary",
                    "title": "Local SEO – Auswertung Ihres Unternehmensprofils",
                    "accent_token": b.get("accent_token", "COLOR_2"),
                    "pre_html": (b.get("pdf_intro_html") or "") + (b.get("pdf_summary_html") or ""),
                },
                {
                    "id": "google_presence",
                    "title": "Google Präsenz",
                    "accent_token": b.get("accent_token", "COLOR_2"),
                    "pre_html": b.get("pdf_google_presence_html")
                    or "<div style='font-size:14px; line-height:1.6; color:#666;'>Diese Auswertung setzt ein passendes Firmendaten-Manager-Unternehmensprofil voraus.</div>",
                    "fig": b.get("fig"),
                    "post_fig": b.get("post_fig"),
                },
                {
                    "id": "google_reviews",
                    "title": "Google Bewertungen",
                    "accent_token": b.get("accent_token", "COLOR_2"),
                    "pre_html": b.get("pdf_reviews_html") or "",
                },
                {
                    "id": "technical_quick_check",
                    "title": "Technischer Quick-Check",
                    "accent_token": b.get("accent_token", "COLOR_2"),
                    "pre_html": b.get("pdf_technical_html")
                    or "<div style='font-size:14px; line-height:1.6; color:#666;'>Für diesen Abschnitt liegen aktuell keine Daten vor.</div>",
                },
                {
                    "id": "mobile_display",
                    "title": "Mobile Darstellung",
                    "accent_token": b.get("accent_token", "COLOR_2"),
                    "pre_html": b.get("pdf_mobile_html")
                    or "<div style='font-size:14px; line-height:1.6; color:#666;'>Für diesen Abschnitt liegen aktuell keine Daten vor.</div>",
                },
            ]
        )
    return normalized


def build_pdf_blocks(blocks: list[dict]) -> list[dict]:
    return [
        b for b in normalize_blocks(blocks)
        if isinstance(b, dict) and pdf_section_visible(b.get("id", ""))
    ]


if not require_secrets():
    st.stop()

if not require_access_pin():
    st.stop()

c_title_1, c_title_2 = st.columns([0.92, 0.08])
with c_title_1:
    st.title(st.session_state.get("report_title_override", "SEO-Report"))
    st.caption("Google.at · Mobile")
with c_title_2:
    if "edit_report_title" not in st.session_state:
        st.session_state["edit_report_title"] = False
    if st.button("✏️", key="btn_report_title", help="Report-Titel bearbeiten"):
        st.session_state["edit_report_title"] = not st.session_state["edit_report_title"]

if st.session_state.get("edit_report_title", False):
    new_report_title = st.text_input(
        "Report-Titel",
        value=st.session_state.get("report_title_override", "SEO-Report"),
        key="report_title_input",
    )
    t1, t2 = st.columns(2)
    with t1:
        if st.button("Titel speichern", key="save_report_title"):
            st.session_state["report_title_override"] = (new_report_title or "").strip() or "SEO-Report"
            st.session_state["edit_report_title"] = False
            st.rerun()
    with t2:
        if st.button("Titel zurücksetzen", key="reset_report_title"):
            st.session_state["report_title_override"] = "SEO-Report"
            st.session_state["edit_report_title"] = False
            st.rerun()


# -----------------------------
# Sidebar
# -----------------------------
with st.sidebar:
    domain_raw = st.text_input("Domain (ohne www)", placeholder="z.B. example.at")
    insites_report_id = st.text_input(
        "Insites Report-ID",
        value=st.session_state.get("insites_report_id", ""),
        help="Optional: Report-ID aus Insites zur Datenanreicherung.",
    )
    uberall_location_id = st.text_input(
        "FDM Location-ID (optional)",
        value="",
        help="Wenn vorhanden, verwenden wir die Location-ID.",
    )

    default_from, default_to = default_date_range()
    col1, col2 = st.columns(2)
    start_date = col1.date_input("Zeitraum von", value=default_from)
    end_date = col2.date_input("Zeitraum bis", value=default_to)

    st.markdown("---")
    st.markdown("### Google Fallback")

    business_name = st.text_input(
        "Unternehmensname",
        value="",
        help="Für Google Bewertungen erforderlich.",
    )

    street = st.text_input(
        "Straße + Hausnummer",
        value="",
        help="Für Google Bewertungen erforderlich.",
    )

    postal_code = st.text_input(
        "PLZ",
        value="",
        help="Optional für präzisere Google-Suche.",
    )

    st.markdown("---")
    run = st.button("Report generieren", type="primary")
    st.caption("Version 1.0.18")


domain = safe_domain(domain_raw)
st.session_state["insites_report_id"] = (insites_report_id or "").strip()


# Wir merken uns den letzten fertigen HTML-Report, damit PDF-Export stabil ist
if "report_html" not in st.session_state:
    st.session_state["report_html"] = None
if "report_pdf_key" not in st.session_state:
    st.session_state["report_pdf_key"] = None
if "report_pdf_bytes" not in st.session_state:
    st.session_state["report_pdf_bytes"] = None


if run:
    if not domain:
        st.error("Bitte eine Domain eingeben.")
        st.stop()

    if start_date > end_date:
        st.error("Der Zeitraum ist ungültig (Startdatum ist nach dem Enddatum).")
        st.stop()

    # Uberall-Eingaben nur sammeln (noch keine harten Pflichtfelder, damit du reporten kannst)
    uberall_input = {
        "location_id": uberall_location_id.strip(),
        "name": business_name.strip(),
        "street": street.strip(),
        "postal_code": postal_code.strip(),
        "insites_report_id": st.session_state.get("insites_report_id", "").strip(),
    }
    st.session_state["uberall_input"] = uberall_input

    ctx = ReportContext(domain=domain, start_date=start_date, end_date=end_date)

    loading_lines = [
        "Wir sortieren gerade das Google-Universum nach Ihrer Domain …",
        "Rankings werden poliert und auf Hochglanz gebracht …",
        "Feenstaub wird über die Suchergebnisse gestreut ✨",
        "Die Keywords machen sich für ihren großen Auftritt bereit …",
        "Wir überzeugen Google kurz noch von Ihrer Großartigkeit …",
        "Backlinks werden gezählt (und nochmal nachgezählt) …",
        "Der Sichtbarkeitsindex trinkt noch schnell einen Espresso …",
        "Die SERPs werden einmal freundlich durchgekämmt …",
        "Lokale Signale werden auf Empfang gestellt …",
        "Ihr SEO-Report nimmt gerade Form an – fast geschafft!",
    ]

    status_box = st.empty()
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            build_report,
            ctx,
            st.secrets["SISTRIX_API_KEY"],
            st.secrets["OPENAI_API_KEY"],
            st.session_state.get("uberall_input", {}),
            st.secrets.get("UBERALL_API_KEY", ""),
            st.secrets.get("GOOGLE_PLACES_API_KEY", ""),
            st.secrets.get("INSITES_API_KEY", ""),
        )

        i = 0
        while not future.done():
            status_box.markdown(
                render_loading_card(loading_lines[i % len(loading_lines)]),
                unsafe_allow_html=True,
            )
            i += 1
            time.sleep(5.5)

        blocks = future.result()
    status_box.empty()

     # --- REPORT PREVIEW + EDITABLE COMMENTS BEGIN ---

    # Blocks + Kontext dauerhaft speichern, damit beim ✏️-Klick nichts verschwindet
    st.session_state["blocks"] = blocks
    st.session_state["report_domain"] = domain
    st.session_state["report_start_date"] = start_date
    st.session_state["report_end_date"] = end_date

    # Store Uberall input (falls du es schon hast)
    st.session_state["uberall_input"] = st.session_state.get("uberall_input", {})

    # Kommentar-Overrides Speicher
    if "comment_overrides" not in st.session_state:
        st.session_state["comment_overrides"] = {}

# --- REPORT PREVIEW OUTSIDE RUN BEGIN ---
blocks = normalize_blocks(st.session_state.get("blocks"))
report_domain = st.session_state.get("report_domain")
report_start_date = st.session_state.get("report_start_date")
report_end_date = st.session_state.get("report_end_date")

if blocks:
    # Report-HTML bei jedem Rerun neu erzeugen, damit manuelle Kommentar-Edits im Export landen.
    if report_domain and report_start_date and report_end_date:
        st.session_state["report_html"] = render_report_html(
            report_domain,
            report_start_date,
            report_end_date,
            build_pdf_blocks(blocks),
        )

    st.markdown("## Vorschau")
    st.markdown(
        """
<style>
.preview-section-title {
  font-size: 30px;
  font-weight: 700;
  margin: 12px 0 8px 0;
  padding-bottom: 6px;
  border-bottom: 2px solid #EE316B;
  line-height: 1.2;
}
input[type="checkbox"] {
  accent-color: #2DBE8D !important;
}
.stToggle div[data-baseweb="checkbox"]:has(input:checked) > label > div:first-child,
.stToggle label[data-baseweb="checkbox"]:has(input:checked) > div:first-child,
.stToggle div[data-baseweb="switch"]:has(input:checked) > label > div:first-child,
.stToggle label[data-baseweb="switch"]:has(input:checked) > div:first-child {
  background-color: #2DBE8D !important;
  border-color: #2DBE8D !important;
}
.stToggle div[data-baseweb="checkbox"]:has(input:not(:checked)) > label > div:first-child,
.stToggle label[data-baseweb="checkbox"]:has(input:not(:checked)) > div:first-child,
.stToggle div[data-baseweb="switch"]:has(input:not(:checked)) > label > div:first-child,
.stToggle label[data-baseweb="switch"]:has(input:not(:checked)) > div:first-child {
  background-color: #C9CED6 !important;
  border-color: #C9CED6 !important;
}
</style>
""",
        unsafe_allow_html=True,
    )

    def render_section_header(title: str, section_id: str):
        c1, c2 = st.columns([0.88, 0.12])
        with c1:
            st.markdown(
                f"<div class='preview-section-title'>{title}</div>",
                unsafe_allow_html=True,
            )
        with c2:
            st.toggle("PDF", value=pdf_section_visible(section_id), key=pdf_toggle_key(section_id), label_visibility="collapsed")

    for b in blocks:
        if not isinstance(b, dict):
            st.error("Ein Report-Block ist leer (None). Bitte Block-Builder prüfen.")
            continue

        render_section_header(b.get("title", "Block"), b.get("id", "block"))

        if b.get("error"):
            st.warning(b["error"])
            continue

        if b.get("pre_html"):
            st.markdown(b["pre_html"], unsafe_allow_html=True)

        if b.get("fig") is not None:
            st.plotly_chart(b["fig"], width="stretch")
        if b.get("mid_html"):
            st.markdown(b["mid_html"], unsafe_allow_html=True)

        if b.get("post_fig") is not None:
            st.plotly_chart(b["post_fig"], width="stretch")
        if b.get("post_html"):
            st.markdown(b["post_html"], unsafe_allow_html=True)

        # --- Kommentar + Edit ---
        if b.get("comment"):
            comment_title = b.get("comment_title", "Kommentar")
            block_id = (b.get("id") or b.get("title") or "block").replace(" ", "_").lower()
            default_comment = b.get("comment", "")
            current_comment = st.session_state["comment_overrides"].get(block_id, default_comment)

            c1, c2 = st.columns([0.92, 0.08])
            with c1:
                st.markdown(f"**{comment_title}:**")
            with c2:
                edit_flag_key = f"edit_{block_id}"
                if edit_flag_key not in st.session_state:
                    st.session_state[edit_flag_key] = False

                # WICHTIG: kein st.rerun nötig – Button klickt sowieso rerun
                if st.button("✏️", key=f"btn_{block_id}", help="Text bearbeiten"):
                    st.session_state[edit_flag_key] = not st.session_state[edit_flag_key]

            if st.session_state.get(edit_flag_key, False):
                new_text = st.text_area(
                    "Text bearbeiten",
                    value=current_comment,
                    height=140,
                    key=f"ta_{block_id}",
                )
                s1, s2 = st.columns(2)
                with s1:
                    if st.button("Speichern", key=f"save_{block_id}"):
                        st.session_state["comment_overrides"][block_id] = new_text
                        st.session_state[edit_flag_key] = False
                with s2:
                    if st.button("Abbrechen", key=f"cancel_{block_id}"):
                        st.session_state[edit_flag_key] = False
            else:
                st.write(current_comment)
# --- REPORT PREVIEW OUTSIDE RUN END ---

# Export (nur wenn es einen Report gibt)
if (
    st.session_state.get("report_html")
    and report_domain
    and report_start_date
    and report_end_date
):
    pdf_file_name = f"seo-report_{report_domain}_{report_start_date}_{report_end_date}.pdf"
    report_html = st.session_state["report_html"]
    report_hash = hashlib.sha256(report_html.encode("utf-8")).hexdigest()
    pdf_key = f"{report_domain}|{report_start_date}|{report_end_date}|{report_hash}"

    if st.session_state.get("report_pdf_key") != pdf_key:
        from services.pdf import html_to_pdf
        pdf_path = f"/tmp/{pdf_file_name}"

        try:
            with st.spinner("PDF wird erzeugt…"):
                html_to_pdf(report_html, pdf_path)
            with open(pdf_path, "rb") as f:
                st.session_state["report_pdf_bytes"] = f.read()
            st.session_state["report_pdf_key"] = pdf_key
        except RuntimeError as e:
            st.error(str(e))
            st.info(
                "Wenn du bereits `pip install -r requirements.txt` ausgeführt hast, "
                "fehlt oft noch der Browser: `playwright install chromium`."
            )
            st.stop()
        except Exception as e:
            st.error(f"PDF-Export fehlgeschlagen: {e}")
            st.stop()

    if st.session_state.get("report_pdf_bytes"):
        st.download_button(
            "PDF exportieren",
            data=st.session_state["report_pdf_bytes"],
            file_name=pdf_file_name,
            mime="application/pdf",
        )
