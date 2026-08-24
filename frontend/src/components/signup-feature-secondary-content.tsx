import {
  Building2,
  HelpCircle,
  MessageSquare,
  TrendingUp,
} from 'lucide-react'
import { cn } from '@/lib/utils'

type SecondaryPanelProps = {
  className?: string
}

/** Preference questions for Home Wishlist. */
export function HomeWishlistResultsPanel({ className }: SecondaryPanelProps) {
  const preferenceQuestions = [
    {
      question: 'What size home fits your household?',
      detail: 'Beds, layout, and square footage',
    },
    {
      question: 'What price range are you targeting?',
      detail: 'Budget ceiling and monthly comfort zone',
    },
    {
      question: 'Which locations are you open to?',
      detail: 'Neighborhoods, commute radius, and must-have areas',
    },
  ]

  return (
    <div className={cn('flex h-full flex-col gap-3', className)}>
      <p className="text-muted-foreground text-xs uppercase tracking-wider">
        Your preferences
      </p>
      <div className="flex flex-col gap-2">
        {preferenceQuestions.map((item) => (
          <div
            key={item.question}
            className="border-amber-400/25 bg-amber-400/5 flex items-start gap-3 rounded-md border px-3 py-2.5"
          >
            <HelpCircle className="text-amber-400 mt-0.5 size-4 shrink-0" />
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium leading-snug">{item.question}</p>
              <p className="text-muted-foreground mt-0.5 text-xs leading-relaxed">
                {item.detail}
              </p>
            </div>
          </div>
        ))}
      </div>
      <div className="border-border/50 mt-auto rounded-md border border-dashed px-3 py-2">
        <p className="text-muted-foreground text-xs leading-relaxed">
          We capture your answers first so every search starts aligned with your priorities.
        </p>
      </div>
    </div>
  )
}

