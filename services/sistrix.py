import time
import requests

BASE_URL = "https://api.sistrix.com"
DEFAULT_CACHE_TTL_SECONDS = 1800
_CACHE: dict[tuple, tuple[float, dict]] = {}


def _cache_key(endpoint: str, full_params: dict) -> tuple:
    return (endpoint.lstrip("/"), tuple(sorted((str(k), str(v)) for k, v in full_params.items())))


def _get_cached(endpoint: str, full_params: dict, cache_ttl: int) -> dict | None:
    key = _cache_key(endpoint, full_params)
    hit = _CACHE.get(key)
    if not hit:
        return None
    ts, payload = hit
    if (time.time() - ts) > cache_ttl:
        _CACHE.pop(key, None)
        return None
    return payload


def _put_cached(endpoint: str, full_params: dict, payload: dict) -> None:
    key = _cache_key(endpoint, full_params)
    _CACHE[key] = (time.time(), payload)


def call(
    endpoint: str,
    api_key: str,
    params: dict,
    timeout: tuple[float, float] = (10, 60),
    retries: int = 1,
    use_cache: bool = True,
    cache_ttl: int = DEFAULT_CACHE_TTL_SECONDS,
) -> dict:
    url = f"{BASE_URL}/{endpoint.lstrip('/')}"
    full_params = {"api_key": api_key, "format": "json", **params}

    if use_cache:
        cached = _get_cached(endpoint, full_params, cache_ttl=cache_ttl)
        if cached is not None:
            return cached

    last_err = None

    for attempt in range(retries):
        try:
            r = requests.get(url, params=full_params, timeout=timeout)
            # 5xx kann transient sein -> retry sinnvoll.
            if r.status_code >= 500:
                r.raise_for_status()

            # 4xx ist bei SISTRIX oft ein valider API-Fehler (z. B. Parameter),
            # den wir direkt an den Caller geben statt unnötig zu retrien.
            if r.status_code >= 400:
                try:
                    payload = r.json()
                except Exception:
                    payload = {"error_message": f"HTTP {r.status_code}"}
                return payload

            payload = r.json()
            if use_cache:
                _put_cached(endpoint, full_params, payload)
            return payload
        except (requests.Timeout, requests.ConnectionError, requests.HTTPError) as e:
            last_err = e
            if attempt < retries - 1:
                time.sleep(0.8 * (attempt + 1))
                continue
            raise

    raise RuntimeError(f"SISTRIX request failed: {last_err}")
