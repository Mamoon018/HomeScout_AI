import json
from pathlib import Path

from google.maps import places_v1

from src.clients.google_places import create_places_client
from src.core.config import get_settings
from src.core.logging import configure_logging

SAMPLE_LISTING_LATITUDE = 50.130034
SAMPLE_LISTING_LONGITUDE = 8.628251
SAMPLE_RADIUS_METERS = 1500.0
SAMPLE_DATA_PATH = (
    Path(__file__).resolve().parents[1] / "sample_data" / "search_nearby_response.json"
)

# One category per call. Types in a list are OR-matched by searchNearby.
SURROUNDINGS_CATEGORIES: dict[str, list[str]] = {
    "supermarket": [
        "supermarket",
        "grocery_store",
        "convenience_store",
        "market",
        "food_store",
    ],
    "hospital": ["hospital"],
    "pharmacy": ["pharmacy"],
    "school": ["school", "primary_school", "secondary_school"],
    "daycare": ["child_care_agency", "preschool"],
    "park": ["park"],
    "gym": ["gym"],
    "restaurant": ["restaurant"],
    "cafe": ["cafe", "coffee_shop"],
    "utility_store": ["hardware_store", "home_improvement_store"],
    "outdoor_activity": ["hiking_area", "sports_complex", "campground"],
    "train_station": [
        "train_station",
        "subway_station",
        "light_rail_station",
        "transit_station",
    ],
}

ENABLED_CATEGORIES = ("supermarket",)

TRAVEL_MODES = {
    "car": places_v1.TravelMode.DRIVE,
    "bike": places_v1.TravelMode.BICYCLE,
    "walk": places_v1.TravelMode.WALK,
}


def run_sample_search() -> dict:
    """Call searchNearby once per enabled category and travel mode; write sample JSON."""
    settings = get_settings()
    configure_logging(settings.log_level)
    client = create_places_client(settings)

    results: dict[str, dict[str, dict]] = {}
    for category in ENABLED_CATEGORIES:
        included_types = SURROUNDINGS_CATEGORIES[category]
        results[category] = {}
        for mode_name, travel_mode in TRAVEL_MODES.items():
            response = client.search_nearby(
                latitude=SAMPLE_LISTING_LATITUDE,
                longitude=SAMPLE_LISTING_LONGITUDE,
                radius_meters=SAMPLE_RADIUS_METERS,
                included_types=included_types,
                travel_mode=travel_mode,
                max_result_count=20,
            )
            results[category][mode_name] = json.loads(
                places_v1.SearchNearbyResponse.to_json(response)
            )

    payload = {
        "listing": {
            "latitude": SAMPLE_LISTING_LATITUDE,
            "longitude": SAMPLE_LISTING_LONGITUDE,
            "radius_meters": SAMPLE_RADIUS_METERS,
        },
        "results": results,
    }
    SAMPLE_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    SAMPLE_DATA_PATH.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return payload


if __name__ == "__main__":
    run_sample_search()
