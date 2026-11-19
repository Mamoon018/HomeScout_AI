import { MIN_BRIEF_WORDS } from '@/features/composer/utils/briefWords'

/**
 * What the renter reads when the server refuses the brief. The server's own sentence is a
 * developer message ("Instructions must be of more than 100 words"), so known reasons are
 * rewritten and anything else is shown as sent.
 */
export function briefRejectionCopy(message: string): string {
  if (/english/i.test(message)) {
    return 'HomeScout reads briefs written in English for now. Please write yours in English.'
  }
  if (/words/i.test(message)) {
    return `Your brief needs at least ${MIN_BRIEF_WORDS} words so HomeScout can read it properly.`
  }
  return message || 'HomeScout could not accept this brief. Check it and send it again.'
}

export const ANSWERS_REJECTED_COPY =
  "Those answers didn't match the questions. Check them and try again."
