
# Sample Output - Responsibility - 1 (Mechanism - 1)
# ==============================================================================
# STAGE 5 - HANDOFF
# ==============================================================================
{
  "payload": {
    "normalized_text": "We're moving to Frankfurt in April with our two kids, aged four and nine, and we've narrowed things down to a few apartments in the north of the city. My wife and I both work hybrid, so we're each in the office two or three days a week and at home the rest of the time. The younger one starts kindergarten in the autumn, so a daycare within a short walk is the thing we care about most, and the older one needs a primary school we'd be happy with. I run early in the mornings and would like green space I can actually loop around rather than a small square with a bench.\n\nWe do a big weekly shop, so a proper supermarket rather than a corner shop matters, ideally one we can reach without the car since we only have one between us. A decent gym would be a bonus, nothing fancy, just something open before seven. We're not particularly interested in nightlife. If we end up getting a dog, which we have been discussing, somewhere to walk it would suddenly matter a lot more than it does today.",
    "raw_text": "We're moving to Frankfurt in April with our two kids, aged four and nine, and we've narrowed things down to a few apartments in the north of the city. My wife and I both work hybrid, so we're each in the office two or three days a week and at home the rest of the time. The younger one starts kindergarten in the autumn, so a daycare within a short walk is the thing we care about most, and the older one needs a primary school we'd be happy with. I run early in the mornings and would like green space I can actually loop around rather than a small square with a bench.\n\nWe do a big weekly shop, so a proper supermarket rather than a corner shop matters, ideally one we can reach without the car since we only have one between us. A decent gym would be a bonus, nothing fancy, just something open before seven. We're not particularly interested in nightlife. If we end up getting a dog, which we have been discussing, somewhere to walk it would suddenly matter a lot more than it does today."
  },
  "extracted": {
    "explicit_categories": [
      {
        "name": "daycare",
        "characteristics": [
          "within a short walk"
        ]
      },
      {
        "name": "primary school",
        "characteristics": [
          "we'd be happy with"
        ]
      },
      {
        "name": "green space",
        "characteristics": [
          "I can actually loop around",
          "rather than a small square with a bench"
        ]
      },
      {
        "name": "proper supermarket",
        "characteristics": [
          "rather than a corner shop",
          "we can reach without the car"
        ]
      },
      {
        "name": "gym",
        "characteristics": [
          "decent",
          "open before seven"
        ]
      }
    ],
    "ambiguity_flags": [
      {
        "phrase": "a primary school we'd be happy with",
        "target": "characteristic"
      },
      {
        "phrase": "green space I can actually loop around",
        "target": "characteristic"
      },
      {
        "phrase": "proper supermarket",
        "target": "characteristic"
      },
      {
        "phrase": "a decent gym",
        "target": "characteristic"
      }
    ],
    "persona_facts": [
      "moving to Frankfurt in April",
      "has two kids, aged four and nine",
      "has narrowed the options down to a few apartments in the north of the city",
      "both adults work hybrid, in the office two or three days a week and at home the rest of the time",
      "the younger child starts kindergarten in the autumn",
      "the older child needs a primary school",
      "runs early in the mornings",
      "does a big weekly shop",
      "has one car between them",
      "not particularly interested in nightlife",
      "has been discussing getting a dog, but it is not decided yet",
      "somewhere to walk the dog would matter much more if they get one"
    ]
  }
}






# Sample Output - Responsibility - 1 (Mechanism - 4)
# ==============================================================================
# Inferred Categories
# ==============================================================================

[
  {
    "taxonomy_node": "dog_park",
    "category_id": 2,
    "reasoning": "The persona fact that they adopted a rescue dog last month and walk it twice a day supports a distinct need for dog-friendly outdoor space, such as a dog park, beyond the explicit swimming pool and book_store."
  },
  {
    "taxonomy_node": "medical_clinic",
    "category_id": 3,
    "reasoning": "The persona fact that the partner is in the third trimester, together with the stated need for somewhere she can be seen quickly if something feels off, supports a medical clinic as a distinct information need."
  }
]





# Sample Output 
# ==============================================================================
# Metric definition Sample run
# ==============================================================================


