import requests


BASE_URL = "https://api.insites.com/api/v1"
TIMEOUT = 30


def get_report(report_id: str, api_key: str) -> dict:
    rid = (report_id or "").strip()
    key = (api_key or "").strip()
    if not rid or not key:
        return {}

    url = f"{BASE_URL}/report/{rid}"
    headers = {"api-key": key}
    r = requests.get(url, headers=headers, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json() if r.text else {}
