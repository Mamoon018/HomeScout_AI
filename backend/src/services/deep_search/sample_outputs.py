
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






# ==============================================================================
# DISCOVERED PLACES (FULL OUTPUT)
# ==============================================================================

# field masks used per category: ['places.displayName,places.primaryType,places.formattedAddress,places.websiteUri,places.id,places.location,places.googleMapsUri,places.regularOpeningHours,places.internationalPhoneNumber,places.rating,places.userRatingCount,places.priceLevel,places.reviews', 'places.displayName,places.primaryType,places.formattedAddress,places.websiteUri,places.id,places.location,places.googleMapsUri']


{
  "0": {
    "ChIJY4ZI450JvUcRjTDtxXhyNi4": {
      "id": "ChIJY4ZI450JvUcRjTDtxXhyNi4",
      "international_phone_number": "+49 69 2710892200",
      "formatted_address": "Rödelheimer Parkweg 13, 60489 Frankfurt am Main, Germany",
      "location": {
        "latitude": 50.125759699999996,
        "longitude": 8.6198984
      },
      "rating": 4.4,
      "google_maps_uri": "https://maps.google.com/?cid=3329974837529358477&g_mp=Cilnb29nbGUubWFwcy5wbGFjZXMudjEuUGxhY2VzLlNlYXJjaE5lYXJieRACGAQgAA",
      "website_uri": "https://www.frankfurter-baeder.de/freibad-brentanobad/",
      "user_rating_count": 1822,
      "display_name": {
        "text": "Brentanobad",
        "language_code": "en"
      },
      "primary_type": "swimming_pool",
      "reviews": [
        {
          "name": "places/ChIJY4ZI450JvUcRjTDtxXhyNi4/reviews/Ci9DQUlRQUNvZENodHljRjlvT2xkNFJ6RTNOaTFNWjIwNVJuVlRaWGRIWkVSU2JWRRAB",
          "relative_publish_time_description": "2 months ago",
          "rating": 3.0,
          "text": {
            "text": "The pool was decent and the water had perfect temperature, BUT. Having literally one food stand and only a couple more drink stands for the entire pool is a really poor oversight on their part. We spent more than hour waiting to enter, than around 45 minutes for food and once again more than hour for A BOTTLE OF WATER! the prices were okay, but the waiting time was very much not. definitelly bring your own food and drinks.",
            "language_code": "en"
          },
          "original_text": {
            "text": "The pool was decent and the water had perfect temperature, BUT. Having literally one food stand and only a couple more drink stands for the entire pool is a really poor oversight on their part. We spent more than hour waiting to enter, than around 45 minutes for food and once again more than hour for A BOTTLE OF WATER! the prices were okay, but the waiting time was very much not. definitelly bring your own food and drinks.",
            "language_code": "en"
          },
          "author_attribution": {
            "display_name": "Michaela Molnárová",
            "uri": "https://www.google.com/maps/contrib/109084597108931616705/reviews",
            "photo_uri": "https://lh3.googleusercontent.com/a-/ALV-UjV9uYGt5t2QmnWxJC2d4lbzk10feBtG8vqUEDi82Un1xHvvCX6-rg=s128-c0x00000000-cc-rp-mo-ba3"
          },
          "publish_time": "2026-07-04T13:04:28.313719380Z",
          "flag_content_uri": "https://www.google.com/local/content/rap/report?postId=Ci9DQUlRQUNvZENodHljRjlvT2xkNFJ6RTNOaTFNWjIwNVJuVlRaWGRIWkVSU2JWRRAB&d=17924085&t=1",
          "google_maps_uri": "https://www.google.com/maps/reviews/data=!4m6!14m5!1m4!2m3!1sCi9DQUlRQUNvZENodHljRjlvT2xkNFJ6RTNOaTFNWjIwNVJuVlRaWGRIWkVSU2JWRRAB!2m1!1s0x47bd099de3488663:0x2e367278c5ed308d"
        },
        {
          "name": "places/ChIJY4ZI450JvUcRjTDtxXhyNi4/reviews/Ci9DQUlRQUNvZENodHljRjlvT2xoNGFHMUNUVXhLZWkxQlFWSk1URXQxWXpoNVMyYxAB",
          "relative_publish_time_description": "a year ago",
          "rating": 5.0,
          "text": {
            "text": "Great outdoor swimming pool for the summer ☀️ super big (supposedly the biggest in all Europe), clean, with great amenities and greenery.\n\nPerfect full day plan. The pool is clearly divided based on the deepness and there is one big part that is perfect for kids of all ages because it's like a beach: the depth slowly increases from just few centimeters to adult appropriate depth the further you go, so everyone can enjoy it. The only comment here maybe is that there is no shadow at all on this main swimming pool, so take your precautions.\n\nThere are also a couple of slides for kids and adults that are not too high, and a small swimming pool separated form the main one, dedicated only to small children with shadow, an small slide and sparklers.\n\nBoth swimming pools are surrounded by green areas to lay down, and you can also find some chairs and tables spread around.\n\nFinally, you can find food, ice cream and drinks inside the area, so you actually don't need to bring anything if you want.\n\n100% recommended if you are in Frankfurt during summer, it's a must for hot days 😜",
            "language_code": "en"
          },
          "original_text": {
            "text": "Great outdoor swimming pool for the summer ☀️ super big (supposedly the biggest in all Europe), clean, with great amenities and greenery.\n\nPerfect full day plan. The pool is clearly divided based on the deepness and there is one big part that is perfect for kids of all ages because it's like a beach: the depth slowly increases from just few centimeters to adult appropriate depth the further you go, so everyone can enjoy it. The only comment here maybe is that there is no shadow at all on this main swimming pool, so take your precautions.\n\nThere are also a couple of slides for kids and adults that are not too high, and a small swimming pool separated form the main one, dedicated only to small children with shadow, an small slide and sparklers.\n\nBoth swimming pools are surrounded by green areas to lay down, and you can also find some chairs and tables spread around.\n\nFinally, you can find food, ice cream and drinks inside the area, so you actually don't need to bring anything if you want.\n\n100% recommended if you are in Frankfurt during summer, it's a must for hot days 😜",
            "language_code": "en"
          },
          "author_attribution": {
            "display_name": "Nohelvy Peralta",
            "uri": "https://www.google.com/maps/contrib/115126514800384476600/reviews",
            "photo_uri": "https://lh3.googleusercontent.com/a-/ALV-UjUtJVxGQZFoTAQDOQHjAfmDLw_KKdaGk1tiRlTNIvKQula6S510hg=s128-c0x00000000-cc-rp-mo-ba4"
          },
          "publish_time": "2025-08-26T15:14:43.520730554Z",
          "flag_content_uri": "https://www.google.com/local/content/rap/report?postId=Ci9DQUlRQUNvZENodHljRjlvT2xoNGFHMUNUVXhLZWkxQlFWSk1URXQxWXpoNVMyYxAB&d=17924085&t=1",
          "google_maps_uri": "https://www.google.com/maps/reviews/data=!4m6!14m5!1m4!2m3!1sCi9DQUlRQUNvZENodHljRjlvT2xoNGFHMUNUVXhLZWkxQlFWSk1URXQxWXpoNVMyYxAB!2m1!1s0x47bd099de3488663:0x2e367278c5ed308d"
        },
        {
          "name": "places/ChIJY4ZI450JvUcRjTDtxXhyNi4/reviews/Ci9DQUlRQUNvZENodHljRjlvT21Sb2VYSk9XRlZFVVhOSVJreDROamhwYWtaUVRtYxAB",
          "relative_publish_time_description": "a year ago",
          "rating": 5.0,
          "text": {
            "text": "Probably the biggest pool here, divided into 2 zone kids and adults, it’s 1,8m deep for the adult zone and plenty of space to swim, sliding and space to relax too. Toilets are on sites, the fee is only 5€, hundreds of people every day.\nThe water seems to be cleaned but pretty cold 🥶.",
            "language_code": "en"
          },
          "original_text": {
            "text": "Probably the biggest pool here, divided into 2 zone kids and adults, it’s 1,8m deep for the adult zone and plenty of space to swim, sliding and space to relax too. Toilets are on sites, the fee is only 5€, hundreds of people every day.\nThe water seems to be cleaned but pretty cold 🥶.",
            "language_code": "en"
          },
          "author_attribution": {
            "display_name": "Pasan Sensouk",
            "uri": "https://www.google.com/maps/contrib/101861523796909541609/reviews",
            "photo_uri": "https://lh3.googleusercontent.com/a-/ALV-UjWWqT5BK_myNVRTAsDy10jkkdKamv-ZEOELlMZVaveM-XeZBgyv=s128-c0x00000000-cc-rp-mo-ba7"
          },
          "publish_time": "2025-08-12T18:13:36.875241401Z",
          "flag_content_uri": "https://www.google.com/local/content/rap/report?postId=Ci9DQUlRQUNvZENodHljRjlvT21Sb2VYSk9XRlZFVVhOSVJreDROamhwYWtaUVRtYxAB&d=17924085&t=1",
          "google_maps_uri": "https://www.google.com/maps/reviews/data=!4m6!14m5!1m4!2m3!1sCi9DQUlRQUNvZENodHljRjlvT21Sb2VYSk9XRlZFVVhOSVJreDROamhwYWtaUVRtYxAB!2m1!1s0x47bd099de3488663:0x2e367278c5ed308d"
        },
        {
          "name": "places/ChIJY4ZI450JvUcRjTDtxXhyNi4/reviews/ChZDSUhNMG9nS0VJQ0FnSURiOTV5a09REAE",
          "relative_publish_time_description": "2 years ago",
          "rating": 5.0,
          "text": {
            "text": "Very nice place and very clean !!! The pool very big and the area for children in separate ! 😃\nOnly thing I can  say about it that we cannot pay with cards inside so we cannot buy water or drinks or something like that only with cash 💰!!!\nAnd this was for us problem because we cannot drink water or buy something because we don’t have cash money .",
            "language_code": "en"
          },
          "original_text": {
            "text": "Very nice place and very clean !!! The pool very big and the area for children in separate ! 😃\nOnly thing I can  say about it that we cannot pay with cards inside so we cannot buy water or drinks or something like that only with cash 💰!!!\nAnd this was for us problem because we cannot drink water or buy something because we don’t have cash money .",
            "language_code": "en"
          },
          "author_attribution": {
            "display_name": "Nibal Ross",
            "uri": "https://www.google.com/maps/contrib/100224993647581813370/reviews",
            "photo_uri": "https://lh3.googleusercontent.com/a-/ALV-UjWuhNUz0JGdGDdKhfDbnD73G2lHvi7dF2z9QKqCLYrISgliSlU=s128-c0x00000000-cc-rp-mo-ba5"
          },
          "publish_time": "2024-08-10T19:46:08.018451Z",
          "flag_content_uri": "https://www.google.com/local/content/rap/report?postId=ChZDSUhNMG9nS0VJQ0FnSURiOTV5a09REAE&d=17924085&t=1",
          "google_maps_uri": "https://www.google.com/maps/reviews/data=!4m6!14m5!1m4!2m3!1sChZDSUhNMG9nS0VJQ0FnSURiOTV5a09REAE!2m1!1s0x47bd099de3488663:0x2e367278c5ed308d"
        },
        {
          "name": "places/ChIJY4ZI450JvUcRjTDtxXhyNi4/reviews/Ci9DQUlRQUNvZENodHljRjlvT2pWcmVURnZTR2hZZWtkelFsQk1OSGhUWVZKTFFXYxAB",
          "relative_publish_time_description": "2 months ago",
          "rating": 1.0,
          "text": {
            "text": "Absolutely horrible experience with Vorteilskarte - bought on Saturday evening, card empty on Sunday afternoon. 50 € lost? Also claims that smoking is forbidden are nothing but LIES. The so-called smoking ban is not enforced...",
            "language_code": "en"
          },
          "original_text": {
            "text": "Absolutely horrible experience with Vorteilskarte - bought on Saturday evening, card empty on Sunday afternoon. 50 € lost? Also claims that smoking is forbidden are nothing but LIES. The so-called smoking ban is not enforced...",
            "language_code": "en"
          },
          "author_attribution": {
            "display_name": "Ondřej Lébl",
            "uri": "https://www.google.com/maps/contrib/117178005389472638387/reviews",
            "photo_uri": "https://lh3.googleusercontent.com/a-/ALV-UjWb5h52onF4I5taiIEuMOWRp5mejb-bBbq1bDdGMo_fcJfyAnNv=s128-c0x00000000-cc-rp-mo"
          },
          "publish_time": "2026-06-28T12:50:20.157888632Z",
          "flag_content_uri": "https://www.google.com/local/content/rap/report?postId=Ci9DQUlRQUNvZENodHljRjlvT2pWcmVURnZTR2hZZWtkelFsQk1OSGhUWVZKTFFXYxAB&d=17924085&t=1",
          "google_maps_uri": "https://www.google.com/maps/reviews/data=!4m6!14m5!1m4!2m3!1sCi9DQUlRQUNvZENodHljRjlvT2pWcmVURnZTR2hZZWtkelFsQk1OSGhUWVZKTFFXYxAB!2m1!1s0x47bd099de3488663:0x2e367278c5ed308d"
        }
      ],
      "name": "",
      "types": [],
      "national_phone_number": "",
      "short_formatted_address": "",
      "address_components": [],
      "photos": [],
      "adr_format_address": "",
      "business_status": 0,
      "price_level": 0,
      "attributions": [],
      "icon_mask_base_uri": "",
      "icon_background_color": "",
      "current_secondary_opening_hours": [],
      "regular_secondary_opening_hours": [],
      "sub_destinations": [],
      "containing_places": [],
      "moved_place": "",
      "moved_place_id": ""
    }
  },
  "1": {
    "ChIJ8XQv_QIJvUcROkzXexWdpvo": {
      "id": "ChIJ8XQv_QIJvUcROkzXexWdpvo",
      "formatted_address": "Hausener Brückweg 5, 60488 Frankfurt am Main, Germany",
      "location": {
        "latitude": 50.1326342,
        "longitude": 8.6259742
      },
      "google_maps_uri": "https://maps.google.com/?cid=18061296071213534266&g_mp=Cilnb29nbGUubWFwcy5wbGFjZXMudjEuUGxhY2VzLlNlYXJjaE5lYXJieRACGAQgAA",
      "website_uri": "https://heberer.de/",
      "display_name": {
        "text": "Wiener Feinbäcker Heberer",
        "language_code": "de"
      },
      "primary_type": "bakery",
      "name": "",
      "types": [],
      "national_phone_number": "",
      "international_phone_number": "",
      "short_formatted_address": "",
      "address_components": [],
      "rating": 0.0,
      "reviews": [],
      "photos": [],
      "adr_format_address": "",
      "business_status": 0,
      "price_level": 0,
      "attributions": [],
      "icon_mask_base_uri": "",
      "icon_background_color": "",
      "current_secondary_opening_hours": [],
      "regular_secondary_opening_hours": [],
      "sub_destinations": [],
      "containing_places": [],
      "moved_place": "",
      "moved_place_id": ""
    },
    "ChIJb639J9UJvUcRQ7zplnNAkC0": {
      "id": "ChIJb639J9UJvUcRQ7zplnNAkC0",
      "formatted_address": "Alt-Hausen 14, 60488 Frankfurt am Main, Germany",
      "location": {
        "latitude": 50.132419999999996,
        "longitude": 8.624839999999999
      },
      "google_maps_uri": "https://maps.google.com/?cid=3283194993550408771&g_mp=Cilnb29nbGUubWFwcy5wbGFjZXMudjEuUGxhY2VzLlNlYXJjaE5lYXJieRACGAQgAA",
      "website_uri": "http://www.fingerfood-company.de/",
      "display_name": {
        "text": "THE DAILY COFFEE KITCHEN AND BAKERY",
        "language_code": "de"
      },
      "primary_type": "bakery",
      "name": "",
      "types": [],
      "national_phone_number": "",
      "international_phone_number": "",
      "short_formatted_address": "",
      "address_components": [],
      "rating": 0.0,
      "reviews": [],
      "photos": [],
      "adr_format_address": "",
      "business_status": 0,
      "price_level": 0,
      "attributions": [],
      "icon_mask_base_uri": "",
      "icon_background_color": "",
      "current_secondary_opening_hours": [],
      "regular_secondary_opening_hours": [],
      "sub_destinations": [],
      "containing_places": [],
      "moved_place": "",
      "moved_place_id": ""
    },
    "ChIJ3ThJAmwJvUcRiJWH23UG-F0": {
      "id": "ChIJ3ThJAmwJvUcRiJWH23UG-F0",
      "formatted_address": "Grempstraße 33, 60487 Frankfurt am Main, Germany",
      "location": {
        "latitude": 50.1251781,
        "longitude": 8.6383346
      },
      "google_maps_uri": "https://maps.google.com/?cid=6771169143015576968&g_mp=Cilnb29nbGUubWFwcy5wbGFjZXMudjEuUGxhY2VzLlNlYXJjaE5lYXJieRACGAQgAA",
      "website_uri": "https://schaan.de/",
      "display_name": {
        "text": "Bäckerei Schaan",
        "language_code": "de"
      },
      "primary_type": "bakery",
      "name": "",
      "types": [],
      "national_phone_number": "",
      "international_phone_number": "",
      "short_formatted_address": "",
      "address_components": [],
      "rating": 0.0,
      "reviews": [],
      "photos": [],
      "adr_format_address": "",
      "business_status": 0,
      "price_level": 0,
      "attributions": [],
      "icon_mask_base_uri": "",
      "icon_background_color": "",
      "current_secondary_opening_hours": [],
      "regular_secondary_opening_hours": [],
      "sub_destinations": [],
      "containing_places": [],
      "moved_place": "",
      "moved_place_id": ""
    },
    "ChIJCwqRAAAJvUcRV9YCH7wnLw8": {
      "id": "ChIJCwqRAAAJvUcRV9YCH7wnLw8",
      "formatted_address": "Fröbelstraße 2, 60487 Frankfurt am Main, Germany",
      "location": {
        "latitude": 50.123603499999994,
        "longitude": 8.637477900000002
      },
      "google_maps_uri": "https://maps.google.com/?cid=1094136923401934423&g_mp=Cilnb29nbGUubWFwcy5wbGFjZXMudjEuUGxhY2VzLlNlYXJjaE5lYXJieRACGAQgAA",
      "display_name": {
        "text": "Frisch Balkan Bäckerei",
        "language_code": "de"
      },
      "primary_type": "bakery",
      "name": "",
      "types": [],
      "national_phone_number": "",
      "international_phone_number": "",
      "short_formatted_address": "",
      "address_components": [],
      "rating": 0.0,
      "website_uri": "",
      "reviews": [],
      "photos": [],
      "adr_format_address": "",
      "business_status": 0,
      "price_level": 0,
      "attributions": [],
      "icon_mask_base_uri": "",
      "icon_background_color": "",
      "current_secondary_opening_hours": [],
      "regular_secondary_opening_hours": [],
      "sub_destinations": [],
      "containing_places": [],
      "moved_place": "",
      "moved_place_id": ""
    },
    "ChIJIVDnAVkJvUcR0QoIz_ep6MA": {
      "id": "ChIJIVDnAVkJvUcR0QoIz_ep6MA",
      "formatted_address": "Joachim-Biermann-Straße 5, 60486 Frankfurt am Main, Germany",
      "location": {
        "latitude": 50.120715499999996,
        "longitude": 8.6285983
      },
      "google_maps_uri": "https://maps.google.com/?cid=13900547131674462929&g_mp=Cilnb29nbGUubWFwcy5wbGFjZXMudjEuUGxhY2VzLlNlYXJjaE5lYXJieRACGAQgAA",
      "website_uri": "https://cafe-ernst.de/",
      "display_name": {
        "text": "Cafe Ernst",
        "language_code": "de"
      },
      "primary_type": "bakery",
      "name": "",
      "types": [],
      "national_phone_number": "",
      "international_phone_number": "",
      "short_formatted_address": "",
      "address_components": [],
      "rating": 0.0,
      "reviews": [],
      "photos": [],
      "adr_format_address": "",
      "business_status": 0,
      "price_level": 0,
      "attributions": [],
      "icon_mask_base_uri": "",
      "icon_background_color": "",
      "current_secondary_opening_hours": [],
      "regular_secondary_opening_hours": [],
      "sub_destinations": [],
      "containing_places": [],
      "moved_place": "",
      "moved_place_id": ""
    },
    "ChIJWxyNJKoJvUcRWzaRMflxw5o": {
      "id": "ChIJWxyNJKoJvUcRWzaRMflxw5o",
      "formatted_address": "Thudichumstraße 20, 60489 Frankfurt am Main-Frankfurt-Mitte-West, Germany",
      "location": {
        "latitude": 50.126837099999996,
        "longitude": 8.6137053
      },
      "google_maps_uri": "https://maps.google.com/?cid=11151882417391875675&g_mp=Cilnb29nbGUubWFwcy5wbGFjZXMudjEuUGxhY2VzLlNlYXJjaE5lYXJieRACGAQgAA",
      "website_uri": "https://www.baeckerei-huck.de/",
      "display_name": {
        "text": "Bäckerei und Konditorei Huck",
        "language_code": "de"
      },
      "primary_type": "bakery",
      "name": "",
      "types": [],
      "national_phone_number": "",
      "international_phone_number": "",
      "short_formatted_address": "",
      "address_components": [],
      "rating": 0.0,
      "reviews": [],
      "photos": [],
      "adr_format_address": "",
      "business_status": 0,
      "price_level": 0,
      "attributions": [],
      "icon_mask_base_uri": "",
      "icon_background_color": "",
      "current_secondary_opening_hours": [],
      "regular_secondary_opening_hours": [],
      "sub_destinations": [],
      "containing_places": [],
      "moved_place": "",
      "moved_place_id": ""
    },
    "ChIJi4FnoFYJvUcRlv2TFQfMI40": {
      "id": "ChIJi4FnoFYJvUcRlv2TFQfMI40",
      "formatted_address": "Westring 44, 60488 Frankfurt am Main-Frankfurt-Mitte-West, Germany",
      "location": {
        "latitude": 50.1334308,
        "longitude": 8.6124485
      },
      "google_maps_uri": "https://maps.google.com/?cid=10170196714331569558&g_mp=Cilnb29nbGUubWFwcy5wbGFjZXMudjEuUGxhY2VzLlNlYXJjaE5lYXJieRACGAQgAA",
      "display_name": {
        "text": "SB Bäckerei & Kiosk",
        "language_code": "pl"
      },
      "primary_type": "bakery",
      "name": "",
      "types": [],
      "national_phone_number": "",
      "international_phone_number": "",
      "short_formatted_address": "",
      "address_components": [],
      "rating": 0.0,
      "website_uri": "",
      "reviews": [],
      "photos": [],
      "adr_format_address": "",
      "business_status": 0,
      "price_level": 0,
      "attributions": [],
      "icon_mask_base_uri": "",
      "icon_background_color": "",
      "current_secondary_opening_hours": [],
      "regular_secondary_opening_hours": [],
      "sub_destinations": [],
      "containing_places": [],
      "moved_place": "",
      "moved_place_id": ""
    },
    "ChIJ2WrzCwAJvUcRkdQ0_vvX6Qg": {
      "id": "ChIJ2WrzCwAJvUcRkdQ0_vvX6Qg",
      "formatted_address": "Ginnheimer Landstraße 49, 60487 Frankfurt am Main-Innenstadt II, Germany",
      "location": {
        "latitude": 50.134336499999996,
        "longitude": 8.6449293
      },
      "google_maps_uri": "https://maps.google.com/?cid=642281899178644625&g_mp=Cilnb29nbGUubWFwcy5wbGFjZXMudjEuUGxhY2VzLlNlYXJjaE5lYXJieRACGAQgAA",
      "display_name": {
        "text": "Makkabi bäckerei",
        "language_code": "de"
      },
      "primary_type": "bakery",
      "name": "",
      "types": [],
      "national_phone_number": "",
      "international_phone_number": "",
      "short_formatted_address": "",
      "address_components": [],
      "rating": 0.0,
      "website_uri": "",
      "reviews": [],
      "photos": [],
      "adr_format_address": "",
      "business_status": 0,
      "price_level": 0,
      "attributions": [],
      "icon_mask_base_uri": "",
      "icon_background_color": "",
      "current_secondary_opening_hours": [],
      "regular_secondary_opening_hours": [],
      "sub_destinations": [],
      "containing_places": [],
      "moved_place": "",
      "moved_place_id": ""
    },
    "ChIJjy3sREcJvUcR6HXVuNC9D74": {
      "id": "ChIJjy3sREcJvUcR6HXVuNC9D74",
      "formatted_address": "Leipziger Str. 63-65, 60487 Frankfurt am Main-Innenstadt II, Germany",
      "location": {
        "latitude": 50.1230389,
        "longitude": 8.6439959
      },
      "google_maps_uri": "https://maps.google.com/?cid=13695373696008812008&g_mp=Cilnb29nbGUubWFwcy5wbGFjZXMudjEuUGxhY2VzLlNlYXJjaE5lYXJieRACGAQgAA",
      "website_uri": "https://heberer.de/",
      "display_name": {
        "text": "Wiener Feinbäcker Heberer",
        "language_code": "de"
      },
      "primary_type": "bakery",
      "name": "",
      "types": [],
      "national_phone_number": "",
      "international_phone_number": "",
      "short_formatted_address": "",
      "address_components": [],
      "rating": 0.0,
      "reviews": [],
      "photos": [],
      "adr_format_address": "",
      "business_status": 0,
      "price_level": 0,
      "attributions": [],
      "icon_mask_base_uri": "",
      "icon_background_color": "",
      "current_secondary_opening_hours": [],
      "regular_secondary_opening_hours": [],
      "sub_destinations": [],
      "containing_places": [],
      "moved_place": "",
      "moved_place_id": ""
    },
    "ChIJtxtvpJsJvUcR53-lMBQWKzE": {
      "id": "ChIJtxtvpJsJvUcR53-lMBQWKzE",
      "formatted_address": "Radilostraße 10, 60489 Frankfurt am Main-Frankfurt-Mitte-West, Germany",
      "location": {
        "latitude": 50.1249811,
        "longitude": 8.6102051
      },
      "google_maps_uri": "https://maps.google.com/?cid=3542949807828336615&g_mp=Cilnb29nbGUubWFwcy5wbGFjZXMudjEuUGxhY2VzLlNlYXJjaE5lYXJieRACGAQgAA",
      "website_uri": "http://der-baecker-eifler.de/",
      "display_name": {
        "text": "Der Bäcker Eifler",
        "language_code": "de"
      },
      "primary_type": "bakery",
      "name": "",
      "types": [],
      "national_phone_number": "",
      "international_phone_number": "",
      "short_formatted_address": "",
      "address_components": [],
      "rating": 0.0,
      "reviews": [],
      "photos": [],
      "adr_format_address": "",
      "business_status": 0,
      "price_level": 0,
      "attributions": [],
      "icon_mask_base_uri": "",
      "icon_background_color": "",
      "current_secondary_opening_hours": [],
      "regular_secondary_opening_hours": [],
      "sub_destinations": [],
      "containing_places": [],
      "moved_place": "",
      "moved_place_id": ""
    }
  }
}

