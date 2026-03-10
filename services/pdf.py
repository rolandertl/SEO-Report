import subprocess
import sys


def _install_playwright_chromium() -> None:
    # Streamlit Cloud installiert Python-Pakete aus requirements.txt,
    # aber nicht automatisch die Playwright-Browser-Binaries.
    subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def html_to_pdf(html: str, out_path: str) -> None:
    """
    Render HTML -> PDF using Playwright.
    Playwright is imported lazily, so the app can run without it in DEV_MODE.
    """
    try:
        from playwright.sync_api import sync_playwright  # lazy import
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "PDF-Export benötigt das Paket 'playwright'. "
            "Installiere es mit: pip install playwright"
        ) from exc

    def _render_once() -> None:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.set_content(html, wait_until="networkidle")
            page.pdf(path=out_path, format="A4", print_background=True)
            browser.close()

    try:
        _render_once()
    except Exception as exc:
        msg = str(exc)
        if "Executable doesn't exist" in msg or "Failed to launch" in msg:
            try:
                _install_playwright_chromium()
            except Exception as install_exc:
                raise RuntimeError(
                    "Playwright-Browser fehlt auf dem Server und konnte nicht automatisch installiert werden."
                ) from install_exc
            _render_once()
            return
        raise
