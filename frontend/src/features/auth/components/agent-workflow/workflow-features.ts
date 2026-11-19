import type { ComponentType } from 'react'
import {
  Building2,
  FileBarChart,
  HouseHeart,
  MessagesSquare,
  Puzzle,
  Star,
  type LucideIcon,
} from 'lucide-react'
import {
  AnalysisReportContent,
  DeepSearchContent,
  HomeWishlistContent,
  MatchingEngineContent,
  OwnersOutreachContent,
  UserFeedbackContent,
} from './agent-workflow-content'

export type WorkflowFeature = {
  title: string
  accent: string
  icon: LucideIcon
  /** Owners Outreach and User Feedback use a tighter 8px content gap. */
  compact?: boolean
  Content: ComponentType
}

/** Feature order is the workflow order: the agent runs them left to right. */
export const WORKFLOW_FEATURES: WorkflowFeature[] = [
  { title: 'Home Wishlist', accent: '#9A6B00', icon: HouseHeart, Content: HomeWishlistContent },
  { title: 'Deep Search', accent: '#1D6FA3', icon: Building2, Content: DeepSearchContent },
  { title: 'Analysis Report', accent: '#1F7A80', icon: FileBarChart, Content: AnalysisReportContent },
  { title: 'Matching Engine', accent: '#B0306E', icon: Puzzle, Content: MatchingEngineContent },
  { title: 'Owners Outreach', accent: '#B35A12', icon: MessagesSquare, compact: true, Content: OwnersOutreachContent },
  { title: 'User Feedback', accent: '#B3302F', icon: Star, compact: true, Content: UserFeedbackContent },
]
