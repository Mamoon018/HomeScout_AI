import React, { useEffect, useId, useMemo, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

export type FeatureType = {
  title: string
  icon: React.ComponentType<React.SVGProps<SVGSVGElement>>
  description: string
  iconClassName?: string
  borderClassName?: string
  neonBorderClassName?: string
  secondaryContent?: React.ReactNode
}

type FeatureCardProps = React.ComponentProps<'div'> & {
  feature: FeatureType
  index?: number
}

/** Renders a single feature tile with optional secondary results overlay. */
export function FeatureCard({
  feature,
  className,
  index = 0,
  style,
  ...props
}: FeatureCardProps) {
  const pattern = useMemo(() => genRandomPattern(), [])
  const [isSecondaryOpen, setIsSecondaryOpen] = useState(false)
  const secondaryCardRef = useRef<HTMLDivElement>(null)
  const seeResultsButtonRef = useRef<HTMLSpanElement>(null)
  const secondaryPanelId = useId()

  // Close secondary card on outside click or Escape.
  useEffect(() => {
    if (!isSecondaryOpen) return

    const handlePointerDown = (event: PointerEvent) => {
      const target = event.target as Node
      if (secondaryCardRef.current?.contains(target)) return
      if (seeResultsButtonRef.current?.contains(target)) return
      setIsSecondaryOpen(false)
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setIsSecondaryOpen(false)
    }

    document.addEventListener('pointerdown', handlePointerDown)
    document.addEventListener('keydown', handleKeyDown)

    return () => {
      document.removeEventListener('pointerdown', handlePointerDown)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [isSecondaryOpen])

  const toggleSecondaryCard = () => {
    setIsSecondaryOpen((open) => !open)
  }

  return (
    <div className="relative overflow-visible">
      <div
        className={cn(
          'feature-card animate-feature-card-enter relative flex h-[9.5rem] overflow-hidden rounded-xl border-border/60 bg-card p-8',
          className,
        )}
        style={
          {
            '--feature-card-index': index,
            ...style,
          } as React.CSSProperties
        }
        {...props}
      >
        <div className="pointer-events-none absolute top-0 left-1/2 -mt-2 -ml-20 h-full w-full [mask-image:linear-gradient(white,transparent)]">
          <div className="from-foreground/5 to-foreground/1 absolute inset-0 bg-gradient-to-r [mask-image:radial-gradient(farthest-side_at_top,white,transparent)] opacity-100">
            <GridPattern
              width={20}
              height={20}
              x="-12"
              y="4"
              squares={pattern}
              className="fill-foreground/5 stroke-foreground/25 absolute inset-0 h-full w-full mix-blend-overlay"
            />
          </div>
        </div>
        <div className="relative z-20 flex flex-col gap-3">
          <div className="flex items-start gap-4">
            <feature.icon
              className={cn('size-6 shrink-0', feature.iconClassName ?? 'text-foreground/75')}
              strokeWidth={1}
              aria-hidden
            />
            <div className="flex min-w-0 flex-1 items-start justify-between gap-3">
              <h3 className="text-lg leading-snug">{feature.title}</h3>
              {feature.secondaryContent ? (
                <span ref={seeResultsButtonRef} className="shrink-0">
                  <Button
                    type="button"
                    variant="outline"
                    size="xs"
                    className="text-xs font-medium text-foreground"
                    aria-expanded={isSecondaryOpen}
                    aria-controls={secondaryPanelId}
                    onClick={toggleSecondaryCard}
                  >
                    see results
                  </Button>
                </span>
              ) : null}
            </div>
          </div>
          <div
            className={cn(
              'w-full rounded-md border px-4 py-3',
              feature.borderClassName ?? 'border-border/40',
            )}
          >
            <p className="text-muted-foreground text-sm font-light leading-snug">
              {feature.description}
            </p>
          </div>
        </div>
      </div>

      {feature.secondaryContent && isSecondaryOpen ? (
        <div
          ref={secondaryCardRef}
          id={secondaryPanelId}
          role="dialog"
          aria-label={`${feature.title} results`}
          className={cn(
            'animate-feature-card-enter absolute top-0 left-0 z-30 w-full overflow-visible rounded-xl',
            'h-full min-h-[9.5rem] md:h-[150%] md:min-h-[14.25rem] md:w-[60%]',
            '[animation-delay:0ms]',
            'md:left-1/2',
          )}
        >
          <div
            className={cn(
              'secondary-neon-border pointer-events-none absolute inset-0 rounded-xl',
              feature.neonBorderClassName,
            )}
            aria-hidden
          />
          <div
            className={cn(
              'feature-card absolute inset-[2px] z-10 flex flex-col overflow-hidden rounded-[10px] bg-card p-8',
              '[box-shadow:var(--shadow-Shadow-Elevated)]',
            )}
          >
            <div className="pointer-events-none absolute top-0 left-1/2 -mt-2 -ml-20 h-full w-full [mask-image:linear-gradient(white,transparent)]">
              <div className="from-foreground/5 to-foreground/1 absolute inset-0 bg-gradient-to-r [mask-image:radial-gradient(farthest-side_at_top,white,transparent)] opacity-100">
                <GridPattern
                  width={20}
                  height={20}
                  x="-12"
                  y="4"
                  squares={pattern}
                  className="fill-foreground/5 stroke-foreground/25 absolute inset-0 h-full w-full mix-blend-overlay"
                />
              </div>
            </div>
            <div className="secondary-card-scroll relative z-20 min-h-0 flex-1 overflow-y-auto overscroll-contain pr-1">
              {feature.secondaryContent}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}

type GridFeatureCardsProps = React.ComponentProps<'div'> & {
  features: FeatureType[]
}

/** Lays out feature cards in a responsive grid for marketing or highlight sections. */
export function GridFeatureCards({
  features,
  className,
  ...props
}: GridFeatureCardsProps) {
  return (
    <div
      className={cn('grid grid-cols-1 gap-8 overflow-visible md:grid-cols-2', className)}
      {...props}
    >
      {features.map((feature, index) => (
        <div key={feature.title} className="overflow-visible">
          <FeatureCard feature={feature} index={index} />
        </div>
      ))}
    </div>
  )
}

function GridPattern({
  width,
  height,
  x,
  y,
  squares,
  ...props
}: React.ComponentProps<'svg'> & {
  width: number
  height: number
  x: string
  y: string
  squares?: number[][]
}) {
  const patternId = React.useId()

  return (
    <svg aria-hidden="true" {...props}>
      <defs>
        <pattern
          id={patternId}
          width={width}
          height={height}
          patternUnits="userSpaceOnUse"
          x={x}
          y={y}
        >
          <path d={`M.5 ${height}V.5H${width}`} fill="none" />
        </pattern>
      </defs>
      <rect width="100%" height="100%" strokeWidth={0} fill={`url(#${patternId})`} />
      {squares && (
        <svg x={x} y={y} className="overflow-visible">
          {squares.map(([squareX, squareY], squareIndex) => (
            <rect
              strokeWidth="0"
              key={squareIndex}
              width={width + 1}
              height={height + 1}
              x={squareX * width}
              y={squareY * height}
            />
          ))}
        </svg>
      )}
    </svg>
  )
}

function genRandomPattern(length?: number): number[][] {
  length = length ?? 5
  return Array.from({ length }, () => [
    Math.floor(Math.random() * 4) + 7,
    Math.floor(Math.random() * 6) + 1,
  ])
}
