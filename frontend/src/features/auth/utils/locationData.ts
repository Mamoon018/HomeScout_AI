/** Static country and city options for signup location fields. */
export const COUNTRIES = [
  'United States',
  'United Kingdom',
  'Canada',
  'Germany',
  'France',
  'Australia',
  'India',
  'Japan',
] as const

export const CITIES_BY_COUNTRY: Record<string, string[]> = {
  'United States': ['New York', 'Los Angeles', 'Chicago', 'Houston', 'San Francisco'],
  'United Kingdom': ['London', 'Manchester', 'Birmingham', 'Edinburgh', 'Bristol'],
  Canada: ['Toronto', 'Vancouver', 'Montreal', 'Calgary', 'Ottawa'],
  Germany: ['Berlin', 'Munich', 'Hamburg', 'Frankfurt', 'Cologne'],
  France: ['Paris', 'Lyon', 'Marseille', 'Toulouse', 'Nice'],
  Australia: ['Sydney', 'Melbourne', 'Brisbane', 'Perth', 'Adelaide'],
  India: ['Mumbai', 'Delhi', 'Bangalore', 'Hyderabad', 'Chennai'],
  Japan: ['Tokyo', 'Osaka', 'Kyoto', 'Yokohama', 'Nagoya'],
}

/** Returns cities for a selected country, or an empty list when none is chosen. */
export function getCitiesForCountry(country: string): string[] {
  return CITIES_BY_COUNTRY[country] ?? []
}
