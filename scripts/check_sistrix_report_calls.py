#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any
import sys

# Ensure project root is importable when script is executed from scripts/
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.context import ReportContext
from metrics.visibility import build_visibility_block
from metrics.top_urls import build_top_urls_block
from metrics.keyword_profile import build_keyword_profile_block
from metrics.interesting_rankings import build_interesting_rankings_block
from metrics.ranking_changes import (
    build_newcomers_block,
    build_winners_block,
    build_losers_block,
)
import services.sistrix as sistrix_mod


def _read_secret(path: str, key: str) -> str:
    p = Path(path)
    if not p.exists():
        return ""
    for line in p.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        if k.strip() == key:
            return v.strip().strip('"').strip("'")
    return ""


def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Runs only SISTRIX report blocks and prints outgoing SISTRIX HTTP call profile."
    )
    ap.add_argument("--domain", required=True, help="Domain ohne www, z. B. dr-hiller.at")
    ap.add_argument("--start", required=True, help="YYYY-MM-DD")
    ap.add_argument("--end", required=True, help="YYYY-MM-DD")
    ap.add_argument("--country", default="at")
    ap.add_argument("--api-key", default="", help="Optional; sonst aus .streamlit/secrets.toml")
    args = ap.parse_args()

    api_key = args.api_key.strip() or _read_secret(".streamlit/secrets.toml", "SISTRIX_API_KEY")
    if not api_key:
        print("ERROR: Kein SISTRIX API Key gefunden.")
        return 2

    ctx = ReportContext(
        domain=args.domain.strip(),
        start_date=_parse_date(args.start),
        end_date=_parse_date(args.end),
        country=args.country.strip().lower(),
    )

    endpoint_counter: Counter[str] = Counter()
    signature_counter: Counter[str] = Counter()

    orig_get = sistrix_mod.requests.get

    def wrapped_get(url: str, params: dict | None = None, timeout: Any = None, **kwargs: Any):
        endpoint = url.rstrip("/").split("/")[-1]
        endpoint_counter[endpoint] += 1
        p = dict(params or {})
        p.pop("api_key", None)
        signature = f"{endpoint} | " + "&".join(f"{k}={p[k]}" for k in sorted(p.keys()))
        signature_counter[signature] += 1
        return orig_get(url, params=params, timeout=timeout, **kwargs)

    sistrix_mod.requests.get = wrapped_get
    try:
        # Nur SISTRIX-Blöcke (kein OpenAI/Uberall)
        _ = build_visibility_block(ctx, api_key, "")
        _ = build_top_urls_block(ctx, api_key, "")
        _ = build_keyword_profile_block(ctx, api_key, "")
        _ = build_interesting_rankings_block(ctx, api_key, "")
        _ = build_newcomers_block(ctx, api_key, "")
        _ = build_winners_block(ctx, api_key, "")
        _ = build_losers_block(ctx, api_key, "")
    finally:
        sistrix_mod.requests.get = orig_get

    print("=== SISTRIX HTTP Call Profile ===")
    print(f"Domain: {ctx.domain} | Zeitraum: {ctx.start_date} bis {ctx.end_date}")
    print("\nCalls pro Endpoint:")
    for ep, n in endpoint_counter.most_common():
        print(f"- {ep}: {n}")

    print("\nCall-Signaturen:")
    for sig, n in signature_counter.most_common():
        print(f"- {n}x {sig}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
