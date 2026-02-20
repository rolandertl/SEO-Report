import requests


FIND_PLACE_URL = "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"
TEXT_SEARCH_NEW_URL = "https://places.googleapis.com/v1/places:searchText"


def fetch_rating_and_review_count(
    api_key: str,
    *,
    name: str,
    street: str = "",
    postal_code: str = "",
) -> tuple[float, int] | None:
    name = name.strip()
    street = street.strip()
    postal_code = postal_code.strip()

    if not name:
        return None

    queries = []
    if street and postal_code:
        queries.append(f"{name}, {street}, {postal_code}")
    if postal_code:
        queries.append(f"{name}, {postal_code}")
    queries.append(name)

    for query in queries:
        # 1) Legacy Find Place
        params = {
            "input": query,
            "inputtype": "textquery",
            "fields": "name,formatted_address,rating,user_ratings_total",
            "key": api_key,
        }
        resp = requests.get(FIND_PLACE_URL, params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json()

        status = data.get("status")
        if status == "OK":
            candidates = data.get("candidates") or []
            if candidates:
                first = candidates[0]
                rating = first.get("rating")
                count = first.get("user_ratings_total")
                if rating is not None and count is not None:
                    return float(rating), int(count)
        elif status in {"ZERO_RESULTS", None}:
            pass
        else:
            raise RuntimeError(
                f"Google Places Legacy Fehler: {status} - {data.get('error_message', 'ohne Details')}"
            )

        # 2) Places API (New) Text Search
        headers = {
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.rating,places.userRatingCount",
        }
        payload = {"textQuery": query}
        resp_new = requests.post(TEXT_SEARCH_NEW_URL, headers=headers, json=payload, timeout=20)

        if resp_new.status_code >= 400:
            try:
                err = resp_new.json()
            except Exception:
                err = {}
            msg = (
                (err.get("error") or {}).get("message")
                or f"HTTP {resp_new.status_code}"
            )
            raise RuntimeError(f"Google Places New Fehler: {msg}")

        data_new = resp_new.json()
        places = data_new.get("places") or []
        if places:
            first = places[0]
            rating = first.get("rating")
            count = first.get("userRatingCount")
            if rating is not None and count is not None:
                return float(rating), int(count)

    return None
