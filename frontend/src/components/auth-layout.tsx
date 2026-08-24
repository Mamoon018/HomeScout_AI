import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'
import { BackgroundPixelStars } from '@/components/background-pixel-stars'
import { SignupFeatureGrid } from '@/components/signup-feature-grid'
import { WaxingMoonLogo } from '@/components/waxing-moon-logo'

type AuthLayoutProps = {
  formContent: ReactNode
  leftContent?: ReactNode
  centerForm?: boolean
}

function DefaultLeftContent() {
  return (
    <>
      <WaxingMoonLogo className="-translate-y-[1.2rem] lg:-translate-y-8" />
      <div className="mt-6 flex w-full max-w-6xl flex-col gap-16 overflow-visible">
        <div className="flex flex-col gap-3">
          <h1 className="animate-hero-heading text-left text-4xl font-medium leading-[1.1] tracking-[-0.03em] text-foreground md:text-5xl lg:text-6xl">
            Let us run the whole home hunt for you!
          </h1>
          <p className="text-sm text-muted-foreground">
            Share your needs, constraints, wishlist and open questions.
          </p>
        </div>
        <SignupFeatureGrid />
      </div>
    </>
  )
}

/** Shared auth shell with hero column and form slot for login/signup pages. */
export function AuthLayout({
  formContent,
  leftContent,
  centerForm = false,
}: AuthLayoutProps) {
  return (
    <div className="relative isolate min-h-svh text-foreground">
      <BackgroundPixelStars />
      <div
        className={cn(
          'relative z-10 grid min-h-svh lg:grid-cols-2',
          centerForm ? 'lg:items-stretch' : 'lg:items-start',
        )}
      >
        <div className="flex flex-col px-6 py-12 md:px-12 lg:px-16 lg:pt-20">
          {leftContent ?? <DefaultLeftContent />}
        </div>
        <div
          className={cn(
            'flex justify-center px-6 py-12 md:px-10 lg:px-16',
            centerForm ? 'items-center lg:min-h-svh' : 'items-start lg:pt-20',
          )}
        >
          <div className="w-full max-w-md">{formContent}</div>
        </div>
      </div>
    </div>
  )
}
