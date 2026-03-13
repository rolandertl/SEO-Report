import hashlib
import json
from pathlib import Path

from core.config import DEV_MODE


CACHE_DIR = Path(".cache")
CACHE_FILE = CACHE_DIR / "llm_comments.json"


def _stable_key(title: str, facts: dict) -> str:
    payload = json.dumps({"title": title, "facts": facts}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _read_cache() -> dict:
    try:
        if CACHE_FILE.exists():
            return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _write_cache(data: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


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


def generate_comment_cached(api_key: str, title: str, facts: dict, fallback: str = "") -> str:
    key = _stable_key(title, facts)
    cache = _read_cache()
    cached = cache.get(key)
    if isinstance(cached, str) and cached.strip():
        return cached.strip()

    try:
        text = generate_comment(api_key, title, facts).strip()
    except Exception:
        return fallback

    if not text:
        return fallback

    cache[key] = text
    try:
        _write_cache(cache)
    except Exception:
        pass
    return text


def translate_term_cached(api_key: str, text: str, fallback: str = "") -> str:
    source = (text or "").strip()
    if not source:
        return fallback

    key = _stable_key("translate_term_de_at", {"text": source})
    cache = _read_cache()
    cached = cache.get(key)
    if isinstance(cached, str) and cached.strip():
        return cached.strip()

    if DEV_MODE:
        return fallback or source

    try:
        from openai import OpenAI  # noqa: WPS433

        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model="gpt-5-mini",
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Übersetze diesen englischen Google-Business-Profil-Kategorienamen ins Deutsche (AT). "
                        "Gib nur die kurze deutsche Bezeichnung aus, ohne Erklärung, ohne Anführungszeichen, "
                        "ohne zusätzlichen Text.\n"
                        f"Kategorie: {source}"
                    ),
                }
            ],
        )
        translated = resp.choices[0].message.content.strip()
    except Exception:
        return fallback or source

    if not translated:
        return fallback or source

    cache[key] = translated
    try:
        _write_cache(cache)
    except Exception:
        pass
    return translated
