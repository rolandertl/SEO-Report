#!/usr/bin/env python3
import argparse
import pathlib
import re
from typing import Any
from urllib.parse import urlparse

import requests


def _read_secret(path: str, key: str) -> str:
    txt = pathlib.Path(path).read_text(encoding="utf-8")
    m = re.search(rf'^\s*{re.escape(key)}\s*=\s*"([^"]+)"\s*$', txt, re.M)
    if not m:
        raise RuntimeError(f"{key} fehlt in {path}")
    return m.group(1)


def _norm_domain(value: str | None) -> str:
    s = (value or "").strip().lower()
    if not s:
        return ""
    if "://" not in s:
        s = "https://" + s
    p = urlparse(s)
    host = (p.netloc or p.path).split("/")[0].strip().lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _extract_locations(payload: Any) -> list[dict]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("locations", "items", "objects", "results", "data"):
        v = payload.get(key)
        if isinstance(v, list):
            return [x for x in v if isinstance(x, dict)]
    for key in ("response", "result", "answer"):
        v = payload.get(key)
        if isinstance(v, dict):
            out = _extract_locations(v)
            if out:
                return out
    return []


def main() -> None:
    ap = argparse.ArgumentParser(description="Match entered domain against Uberall locations.website")
    ap.add_argument("--domain", required=True, help="eingegebene Domain, z.B. dr-hiller.at")
    ap.add_argument("--api-key", default="", help="optional, sonst aus .streamlit/secrets.toml")
    ap.add_argument("--max", type=int, default=500, help="maximale Anzahl Locations")
    args = ap.parse_args()

    api_key = args.api_key.strip() or _read_secret(".streamlit/secrets.toml", "UBERALL_API_KEY")
    input_domain = _norm_domain(args.domain)
    if not input_domain:
        raise SystemExit("Ungültige --domain")

    url = "https://api.uberall.com/api/locations"
    headers = {"X-API-KEY": api_key, "Accept": "application/json"}
    base_params = [
        ("fieldMask", "id"),
        ("fieldMask", "name"),
        ("fieldMask", "website"),
    ]

    all_rows: list[dict] = []
    offset = 0
    page = 0

    while True:
        page += 1
        params = [*base_params, ("max", str(args.max)), ("offset", str(offset))]
        r = requests.get(url, headers=headers, params=params, timeout=45)
        print(f"HTTP page {page}:", r.status_code, "| offset:", offset)
        payload = r.json()
        rows = _extract_locations(payload)
        if not rows:
            break
        all_rows.extend(rows)
        if len(rows) < args.max:
            break
        offset += args.max

    print("Locations geladen (gesamt):", len(all_rows))

    matches = []
    for row in all_rows:
        wid = row.get("id")
        name = row.get("name") or ""
        website = row.get("website") or ""
        website_domain = _norm_domain(website)
        if website_domain and website_domain == input_domain:
            matches.append({"id": wid, "name": name, "website": website})

    print("Input-Domain:", input_domain)
    print("Matches:", len(matches))
    for m in matches[:20]:
        print(f"- id={m['id']} | name={m['name']} | website={m['website']}")


if __name__ == "__main__":
    main()
