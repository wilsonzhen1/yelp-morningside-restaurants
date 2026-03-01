import json
import math
import os
import time
from typing import Dict, List, Tuple

import requests

YELP_API_KEY = os.getenv("YELP_API_KEY")
if not YELP_API_KEY:
    raise SystemExit("Missing YELP_API_KEY environment variable.")

SEARCH_URL = "https://api.yelp.com/v3/businesses/search"
HEADERS = {"Authorization": f"Bearer {YELP_API_KEY}"}

# Rough Morningside Heights bounding box:
# North/South: ~125th to ~110th
# West/East: ~Riverside Dr (around -73.97) to Morningside Dr (around -73.95)
# NOTE: This is approximate. Adjust as needed.
SW_LAT, SW_LNG = 40.8030, -73.9725   # near Riverside & ~110th
NE_LAT, NE_LNG = 40.8175, -73.9495   # near Morningside & ~125th

CATEGORIES = "restaurants"

# In dense areas like Manhattan, use smaller radii to avoid hitting result caps.
RADIUS_M = 350

# Pagination settings
LIMIT = 50
MAX_PAGES = 5  # 5 pages * 50 = 250 (Yelp’s effective cap per query is typically around this range)
SLEEP_S = 0.25  # be polite; also helps with rate limits


def meters_to_lat(m: float) -> float:
    return m / 111_320.0


def meters_to_lng(m: float, lat: float) -> float:
    return m / (111_320.0 * math.cos(math.radians(lat)))


def business_search(lat: float, lng: float, radius_m: int) -> List[Dict]:
    """Search Yelp around one center point, with pagination; returns list of businesses."""
    results: List[Dict] = []

    for page in range(MAX_PAGES):
        offset = page * LIMIT
        params = {
            "latitude": lat,
            "longitude": lng,
            "radius": radius_m,
            "categories": CATEGORIES,
            "limit": LIMIT,
            "offset": offset,
        }

        r = requests.get(SEARCH_URL, headers=HEADERS, params=params, timeout=30)
        # If you ever hit 429, increase SLEEP_S and/or reduce schedule frequency.
        r.raise_for_status()

        data = r.json()
        businesses = data.get("businesses", [])
        results.extend(businesses)

        # Stop early if this page wasn't full (no more results for this query)
        if len(businesses) < LIMIT:
            break

        time.sleep(SLEEP_S)

    return results


def generate_grid(sw: Tuple[float, float], ne: Tuple[float, float], radius_m: int) -> List[Tuple[float, float]]:
    """Generate overlapping grid points covering a rectangle."""
    sw_lat, sw_lng = sw
    ne_lat, ne_lng = ne

    # Step slightly smaller than radius for overlap (improves coverage)
    step_m = radius_m * 1.2

    points: List[Tuple[float, float]] = []
    lat = sw_lat
    while lat <= ne_lat:
        lng = sw_lng
        while lng <= ne_lng:
            points.append((lat, lng))
            lng += meters_to_lng(step_m, lat)
        lat += meters_to_lat(step_m)

    return points


def main():
    sw = (SW_LAT, SW_LNG)
    ne = (NE_LAT, NE_LNG)

    grid_points = generate_grid(sw, ne, RADIUS_M)
    print(f"Grid points: {len(grid_points)} (radius={RADIUS_M}m)")

    dedup: Dict[str, Dict] = {}

    for i, (lat, lng) in enumerate(grid_points, start=1):
        hits = business_search(lat, lng, RADIUS_M)
        for b in hits:
            bid = b.get("id")
            if bid:
                dedup[bid] = b

        print(f"[{i}/{len(grid_points)}] point=({lat:.5f},{lng:.5f}) hits={len(hits)} total_unique={len(dedup)}")
        time.sleep(SLEEP_S)

    out_dir = "data"
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "morningside_restaurants.json")

    # Write a cleaner JSON structure
    output = {
        "area": "Morningside Heights (approx bbox)",
        "bbox": {"sw": {"lat": SW_LAT, "lng": SW_LNG}, "ne": {"lat": NE_LAT, "lng": NE_LNG}},
        "radius_m": RADIUS_M,
        "categories": CATEGORIES,
        "count_unique": len(dedup),
        "businesses": sorted(dedup.values(), key=lambda x: x.get("name", "")),
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\nSaved {len(dedup)} unique restaurants to {out_path}")


if __name__ == "__main__":
    main()