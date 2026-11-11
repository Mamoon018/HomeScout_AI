import type { ExtractionOutput } from '@/features/r1-interpretation/types/r1'

/**
 * Sample extraction output (`data` of the extraction step). Replace with the real
 * run view once the endpoint is wired.
 */
export const DUMMY_EXTRACTION: ExtractionOutput = {
  persona_facts: [
    'relocating to Munich in February',
    'relocating with partner',
    'both start new jobs there',
    'office is near Marienplatz',
    'partner works in Schwabing',
    'cook at home a lot',
    'both go to the gym several times a week',
    'weekend walks',
  ],
  ambiguity_flags: [
    {
      phrase: 'a balcony or small garden',
      target: 'category',
      category: null,
      category_id: 7,
      characteristic: null,
    },
  ],
  explicit_categories: [
    {
      name: 'apartment for rent',
      category_id: 0,
      characteristics: [
        'two bedroom',
        'at least 65 square meters',
        'total monthly rent below 1800 euros including utilities',
      ],
    },
    {
      name: 'easy commute for both of us',
      category_id: 1,
      characteristics: ['ideally under 35 minutes by public transport'],
    },
    { name: 'U-Bahn or S-Bahn station', category_id: 2, characteristics: ['within a short walk'] },
    { name: 'supermarket', category_id: 3, characteristics: ['within walking distance'] },
    { name: 'fitted kitchen', category_id: 4, characteristics: [] },
    { name: 'gym', category_id: 5, characteristics: ['nearby'] },
    { name: 'residential street', category_id: 6, characteristics: ['quiet'] },
    { name: 'a balcony or small garden', category_id: 7, characteristics: [] },
    { name: 'building with an elevator', category_id: 8, characteristics: [] },
    { name: 'park', category_id: 9, characteristics: ['close by'] },
  ],
}