/** Live search signals for Deep Search. */
export function DeepSearchResultsPanel({ className }: SecondaryPanelProps) {
  const filters = [
    { label: 'Radius', value: '2.5 mi' },
    { label: 'Budget', value: '$350–$520k' },
    { label: 'Listings', value: '128 found' },
  ]

  return (
    <div className={cn('flex h-full flex-col gap-3', className)}>
      <div className="border-sky-400/30 bg-sky-400/10 flex items-center gap-2 rounded-md border px-3 py-2">
        <Building2 className="text-sky-400 size-4" />
        <p className="text-sm font-medium">Scanning 6 neighborhoods</p>
      </div>
      <div className="grid grid-cols-3 gap-2">
        {filters.map((filter) => (
          <div
            key={filter.label}
            className="border-border/50 bg-muted/15 rounded-md border px-2 py-2 text-center"
          >
            <p className="text-muted-foreground text-[10px] uppercase">{filter.label}</p>
            <p className="text-sky-400 mt-0.5 font-mono text-xs">{filter.value}</p>
          </div>
        ))}
      </div>
      <div className="flex flex-1 flex-col justify-end gap-1.5">
        {['Waterfront district', 'Arts quarter', 'Metro north'].map((zone, index) => (
          <div key={zone} className="flex items-center gap-2">
            <div
              className="bg-sky-400 h-1.5 rounded-full"
              style={{ width: `${72 - index * 14}%` }}
            />
            <span className="text-muted-foreground shrink-0 text-xs">{zone}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

/** Score breakdown for Analysis Report. */
export function AnalysisReportResultsPanel({ className }: SecondaryPanelProps) {
  const scores = [
    { label: 'Location fit', score: 92 },
    { label: 'Value index', score: 87 },
    { label: 'Condition', score: 79 },
    { label: 'Critical Points access', score: 84 },
  ]

  return (
    <div className={cn('flex h-full flex-col gap-3', className)}>
      <div className="flex items-end justify-between">
        <div>
          <p className="text-muted-foreground text-xs uppercase tracking-wider">
            Composite score
          </p>
          <p className="text-emerald-400 text-3xl font-medium leading-none">88</p>
        </div>
        <TrendingUp className="text-emerald-400 size-5" />
      </div>
      <div className="space-y-2.5">
        {scores.map((item) => (
          <div key={item.label} className="space-y-1">
            <div className="flex justify-between text-xs">
              <span>{item.label}</span>
              <span className="text-emerald-400 font-mono">{item.score}</span>
            </div>
            <div className="bg-muted/40 h-1 overflow-hidden rounded-full">
              <div
                className="bg-emerald-400/80 h-full rounded-full"
                style={{ width: `${item.score}%` }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

/** Match matrix for Matching Engine. */
export function MatchingEngineResultsPanel({ className }: SecondaryPanelProps) {
  const matches = [
    { home: 'Linden Ave #214', match: 96 },
    { home: 'Harbor Walk #12', match: 91 },
    { home: 'Oak Court #15', match: 88 },
  ]

  return (
    <div className={cn('flex h-full flex-col gap-2.5', className)}>
      <p className="text-muted-foreground text-[10px] uppercase tracking-wider">
        Top alignments
      </p>
      <div className="grid grid-cols-2 gap-1.5">
        {matches.map((item) => (
          <div
            key={item.home}
            className="border-violet-400/25 col-span-2 flex items-center justify-between rounded-md border px-2.5 py-1.5 first:col-span-2"
          >
            <span className="truncate text-xs">{item.home}</span>
            <span className="text-violet-400 font-mono text-xs">{item.match}%</span>
          </div>
        ))}
      </div>
      <div className="border-violet-400/20 bg-violet-400/5 mt-auto grid grid-cols-2 gap-1.5 rounded-md border p-1.5">
        <div className="text-center">
          <p className="text-violet-400 text-base font-medium">14</p>
          <p className="text-muted-foreground text-[9px]">Signals weighed</p>
        </div>
        <div className="text-center">
          <p className="text-violet-400 text-base font-medium">3</p>
          <p className="text-muted-foreground text-[9px]">Perfect fits</p>
        </div>
      </div>
    </div>
  )
}

/** Message thread preview for Owners Outreach. */
export function CommunicationResultsPanel({ className }: SecondaryPanelProps) {
  const messages = [
    { from: 'Agent', text: 'Is parking spot included?', time: '2:14 PM' },
    { from: 'Owner', text: 'Yes — one covered spot included.', time: '2:18 PM' },
    { from: 'Agent', text: 'Owner open to a Friday viewing.', time: '2:21 PM' },
  ]

  return (
    <div className={cn('flex h-full flex-col gap-2', className)}>
      <div className="flex items-center gap-2">
        <MessageSquare className="text-orange-400 size-3.5" />
        <p className="text-xs font-medium">214 Linden Ave thread</p>
      </div>
      <div className="flex flex-1 flex-col gap-1.5">
        {messages.map((message) => (
          <div
            key={message.text}
            className={cn(
              'max-w-[92%] rounded-md px-2.5 py-1.5 text-[11px] leading-snug',
              message.from === 'Agent'
                ? 'bg-orange-400/15 ml-auto text-right'
                : 'border-border/50 bg-muted/20 border',
            )}
          >
            <p className="text-muted-foreground mb-0.5 text-[9px] uppercase">
              {message.from} · {message.time}
            </p>
            <p>{message.text}</p>
          </div>
        ))}
      </div>
    </div>
  )
}

/** Agent decision prompts for User Feedback — prepares user to respond to owner inquiries. */
export function UserFeedbackResultsPanel({ className }: SecondaryPanelProps) {
  const decisionPrompts = [
    {
      question: 'If the owner counters $8k higher, are you willing to stretch?',
      context: 'Price negotiation',
    },
    {
      question: 'Can you close within 30 days if inspection clears?',
      context: 'Timeline check',
    },
    {
      question: 'Would you accept shared laundry to secure the location?',
      context: 'Trade-off priority',
    },
  ]

  return (
    <div className={cn('flex h-full flex-col gap-2.5', className)}>
      <div className="border-fuchsia-400/30 bg-fuchsia-400/10 flex items-center gap-2 rounded-md border px-2.5 py-2">
        <MessageSquare className="text-fuchsia-400 size-3.5 shrink-0" />
        <div>
          <p className="text-xs font-medium">Agent needs your input</p>
          <p className="text-muted-foreground text-[10px]">
            Quick answers help us respond to owners faster
          </p>
        </div>
      </div>
      <div className="flex flex-col gap-1.5">
        {decisionPrompts.map((item) => (
          <div
            key={item.question}
            className="border-fuchsia-400/20 bg-fuchsia-400/5 rounded-md border px-2.5 py-2"
          >
            <p className="text-fuchsia-400 text-[9px] uppercase tracking-wide">
              Agent · {item.context}
            </p>
            <p className="mt-0.5 text-[11px] leading-snug">{item.question}</p>
          </div>
        ))}
      </div>
      <p className="text-muted-foreground mt-auto text-[10px] italic leading-relaxed">
        Your answers stay in one thread — we handle owner follow-ups from here.
      </p>
    </div>
  )
}
