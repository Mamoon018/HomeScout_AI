import type { ClarificationQuestion } from '@/features/search-progress/types/clarification'

/**
 * Sample R1 questions (shape of a `needs_answers` run). Each question answers one ambiguity
 * flag of the extraction step, matched by `category_id`. Replace with the questions returned
 * by the real run once the endpoint is wired.
 */
export const DUMMY_CLARIFICATION_QUESTIONS: ClarificationQuestion[] = [
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
