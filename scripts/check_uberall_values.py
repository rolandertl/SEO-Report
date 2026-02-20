#!/usr/bin/env python3
import argparse
import json
from typing import Any

import requests


def _to_float(v: Any) -> float | None:
    try:
        return float(v)
    except Exception:
        return None


def _to_int(v: Any) -> int | None:
    try:
        return int(round(float(v)))
    except Exception:
        return None


def _norm_rate(v: Any) -> float | None:
    f = _to_float(v)
    if f is None:
        return None
    if 0 <= f <= 1:
        f *= 100.0
    return f


def _extract_insights_totals(payload: dict) -> tuple[float, float, float]:
    search = 0.0
    maps = 0.0
    clicks = 0.0

    data_rows = payload.get("data") or ((payload.get("response") or {}).get("data") or [])
    if isinstance(data_rows, list) and data_rows:
        for row in data_rows:
            if not isinstance(row, dict):
                continue
            bis_d = _to_float(row.get("BUSINESS_IMPRESSIONS_DESKTOP_SEARCH")) or 0.0
            bis_m = _to_float(row.get("BUSINESS_IMPRESSIONS_MOBILE_SEARCH")) or 0.0
            bim_d = _to_float(row.get("BUSINESS_IMPRESSIONS_DESKTOP_MAPS")) or 0.0
            bim_m = _to_float(row.get("BUSINESS_IMPRESSIONS_MOBILE_MAPS")) or 0.0
            qd = _to_float(row.get("QUERIES_DIRECT")) or 0.0
            qi = _to_float(row.get("QUERIES_INDIRECT")) or 0.0
            qc = _to_float(row.get("QUERIES_CHAIN")) or 0.0
            vs = _to_float(row.get("VIEWS_SEARCH")) or 0.0
            search += (bis_d + bis_m) if (bis_d + bis_m) > 0 else ((qd + qi + qc) if (qd + qi + qc) > 0 else vs)
            maps += (bim_d + bim_m) if (bim_d + bim_m) > 0 else (_to_float(row.get("VIEWS_MAPS")) or 0.0)
            clicks += (
                (_to_float(row.get("ACTIONS_WEBSITE")) or 0.0)
                + (_to_float(row.get("ACTIONS_PHONE")) or 0.0)
                + (_to_float(row.get("ACTIONS_DRIVING_DIRECTIONS")) or 0.0)
            )
        return search, maps, clicks

    metric_rows = ((payload.get("response") or {}).get("metrics") or [])
    if isinstance(metric_rows, list) and metric_rows:
        for metric in metric_rows:
            if not isinstance(metric, dict):
                continue
            name = str(metric.get("name") or "")
            points = metric.get("data") or []
            val = sum((_to_float(p.get("count")) or 0.0) for p in points if isinstance(p, dict))
            if name in (
                "BUSINESS_IMPRESSIONS_DESKTOP_SEARCH",
                "BUSINESS_IMPRESSIONS_MOBILE_SEARCH",
                "QUERIES_DIRECT",
                "QUERIES_INDIRECT",
                "QUERIES_CHAIN",
                "VIEWS_SEARCH",
            ):
                search += val
            elif name in (
                "BUSINESS_IMPRESSIONS_DESKTOP_MAPS",
                "BUSINESS_IMPRESSIONS_MOBILE_MAPS",
                "VIEWS_MAPS",
            ):
                maps += val
            elif name in ("ACTIONS_WEBSITE", "ACTIONS_PHONE", "ACTIONS_DRIVING_DIRECTIONS"):
                clicks += val
        return search, maps, clicks

    return 0.0, 0.0, 0.0


def _extract_feedback(payload: dict) -> tuple[float | None, int | None, float | None]:
    p = payload.get("response") if isinstance(payload.get("response"), dict) else payload
    if not isinstance(p, dict):
        return None, None, None

    avg = _to_float(p.get("averageRating"))
    cnt = _to_int(p.get("numberOfReviews"))
    rr = _norm_rate(p.get("reviewResponseRate") or p.get("responseRate") or p.get("answerRate"))

    if avg is None:
        ratings = p.get("averageRatingByPeriod") or []
        counts = p.get("interactionCountByPeriod") or []
        weight = {}
        for c in counts:
            if isinstance(c, dict):
                period = str(c.get("period") or "")
                weight[period] = _to_float(c.get("count")) or 0.0
        ws = 0.0
        tw = 0.0
        for r in ratings:
            if isinstance(r, dict):
                period = str(r.get("period") or "")
                v = _to_float(r.get("value"))
                if v is None:
                    continue
                w = weight.get(period, 1.0)
                ws += v * w
                tw += w
        if tw > 0:
            avg = ws / tw

    if cnt is None:
        cnt = _to_int(p.get("totalRatingCount"))
    if cnt is None:
        counts = p.get("interactionCountByPeriod") or []
        cnt = int(round(sum((_to_float(c.get("count")) or 0.0) for c in counts if isinstance(c, dict)))) if counts else None

    if rr is None:
        rr_rows = p.get("reviewResponseRateByPeriod") or p.get("responseRateByPeriod") or []
        vals = []
        for r in rr_rows:
            if isinstance(r, dict):
                v = _norm_rate(r.get("value") or r.get("rate"))
                if v is not None:
                    vals.append(v)
        if vals:
            rr = sum(vals) / len(vals)

    return avg, cnt, rr


