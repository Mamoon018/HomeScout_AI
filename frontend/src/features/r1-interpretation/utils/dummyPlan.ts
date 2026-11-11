import type {
  CategoryMetricPlan,
  PredefinedMetric,
} from '@/features/r1-interpretation/types/r1'

function gm(
  band: PredefinedMetric['band'],
  label: string,
  target: string,
): PredefinedMetric {
  return { band, label, resolution_source: { tool: 'google_maps', target } }
}

const ROUTE_MODES = 'routingSummaries.legs'
const TRANSIT = 'Routes API computeRouteMatrix'

/** The same Google Maps fact list R1 attaches to every category. */
const PREDEFINED_METRICS: PredefinedMetric[] = [
  gm('basic_profile', 'name', 'places.displayName'),
  gm('basic_profile', 'category', 'places.primaryType'),
  gm('basic_profile', 'address', 'places.formattedAddress'),
  gm('basic_profile', 'website', 'places.websiteUri'),
  gm('basic_profile', 'place_id', 'places.id'),
  gm('basic_profile', 'coordinates', 'places.location'),
  gm(
    'basic_profile',
    'travel distance per mode (walk, drive, cycle)',
    `${ROUTE_MODES}.distanceMeters via searchNearby for walk/drive/cycle (one call per mode)`,
  ),
  gm(
    'basic_profile',
    'travel duration per mode (walk, drive, cycle)',
    `${ROUTE_MODES}.duration via searchNearby for walk/drive/cycle (one call per mode)`,
  ),
  gm(
    'basic_profile',
    'transit travel distance',
    `${TRANSIT} distanceMeters, travelMode TRANSIT (bus, subway, train allowed in the same call)`,
  ),
  gm(
    'basic_profile',
    'transit travel duration',
    `${TRANSIT} duration, travelMode TRANSIT (bus, subway, train allowed in the same call)`,
  ),
  gm('basic_profile', 'google_maps_uri', 'places.googleMapsUri'),
  gm('operating_details', 'opening hours', 'places.regularOpeningHours'),
  gm('operating_details', 'contact phone', 'places.internationalPhoneNumber'),
  gm('operating_details', 'rating', 'places.rating'),
  gm('operating_details', 'review volume', 'places.userRatingCount'),
  gm('operating_details', 'price level', 'places.priceLevel'),
  gm('operating_details', 'reviews', 'places.reviews'),
]

/**
 * Sample finished R1 output (the `result` of a finished run), trimmed to two categories.
 * Replace with the real run view once the endpoint is wired.
 */
export const DUMMY_PLAN: CategoryMetricPlan[] = [
  {
    depth: 'operating_details',
    category_id: 2,
    taxonomy_node: 'transit_station',
    specific_metrics: [
      {
        band: 'operating_details',
        unit: null,
        label: 'Rail service type',
        question:
          'The customer explicitly wants a transit station within a short walk: does the station serve the U-Bahn, S-Bahn, or both?',
        value_type: 'enum',
        enum_values: ['U-Bahn', 'S-Bahn', 'both'],
        null_policy: 'unknown',
        verification: 'The station is explicitly listed as a stop for each service included in the value.',
        evidence_class: 'factual',
        resolution_source: {
          web_target: 'U-Bahn and S-Bahn services stopping at the station',
          review_target: null,
          scrape_target:
            "station services or network information page on the transit operator's official site",
        },
      },
    ],
    predefined_metrics: PREDEFINED_METRICS,
  },
  {
    depth: 'operating_details',
    category_id: 3,
    taxonomy_node: 'supermarket',
    specific_metrics: [
      {
        band: 'operating_details',
        unit: null,
        label: 'Fresh produce quality',
        question:
          'The customer explicitly says they cook at home a lot and wants a nearby supermarket: how do customers describe the quality of its fresh produce?',
        value_type: 'enum',
        enum_values: ['poor', 'mixed', 'good'],
        null_policy: 'unknown',
        verification:
          'The dominant sentiment across at least 5 reviews specifically mentioning fresh produce supports the value.',
        evidence_class: 'experiential',
        resolution_source: {
          web_target: 'customer experiences of fresh fruit and vegetable quality at the supermarket',
          review_target: 'mentions of freshness or quality of fruit and vegetables in customer reviews',
          scrape_target: null,
        },
      },
    ],
    predefined_metrics: PREDEFINED_METRICS,
  },
]
