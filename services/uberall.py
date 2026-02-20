import requests

# Reihenfolge: neue API-Host-Domain zuerst, alter Host als Fallback.
BASE_URLS = [
    "https://api.uberall.com/api",
    "https://uberall.com/api",
]
TIMEOUT = 30


def _header_variants(api_key: str) -> list[dict]:
    common = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    # Verifiziert für diesen Account: API-Key Header.
    # Bearer-Token liefert BAD_ACCESS_TOKEN und wird daher nicht verwendet.
    return [
        {**common, "X-API-KEY": api_key, "privateKey": api_key},
    ]


def get(path: str, api_key: str, params: dict | None = None) -> dict:
    last_error = None
    for base_url in BASE_URLS:
        url = f"{base_url}/{path.lstrip('/')}"
        for headers in _header_variants(api_key):
            try:
                r = requests.get(url, headers=headers, params=params or {}, timeout=TIMEOUT)
                r.raise_for_status()
                return r.json()
            except Exception as e:
                last_error = e
                continue
    if last_error:
        raise last_error
    raise RuntimeError("Uberall GET fehlgeschlagen.")


def post(path: str, api_key: str, payload: dict | None = None, params: dict | None = None) -> dict:
    last_error = None
    for base_url in BASE_URLS:
        url = f"{base_url}/{path.lstrip('/')}"
        for headers in _header_variants(api_key):
            try:
                r = requests.post(
                    url,
                    headers=headers,
                    params=params or {},
                    json=payload or {},
                    timeout=TIMEOUT,
                )
                r.raise_for_status()
                return r.json()
            except Exception as e:
                last_error = e
                continue
    if last_error:
        raise last_error
    raise RuntimeError("Uberall POST fehlgeschlagen.")