def _extract_feedback_rate_from_customer_feedback(payload: dict) -> float | None:
    p = payload.get("response") if isinstance(payload.get("response"), dict) else payload
    if not isinstance(p, dict):
        return None
    replied = _to_float(p.get("repliedCount"))
    total = _to_float(p.get("ratingCount"))
    if replied is None or total is None or total <= 0:
        return None
    return (replied / total) * 100.0


def main() -> None:
    ap = argparse.ArgumentParser(description="Direct Uberall check for Local SEO values (without report run).")
    ap.add_argument("--api-key", required=True)
    ap.add_argument("--location-id", required=True)
    ap.add_argument("--start-date", required=True, help="YYYY-MM-DD")
    ap.add_argument("--end-date", required=True, help="YYYY-MM-DD")
    args = ap.parse_args()

    base = "https://api.uberall.com/api"
    headers = {"X-API-KEY": args.api_key, "Accept": "application/json"}

    metric_sets = [
        [
            "BUSINESS_IMPRESSIONS_DESKTOP_SEARCH",
            "BUSINESS_IMPRESSIONS_MOBILE_SEARCH",
            "BUSINESS_IMPRESSIONS_DESKTOP_MAPS",
            "BUSINESS_IMPRESSIONS_MOBILE_MAPS",
            "ACTIONS_WEBSITE",
            "ACTIONS_PHONE",
            "ACTIONS_DRIVING_DIRECTIONS",
        ],
        ["QUERIES_DIRECT", "QUERIES_INDIRECT", "QUERIES_CHAIN", "VIEWS_MAPS", "ACTIONS_WEBSITE", "ACTIONS_PHONE", "ACTIONS_DRIVING_DIRECTIONS"],
        ["VIEWS_SEARCH", "VIEWS_MAPS", "ACTIONS_WEBSITE", "ACTIONS_PHONE", "ACTIONS_DRIVING_DIRECTIONS"],
    ]
    base_insights = {
        "startDate": args.start_date,
        "endDate": args.end_date,
        "group": "MONTH",
    }
    insights_variants = []
    for metrics in metric_sets:
        insights_variants.extend(
            [
                {**base_insights, "locationIds": args.location_id, "type": "GOOGLE", "metrics": metrics},
                {**base_insights, "locationIds": [int(args.location_id)], "type": "GOOGLE", "metrics": metrics},
                {**base_insights, "locationId": args.location_id, "type": "GOOGLE", "metrics": metrics},
            ]
        )
    r1 = None
    i_payload = {}
    used_variant = None
    for p in insights_variants:
        resp = requests.get(f"{base}/dashboard/insights-data", headers=headers, params=p, timeout=30)
        payload = resp.json()
        if resp.status_code == 200:
            r1 = resp
            i_payload = payload
            used_variant = p
            break
        r1 = resp
        i_payload = payload

    fb_params = {
        "locationIds": args.location_id,
        "startDate": args.start_date,
        "endDate": args.end_date,
    }
    r2 = requests.get(
        f"{base}/dashboard/customer-feedback-by-period",
        headers=headers,
        params=fb_params,
        timeout=30,
    )
    f_payload = r2.json()
    r3 = requests.get(
        f"{base}/dashboard/customer-feedback",
        headers=headers,
        params={**fb_params, "type": "GOOGLE"},
        timeout=30,
    )
    f2_payload = r3.json()

    search, maps, clicks = _extract_insights_totals(i_payload)
    avg, cnt, rr = _extract_feedback(f_payload)
    if rr is None:
        rr = _extract_feedback_rate_from_customer_feedback(f2_payload)

    print("=== HTTP ===")
    print(f"insights-data: {r1.status_code}")
    print(f"customer-feedback-by-period: {r2.status_code}")
    print(f"customer-feedback: {r3.status_code}")
    if used_variant:
        print("insights variant:", used_variant)
    else:
        print("insights variant: none succeeded")
    print("\n=== Werte ===")
    print(f"Suche Impressions (Summe): {int(round(search))}")
    print(f"Maps Impressions (Summe): {int(round(maps))}")
    print(f"Klicks (Summe): {int(round(clicks))}")
    print(f"Ø Rating: {avg:.2f}" if avg is not None else "Ø Rating: n/a")
    print(f"Anzahl Reviews: {cnt}" if cnt is not None else "Anzahl Reviews: n/a")
    print(f"Antwortrate: {rr:.1f}%" if rr is not None else "Antwortrate: n/a")

    print("\n=== Debug (gekürzt) ===")
    print("insights keys:", list(i_payload.keys())[:10] if isinstance(i_payload, dict) else type(i_payload))
    print("feedback keys:", list(f_payload.keys())[:10] if isinstance(f_payload, dict) else type(f_payload))
    print("feedback2 keys:", list(f2_payload.keys())[:10] if isinstance(f2_payload, dict) else type(f2_payload))
    print("insights sample:", json.dumps(i_payload, ensure_ascii=False)[:400])
    print("feedback sample:", json.dumps(f_payload, ensure_ascii=False)[:400])
    print("feedback2 sample:", json.dumps(f2_payload, ensure_ascii=False)[:400])


if __name__ == "__main__":
    main()
