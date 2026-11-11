import type React from 'react'
import {
  Building2,
  FileBarChart,
  HouseHeart,
  MessagesSquare,
  Puzzle,
  Star,
} from 'lucide-react'
import {
  GridFeatureCards,
  type FeatureType,
} from '@/components/ui/grid-feature-cards'
import {
  AnalysisReportResultsPanel,
  CommunicationResultsPanel,
  DeepSearchResultsPanel,
  HomeWishlistResultsPanel,
  MatchingEngineResultsPanel,
  UserFeedbackResultsPanel,
} from '@/features/auth/components/signup-feature-secondary-content'

const features: FeatureType[] = [
  {
    title: 'Home Wishlist',
    icon: HouseHeart,
    iconClassName: 'text-amber-400',
    borderClassName: 'border-amber-400/50',
    buttonBorderClassName: 'border-amber-400 dark:border-amber-400',
    neonBorderClassName: 'secondary-neon-amber',
    accentDark: '#FBBF24',
    accentOlive: '#FCD34D',
    description: 'Tell us what matters to you!',
    secondaryContent: <HomeWishlistResultsPanel />,
  },
  {
    title: 'Deep Search',
    icon: Building2,
    iconClassName: 'text-sky-400',
    borderClassName: 'border-sky-400/50',
    buttonBorderClassName: 'border-sky-400 dark:border-sky-400',
    neonBorderClassName: 'secondary-neon-sky',
    accentDark: '#38BDF8',
    accentOlive: '#7DD3FC',
    description:
      'Scan neighborhoods, filters, and listings across multiple sources at once.',
    secondaryContent: <DeepSearchResultsPanel />,
  },
  {
    title: 'Analysis Report',
    icon: FileBarChart,
    iconClassName: 'text-emerald-400',
    borderClassName: 'border-emerald-400/50',
    buttonBorderClassName: 'border-emerald-400 dark:border-emerald-400',
    neonBorderClassName: 'secondary-neon-emerald',
    accentDark: '#34D399',
    accentOlive: '#A8D5C6',
    description:
      'Get composite scores on value, condition, location, marts, & critical city points.',
    secondaryContent: <AnalysisReportResultsPanel />,
  },
  {
    title: 'Matching Engine',
    icon: Puzzle,
    iconClassName: 'text-violet-400',
    borderClassName: 'border-violet-400/50',
    buttonBorderClassName: 'border-violet-400 dark:border-violet-400',
    neonBorderClassName: 'secondary-neon-violet',
    accentDark: '#A78BFA',
    accentOlive: '#F9A8D4',
    description:
      'Weigh dozens of signals to surface homes that truly fit your priorities.',
    secondaryContent: <MatchingEngineResultsPanel />,
  },
  {
    title: 'Owners Outreach',
    icon: MessagesSquare,
    iconClassName: 'text-orange-400',
    borderClassName: 'border-orange-400/50',
    buttonBorderClassName: 'border-orange-400 dark:border-orange-400',
    neonBorderClassName: 'secondary-neon-orange',
    accentDark: '#FB923C',
    accentOlive: '#FDBA74',
    description:
      'Coordinate messages, inquiry requests, and follow-ups with owners in one thread.',
    secondaryContent: <CommunicationResultsPanel />,
  },
  {
    title: 'User Feedback',
    icon: Star,
    iconClassName: 'text-fuchsia-400',
    borderClassName: 'border-fuchsia-400/50',
    buttonBorderClassName: 'border-fuchsia-400 dark:border-fuchsia-400',
    neonBorderClassName: 'secondary-neon-fuchsia',
    accentDark: '#E879F9',
    accentOlive: '#FCA5A5',
    description:
      'Keeps you in loop on search updates and critical communication stages.',
    secondaryContent: <UserFeedbackResultsPanel />,
  },
]

/** Signup page feature highlights composed from the shared grid card UI. */
export function SignupFeatureGrid({
  className,
  ...props
}: React.ComponentProps<'div'>) {
  return (
    <GridFeatureCards features={features} className={className} {...props} />
  )
}
