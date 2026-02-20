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

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.set_content(html, wait_until="networkidle")
            page.pdf(path=out_path, format="A4", print_background=True)
            browser.close()
    except Exception as exc:
        msg = str(exc)
        if "Executable doesn't exist" in msg or "Failed to launch" in msg:
            raise RuntimeError(
                "Playwright-Browser fehlt. Installiere ihn mit: playwright install chromium"
            ) from exc
        raise