[
  {
    "category_id": 0,
    "taxonomy_node": "swimming_pool",
    "depth": "specific_attributes",
    "predefined_metrics": [
      {
        "label": "name",
        "band": "basic_profile",
        "resolution_source": {
          "tool": "google_maps",
          "target": "places.displayName"
        }
      },
      {
        "label": "category",
        "band": "basic_profile",
        "resolution_source": {
          "tool": "google_maps",
          "target": "places.primaryType"
        }
      },
      {
        "label": "address",
        "band": "basic_profile",
        "resolution_source": {
          "tool": "google_maps",
          "target": "places.formattedAddress"
        }
      },
      {
        "label": "website",
        "band": "basic_profile",
        "resolution_source": {
          "tool": "google_maps",
          "target": "places.websiteUri"
        }
      },
      {
        "label": "place_id",
        "band": "basic_profile",
        "resolution_source": {
          "tool": "google_maps",
          "target": "places.id"
        }
      },
      {
        "label": "coordinates",
        "band": "basic_profile",
        "resolution_source": {
          "tool": "google_maps",
          "target": "places.location"
        }
      },
      {
        "label": "travel distance per mode (walk, drive, cycle)",
        "band": "basic_profile",
        "resolution_source": {
          "tool": "google_maps",
          "target": "routingSummaries.legs.distanceMeters via searchNearby for walk/drive/cycle (one call per mode)"
        }
      },
      {
        "label": "travel duration per mode (walk, drive, cycle)",
        "band": "basic_profile",
        "resolution_source": {
          "tool": "google_maps",
          "target": "routingSummaries.legs.duration via searchNearby for walk/drive/cycle (one call per mode)"
        }
      },
      {
        "label": "transit_details",
        "band": "basic_profile",
        "resolution_source": {
          "tool": "google_maps",
          "target": "Routes API, travelMode TRANSIT (bus, subway, train allowed in the same call)"
        }
      },
      {
        "label": "opening hours",
        "band": "operating_details",
        "resolution_source": {
          "tool": "google_maps",
          "target": "places.regularOpeningHours"
        }
      },
      {
        "label": "contact phone",
        "band": "operating_details",
        "resolution_source": {
          "tool": "google_maps",
          "target": "places.internationalPhoneNumber"
        }
      },
      {
        "label": "rating",
        "band": "operating_details",
        "resolution_source": {
          "tool": "google_maps",
          "target": "places.rating"
        }
      },
      {
        "label": "review volume",
        "band": "operating_details",
        "resolution_source": {
          "tool": "google_maps",
          "target": "places.userRatingCount"
        }
      },
      {
        "label": "price level",
        "band": "operating_details",
        "resolution_source": {
          "tool": "google_maps",
          "target": "places.priceLevel"
        }
      }
    ],
    "specific_metrics": [
      {
        "label": "Pool cleanliness",
        "question": "The customer explicitly asked for a swimming pool for regular lap swimming: is the pool generally clean and well maintained?",
        "value_type": "enum",
        "unit": null,
        "enum_values": [
          "poor",
          "mixed",
          "good"
        ],
        "resolution_source": {
          "tool": "parallel_web_search",
          "target": "review mentions of pool cleanliness, maintenance, and water quality"
        },
        "verification": "dominant sentiment across at least 5 reviews mentioning cleanliness or maintenance",
        "null_policy": "unknown",
        "band": "operating_details"
      },
      {
        "label": "Lap-lane access before 6am",
        "question": "The customer named lap lanes open before 6am as a requirement: are lap lanes available for swimming before 6:00am?",
        "value_type": "boolean",
        "unit": null,
        "enum_values": [],
        "resolution_source": {
          "tool": "firecrawl",
          "target": "lap-swim schedule or pool timetable on the official site"
        },
        "verification": "lap-lane or lap-swim access before 6:00am is stated on the official schedule",
        "null_policy": "unknown",
        "band": "specific_attributes"
      },
      {
        "label": "Water temperature",
        "question": "The customer named water that is not too warm as a requirement: what temperature is the lap pool maintained at?",
        "value_type": "number_with_unit",
        "unit": "degrees Fahrenheit",
        "enum_values": [],
        "resolution_source": {
          "tool": "firecrawl",
          "target": "pool specifications or aquatics information page on the official site"
        },
        "verification": "temperature stated on the official pool information page",
        "null_policy": "unknown",
        "band": "specific_attributes"
      },
      {
        "label": "Morning lap-swim crowding",
        "question": "The phrase 'not too crowded' is read as the number of swimmers sharing the pool during the customer's morning lap-swim time: is it usually uncrowded, moderately crowded, or crowded?",
        "value_type": "enum",
        "unit": null,
        "enum_values": [
          "uncrowded",
          "moderately crowded",
          "crowded"
        ],
        "resolution_source": {
          "tool": "parallel_web_search",
          "target": "review mentions of morning lap-swim crowding and lane availability"
        },
        "verification": "dominant sentiment across at least 5 reviews specifically mentioning morning crowds or lane sharing",
        "null_policy": "unknown",
        "band": "specific_attributes"
      }
    ]
  },
  {
    "category_id": 1,
    "taxonomy_node": "bakery",
    "depth": "operating_details",
    "predefined_metrics": [
      {
        "label": "name",
        "band": "basic_profile",
        "resolution_source": {
          "tool": "google_maps",
          "target": "places.displayName"
        }
      },
      {
        "label": "category",
        "band": "basic_profile",
        "resolution_source": {
          "tool": "google_maps",
          "target": "places.primaryType"
        }
      },
      {
        "label": "address",
        "band": "basic_profile",
        "resolution_source": {
          "tool": "google_maps",
          "target": "places.formattedAddress"
        }
      },
      {
        "label": "website",
        "band": "basic_profile",
        "resolution_source": {
          "tool": "google_maps",
          "target": "places.websiteUri"
        }
      },
      {
        "label": "place_id",
        "band": "basic_profile",
        "resolution_source": {
          "tool": "google_maps",
          "target": "places.id"
        }
      },
      {
        "label": "coordinates",
        "band": "basic_profile",
        "resolution_source": {
          "tool": "google_maps",
          "target": "places.location"
        }
      },
      {
        "label": "travel distance per mode (walk, drive, cycle)",
        "band": "basic_profile",
        "resolution_source": {
          "tool": "google_maps",
          "target": "routingSummaries.legs.distanceMeters via searchNearby for walk/drive/cycle (one call per mode)"
        }
      },
      {
        "label": "travel duration per mode (walk, drive, cycle)",
        "band": "basic_profile",
        "resolution_source": {
          "tool": "google_maps",
          "target": "routingSummaries.legs.duration via searchNearby for walk/drive/cycle (one call per mode)"
        }
      },
      {
        "label": "transit_details",
        "band": "basic_profile",
        "resolution_source": {
          "tool": "google_maps",
          "target": "Routes API, travelMode TRANSIT (bus, subway, train allowed in the same call)"
        }
      },
      {
        "label": "opening hours",
        "band": "operating_details",
        "resolution_source": {
          "tool": "google_maps",
          "target": "places.regularOpeningHours"
        }
      },
      {
        "label": "contact phone",
        "band": "operating_details",
        "resolution_source": {
          "tool": "google_maps",
          "target": "places.internationalPhoneNumber"
        }
      },
      {
        "label": "rating",
        "band": "operating_details",
        "resolution_source": {
          "tool": "google_maps",
          "target": "places.rating"
        }
      },
      {
        "label": "review volume",
        "band": "operating_details",
        "resolution_source": {
          "tool": "google_maps",
          "target": "places.userRatingCount"
        }
      },
      {
        "label": "price level",
        "band": "operating_details",
        "resolution_source": {
          "tool": "google_maps",
          "target": "places.priceLevel"
        }
      }
    ],
    "specific_metrics": [
      {
        "label": "Bread freshness",
        "question": "The customer explicitly wants a bakery for buying bread on the way home from the pool: is the bread usually fresh when purchased?",
        "value_type": "enum",
        "unit": null,
        "enum_values": [
          "often_stale",
          "mixed",
          "usually_fresh"
        ],
        "resolution_source": {
          "tool": "parallel_web_search",
          "target": "review mentions of bread freshness and baking times"
        },
        "verification": "dominant sentiment across at least 5 reviews mentioning freshness",
        "null_policy": "unknown",
        "band": "operating_details"
      },
      {
        "label": "Bread selection",
        "question": "The customer explicitly wants a bakery for buying bread: is the bread selection limited, moderate, or broad?",
        "value_type": "enum",
        "unit": null,
        "enum_values": [
          "limited",
          "moderate",
          "broad"
        ],
        "resolution_source": {
          "tool": "parallel_web_search",
          "target": "bakery bread menu, product listings, and review mentions of selection"
        },
        "verification": "bread varieties listed on the official site or confirmed by at least 3 listings",
        "null_policy": "unknown",
        "band": "operating_details"
      },
      {
        "label": "Typical purchase queue",
        "question": "The customer explicitly wants to buy bread on the way home from the pool: how long is the typical queue for a purchase?",
        "value_type": "number_with_unit",
        "unit": "minutes",
        "enum_values": [],
        "resolution_source": {
          "tool": "parallel_web_search",
          "target": "review mentions of queue length and checkout wait time"
        },
        "verification": "wait time stated in reviews, with at least 5 reviews supporting the typical range",
        "null_policy": "unknown",
        "band": "operating_details"
      }
    ]
  },
  {
    "category_id": 2,
    "taxonomy_node": "dog_park",
    "depth": "operating_details",
    "predefined_metrics": [
      {
        "label": "name",
        "band": "basic_profile",
        "resolution_source": {
          "tool": "google_maps",
          "target": "places.displayName"
        }
      },
      {
        "label": "category",
        "band": "basic_profile",
        "resolution_source": {
          "tool": "google_maps",
          "target": "places.primaryType"
        }
      },
      {
        "label": "address",
        "band": "basic_profile",
        "resolution_source": {
          "tool": "google_maps",
          "target": "places.formattedAddress"
        }
      },
      {
        "label": "website",
        "band": "basic_profile",
        "resolution_source": {
          "tool": "google_maps",
          "target": "places.websiteUri"
        }
      },
      {
        "label": "place_id",
        "band": "basic_profile",
        "resolution_source": {
          "tool": "google_maps",
          "target": "places.id"
        }
      },
      {
        "label": "coordinates",
        "band": "basic_profile",
        "resolution_source": {
          "tool": "google_maps",
          "target": "places.location"
        }
      },
      {
        "label": "travel distance per mode (walk, drive, cycle)",
        "band": "basic_profile",
        "resolution_source": {
          "tool": "google_maps",
          "target": "routingSummaries.legs.distanceMeters via searchNearby for walk/drive/cycle (one call per mode)"
        }
      },
      {
        "label": "travel duration per mode (walk, drive, cycle)",
        "band": "basic_profile",
        "resolution_source": {
          "tool": "google_maps",
          "target": "routingSummaries.legs.duration via searchNearby for walk/drive/cycle (one call per mode)"
        }
      },
      {
        "label": "transit_details",
        "band": "basic_profile",
        "resolution_source": {
          "tool": "google_maps",
          "target": "Routes API, travelMode TRANSIT (bus, subway, train allowed in the same call)"
        }
      },
      {
        "label": "opening hours",
        "band": "operating_details",
        "resolution_source": {
          "tool": "google_maps",
          "target": "places.regularOpeningHours"
        }
      },
      {
        "label": "contact phone",
        "band": "operating_details",
        "resolution_source": {
          "tool": "google_maps",
          "target": "places.internationalPhoneNumber"
        }
      },
      {
        "label": "rating",
        "band": "operating_details",
        "resolution_source": {
          "tool": "google_maps",
          "target": "places.rating"
        }
      },
      {
        "label": "review volume",
        "band": "operating_details",
        "resolution_source": {
          "tool": "google_maps",
          "target": "places.userRatingCount"
        }
      },
      {
        "label": "price level",
        "band": "operating_details",
        "resolution_source": {
          "tool": "google_maps",
          "target": "places.priceLevel"
        }
      }
    ],
    "specific_metrics": [
      {
        "label": "Secure off-leash fencing",
        "question": "The inferred reasoning shows that the newly adopted puppy needs off-leash time: is the dog park securely fenced for off-leash use?",
        "value_type": "boolean",
        "unit": null,
        "enum_values": [],
        "resolution_source": {
          "tool": "parallel_web_search",
          "target": "official park description and review mentions of fencing and gates"
        },
        "verification": "secure fencing and gated entry stated by the park authority or confirmed by at least 3 listings or reviews",
        "null_policy": "unknown",
        "band": "operating_details"
      },
      {
        "label": "Small-dog area",
        "question": "The inferred reasoning shows that the customer has a puppy needing a safe place to burn energy: is there a separate small-dog or puppy area?",
        "value_type": "boolean",
        "unit": null,
        "enum_values": [],
        "resolution_source": {
          "tool": "parallel_web_search",
          "target": "park facilities descriptions mentioning separate small-dog or puppy areas"
        },
        "verification": "a separate small-dog area is stated by the park authority or official listing",
        "null_policy": "unknown",
        "band": "operating_details"
      },
      {
        "label": "Park cleanliness",
        "question": "The inferred reasoning shows that the puppy needs a regular place to exercise: is the dog park generally clean and free of excessive waste?",
        "value_type": "enum",
        "unit": null,
        "enum_values": [
          "poor",
          "mixed",
          "good"
        ],
        "resolution_source": {
          "tool": "parallel_web_search",
          "target": "review mentions of dog waste, cleanliness, and maintenance"
        },
        "verification": "dominant sentiment across at least 5 reviews mentioning cleanliness or waste",
        "null_policy": "unknown",
        "band": "operating_details"
      },
      {
        "label": "Play-area crowding",
        "question": "The inferred reasoning shows that the puppy needs room to burn energy off leash: is the dog park usually uncrowded, moderately crowded, or crowded?",
        "value_type": "enum",
        "unit": null,
        "enum_values": [
          "uncrowded",
          "moderately crowded",
          "crowded"
        ],
        "resolution_source": {
          "tool": "parallel_web_search",
          "target": "review mentions of crowding, dog density, and available space"
        },
        "verification": "dominant sentiment across at least 5 reviews mentioning crowding or space",
        "null_policy": "unknown",
        "band": "operating_details"
      }
    ]
  },
  {
    "category_id": 3,
    "taxonomy_node": "library",
    "depth": "basic_profile",
    "predefined_metrics": [
      {
        "label": "name",
        "band": "basic_profile",
        "resolution_source": {
          "tool": "google_maps",
          "target": "places.displayName"
        }
      },
      {
        "label": "category",
        "band": "basic_profile",
        "resolution_source": {
          "tool": "google_maps",
          "target": "places.primaryType"
        }
      },
      {
        "label": "address",
        "band": "basic_profile",
        "resolution_source": {
          "tool": "google_maps",
          "target": "places.formattedAddress"
        }
      },
      {
        "label": "website",
        "band": "basic_profile",
        "resolution_source": {
          "tool": "google_maps",
          "target": "places.websiteUri"
        }
      },
      {
        "label": "place_id",
        "band": "basic_profile",
        "resolution_source": {
          "tool": "google_maps",
          "target": "places.id"
        }
      },
      {
        "label": "coordinates",
        "band": "basic_profile",
        "resolution_source": {
          "tool": "google_maps",
          "target": "places.location"
        }
      },
      {
        "label": "travel distance per mode (walk, drive, cycle)",
        "band": "basic_profile",
        "resolution_source": {
          "tool": "google_maps",
          "target": "routingSummaries.legs.distanceMeters via searchNearby for walk/drive/cycle (one call per mode)"
        }
      },
      {
        "label": "travel duration per mode (walk, drive, cycle)",
        "band": "basic_profile",
        "resolution_source": {
          "tool": "google_maps",
          "target": "routingSummaries.legs.duration via searchNearby for walk/drive/cycle (one call per mode)"
        }
      },
      {
        "label": "transit_details",
        "band": "basic_profile",
        "resolution_source": {
          "tool": "google_maps",
          "target": "Routes API, travelMode TRANSIT (bus, subway, train allowed in the same call)"
        }
      }
    ],
    "specific_metrics": []
  }
]

