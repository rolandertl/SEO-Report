from core.config import DEV_MODE


def generate_comment(api_key: str, title: str, facts: dict) -> str:
    # In DEV_MODE: keine OpenAI-Abhängigkeit, keine Calls.
    if DEV_MODE:
        return (
            "Die Entwicklung wirkt insgesamt sehr positiv. Kleine Schwankungen sind im SEO völlig normal, "
            "gleichzeitig zeigt sich, dass die laufenden Maßnahmen greifen. Wir bleiben dran und optimieren "
            "weiter, um die Sichtbarkeit nachhaltig auszubauen."
        )

    # Real Mode: OpenAI erst hier importieren, damit DEV_MODE ohne openai-Paket läuft.
    from openai import OpenAI  # noqa: WPS433

    client = OpenAI(api_key=api_key)

    prompt = (
        "Du bist SEO-Manager:in und schreibst ein kurzes Statement für einen Kundenreport.\n"
        "Sprache: Deutsch (AT). Länge: 2–4 Sätze. Ton: menschlich, freundlich, seriös, motivierend.\n"
        "Immer konstruktiv formulieren – auch wenn die Entwicklung negativ ist (Schwankungen sind normal, "
        "kein Grund zur Sorge, laufende Maßnahmen greifen, Ausblick positiv).\n"
        f"Titel: {title}\n"
        f"Kennzahlen: {facts}\n"
        "Schreibe jetzt das Statement."
    )

    resp = client.chat.completions.create(
        model="gpt-5-mini",
        messages=[{"role": "user", "content": prompt}],
    )

    return resp.choices[0].message.content.strip()
