#!/usr/bin/env python3
import argparse
import pathlib
import re
from typing import Any

import requests


def _read_secret(path: str, key: str) -> str:
    txt = pathlib.Path(path).read_text(encoding="utf-8")
    m = re.search(rf'^\s*{re.escape(key)}\s*=\s*"([^"]+)"\s*$', txt, re.M)
    if not m:
        raise RuntimeError(f"{key} fehlt in {path}")
    return m.group(1)


def _to_int(v: Any) -> int | None:
    try:
        return int(round(float(v)))
    except Exception:
        return None


def _extract_num(answer0: dict, key: str) -> int | None:
    sec = answer0.get(key)
    if isinstance(sec, list) and sec and isinstance(sec[0], dict):
        return _to_int(sec[0].get("num"))
    if isinstance(sec, dict):
        return _to_int(sec.get("num"))
    return None


def main() -> None:
    ap = argparse.ArgumentParser(description="Direct SISTRIX links.overview check (without report run)")
    ap.add_argument("--domain", required=True, help="z.B. dr-hiller.at")
    ap.add_argument("--api-key", default="", help="Optional; sonst aus .streamlit/secrets.toml")
    args = ap.parse_args()

    api_key = args.api_key.strip() or _read_secret(".streamlit/secrets.toml", "SISTRIX_API_KEY")
    domain = args.domain.strip().lower().replace("https://", "").replace("http://", "").split("/")[0]

    base = "https://api.sistrix.com/links.overview"
    variants = [
        {"domain": domain, "format": "json"},
        {"address_object": domain, "format": "json"},
        {"host": domain, "format": "json"},
        {"path": domain, "format": "json"},
    ]

    print("=== links.overview debug ===")
    print("domain:", domain)
    for p in variants:
        params = {"api_key": api_key, **p}
        r = requests.get(base, params=params, timeout=30)
        print("\nstatus:", r.status_code, "| params:", p)
        data = r.json()
        top_keys = list(data.keys())[:8] if isinstance(data, dict) else []
        print("top keys:", top_keys)

        # error shape
        if isinstance(data, list) and data and isinstance(data[0], dict):
            em = data[0].get("error_message") or data[0].get("message")
            if em:
                print("error:", em)
                continue
        if isinstance(data, dict) and data.get("error_message"):
            print("error:", data.get("error_message"))
            continue

        answer = data.get("answer")
        answer0 = answer[0] if isinstance(answer, list) and answer and isinstance(answer[0], dict) else {}
        if not answer0:
            print("no answer[0] payload")
            print("sample:", str(data)[:500])
            continue

        total = _extract_num(answer0, "total")
        hosts = _extract_num(answer0, "hosts")
        domains = _extract_num(answer0, "domains")
        networks = _extract_num(answer0, "networks")
        class_c = _extract_num(answer0, "class_c")

        print("Anzahl Links:", total)
        print("Hostnamen:", hosts)
        print("Verweisende Domains:", domains)
        print("Netzwerke:", networks)
        print("IPs (class_c):", class_c)
        print("answer sample:", str(answer0)[:500])


if __name__ == "__main__":
    main()
