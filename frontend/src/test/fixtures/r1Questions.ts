import type { ClarificationQuestion } from '@/features/search-progress/types/clarification'

/**
 * R1 questions as a `needs_answers` run returns them. Each answers one ambiguity flag of the
 * extraction, matched by `category_id`. Test fixture.
 */
export const QUESTIONS: ClarificationQuestion[] = [
  {
    category_id: 7,
    category: 'a balcony or small garden',
    question:
      'When you say a balcony or small garden, which of these is closest to what you meant?',
    options: [
      'a private balcony or loggia',
      'a shared courtyard garden',
      'a ground-floor patio with garden access',
      'a rooftop terrace',
      'other',
    ],
  },
]
