import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'
import { BackgroundPixelStars } from '@/components/background-pixel-stars'
import { SignupFeatureGrid } from '@/features/auth/components/signup-feature-grid'
import { AgentWorkflow } from '@/features/auth/components/agent-workflow/agent-workflow'
import { OliveHero } from '@/features/auth/components/olive-hero'
import { OliveMenuBar } from '@/features/auth/components/olive-menu-bar'
import { WaxingMoonLogo } from '@/components/waxing-moon-logo'
import { useDocumentClasses } from '@/lib/useDocumentClasses'

export type AuthTheme = 'dark' | 'olive'

type AuthLayoutProps = {
  formContent: ReactNode
  leftContent?: ReactNode
  centerForm?: boolean
  /** "olive" applies the Olive Glass theme (theme-olive.css + theme-olive-auth.css). */
  theme?: AuthTheme
}

const THEME_CLASSES: Record<AuthTheme, readonly string[]> = {
  dark: [],
  olive: ['theme-olive', 'auth-olive'],
}

const DEFAULT_HERO = {
  heading: 'Let us run the whole home hunt for you!',
  subtitle: 'Share your needs, constraints, wishlist and open questions.',
}

function AuthHero({ heading, subtitle }: { heading: string; subtitle: string }) {
  return (
    <div className="flex flex-col gap-3">
      <h1
        data-slot="auth-hero-heading"
        className="animate-hero-heading text-balance text-left text-4xl font-medium leading-[1.1] tracking-[-0.03em] text-foreground md:text-5xl lg:text-6xl"
      >
        {heading}
      </h1>
      <p data-slot="auth-hero-subtitle" className="text-sm text-muted-foreground">
        {subtitle}
      </p>
    </div>
  )
}

function DefaultLeftContent() {
  return (
    <>
      <WaxingMoonLogo className="-translate-y-[1.2rem] lg:-translate-y-8" />
      <div className="mt-6 flex w-full max-w-6xl flex-col gap-16 overflow-visible">
        <AuthHero {...DEFAULT_HERO} />
        <SignupFeatureGrid />
      </div>
    </>
  )
}

/**
 * Olive sign-in: menu bar on top; hero above the agent workflow on the left, with the
 * sign-in card beside the workflow, centred on it. Narrower screens stack
 * hero → sign-in → workflow, so signing in never sits below the demo.
 */
function OliveAuthBody({ formContent }: { formContent: ReactNode }) {
  return (
    <div className="relative z-10 mx-auto flex min-h-svh w-full max-w-[1440px] flex-col gap-10 px-6 py-10 md:px-10 xl:px-[30px]">
      {/* Same columns as the content grid, so the menu sits directly above the sign-in card. */}
      <header className="mx-auto flex w-full max-w-[1380px] flex-wrap items-center justify-between gap-x-6 gap-y-4 xl:grid xl:grid-cols-[minmax(0,940px)_400px]">
        <div className="flex items-center gap-4">
          <WaxingMoonLogo />
          <span
            data-slot="brand-wordmark"
            className="mr-[-0.32em] text-[15px] font-medium tracking-[0.32em] whitespace-nowrap text-[#e6d3a3] uppercase"
          >
            Homescout AI
          </span>
        </div>
        <OliveMenuBar className="xl:justify-self-center" />
      </header>
      <div className="mx-auto grid w-full max-w-[1380px] flex-1 content-center gap-x-10 gap-y-12 [grid-template-areas:'hero'_'form'_'flow'] xl:grid-cols-[minmax(0,940px)_400px] xl:justify-between xl:[grid-template-areas:'hero_.'_'flow_form']">
        <div className="min-w-0 [grid-area:hero]">
          <OliveHero />
        </div>
        <div className="w-full max-w-[400px] [grid-area:form] xl:self-center">{formContent}</div>
        <div className="min-w-0 [grid-area:flow]">
          <AgentWorkflow />
        </div>
      </div>
    </div>
  )
}

/** Shared auth shell with hero column and form slot for login/signup pages. */
export function AuthLayout({
  formContent,
  leftContent,
  centerForm = false,
  theme = 'dark',
}: AuthLayoutProps) {
  useDocumentClasses(THEME_CLASSES[theme])

  return (
    <div className="relative isolate min-h-svh text-foreground">
      <BackgroundPixelStars tone={theme === 'olive' ? 'olive' : 'default'} />
      {theme === 'olive' && !leftContent ? (
        <OliveAuthBody formContent={formContent} />
      ) : (
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
      )}
    </div>
  )
}
