"""Sub-component 3: the maintained amenity-category taxonomy, as data.

Component 2A maps every raw category from Mechanism 1 onto exactly one node in this list.
This is a flat set of nodes, not an abstraction: mapping needs the node list rendered into
a prompt and a membership set for a defensive check, both of which are data reads rather than
behavior, so there is no loader, index, or package layer around it. Nodes are added or
removed by editing the one tuple below; the schema enum and the prompt both derive from it.
"""

# The maintained taxonomy. Every mapped `taxonomy_node` must be one of these exact strings.
# Grouping comments are for the maintainer only; the taxonomy itself is the flat tuple.
AMENITY_TAXONOMY_NODES: tuple[str, ...] = (
    # Food and drink
    "restaurant",
    "cafe",
    "coffee_shop",
    "bakery",
    "bar",
    "pub",
    "fast_food_restaurant",
    "fine_dining_restaurant",
    "ice_cream_shop",
    "juice_bar",
    "tea_house",
    "food_court",
    "food_truck",
    "wine_bar",
    "brewery",
    # Grocery and retail
    "supermarket",
    "grocery_store",
    "convenience_store",
    "organic_food_store",
    "farmers_market",
    "butcher_shop",
    "fishmonger",
    "greengrocer",
    "delicatessen",
    "liquor_store",
    "shopping_mall",
    "department_store",
    "clothing_store",
    "shoe_store",
    "electronics_store",
    "furniture_store",
    "hardware_store",
    "bookstore",
    "pet_store",
    "toy_store",
    "jewelry_store",
    "florist",
    "gift_shop",
    "stationery_store",
    "sporting_goods_store",
    # Health and medical
    "hospital",
    "clinic",
    "doctor_office",
    "dentist",
    "pharmacy",
    "optometrist",
    "physiotherapy_clinic",
    "veterinary_clinic",
    "urgent_care_center",
    "mental_health_clinic",
    "medical_laboratory",
    "blood_donation_center",
    # Fitness and sport
    "gym",
    "fitness_center",
    "yoga_studio",
    "pilates_studio",
    "swimming_pool",
    "sports_complex",
    "tennis_court",
    "basketball_court",
    "soccer_field",
    "golf_course",
    "climbing_gym",
    "martial_arts_school",
    "dance_studio",
    "cycling_track",
    "running_track",
    # Education
    "preschool",
    "kindergarten",
    "daycare",
    "primary_school",
    "secondary_school",
    "high_school",
    "international_school",
    "university",
    "college",
    "library",
    "tutoring_center",
    "language_school",
    "music_school",
    "art_school",
    "vocational_school",
    # Parks and recreation
    "park",
    "playground",
    "dog_park",
    "botanical_garden",
    "nature_reserve",
    "hiking_trail",
    "beach",
    "lake",
    "picnic_area",
    "amusement_park",
    "zoo",
    "aquarium",
    "community_garden",
    # Culture and entertainment
    "museum",
    "art_gallery",
    "cinema",
    "theater",
    "concert_hall",
    "nightclub",
    "bowling_alley",
    "arcade",
    "casino",
    "stadium",
    "event_venue",
    # Transport
    "bus_stop",
    "train_station",
    "subway_station",
    "tram_stop",
    "airport",
    "taxi_stand",
    "bicycle_rental",
    "parking_lot",
    "gas_station",
    "electric_vehicle_charging_station",
    "car_rental",
    "ferry_terminal",
    # Services and civic
    "bank",
    "atm",
    "post_office",
    "police_station",
    "fire_station",
    "laundry",
    "hair_salon",
    "beauty_salon",
    "spa",
    "place_of_worship",
)

# Independent membership check reused after the schema enum, mirroring Mechanism 1's rule of
# validating a body even after generation-time constraint.
TAXONOMY_NODE_SET: frozenset[str] = frozenset(AMENITY_TAXONOMY_NODES)


def render_taxonomy() -> str:
    """Render every node as a numbered list for inlining into the mapping instruction."""
    lines = (
        f"{index}. {node}"
        for index, node in enumerate(AMENITY_TAXONOMY_NODES, start=1)
    )
    return "\n".join(lines)
