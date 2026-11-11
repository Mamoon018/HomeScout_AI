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
  { title: 'Home Wishlist', accent: '#FCD34D', icon: HouseHeart, Content: HomeWishlistContent },
  { title: 'Deep Search', accent: '#7DD3FC', icon: Building2, Content: DeepSearchContent },
  { title: 'Analysis Report', accent: '#A8D5C6', icon: FileBarChart, Content: AnalysisReportContent },
  { title: 'Matching Engine', accent: '#F9A8D4', icon: Puzzle, Content: MatchingEngineContent },
  { title: 'Owners Outreach', accent: '#FDBA74', icon: MessagesSquare, compact: true, Content: OwnersOutreachContent },
  { title: 'User Feedback', accent: '#FCA5A5', icon: Star, compact: true, Content: UserFeedbackContent },
]
