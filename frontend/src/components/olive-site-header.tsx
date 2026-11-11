import { OliveMenuBar } from '@/components/olive-menu-bar'
import { WaxingMoonLogo } from '@/components/waxing-moon-logo'

/**
 * The Frosted Sage top bar: moon logo, HOMESCOUT AI wordmark and the menu pill. Shared by the
 * sign-in / sign-up pages and the Home page so the three never drift apart. On wide screens
 * the menu sits in the same 400px column as the page's card.
 */
export function OliveSiteHeader() {
  return (
    <header className="mx-auto flex w-full max-w-[1380px] flex-wrap items-center justify-between gap-x-6 gap-y-4 xl:grid xl:grid-cols-[minmax(0,940px)_400px]">
      <div className="flex items-center gap-4">
        <WaxingMoonLogo />
        <span
          data-slot="brand-wordmark"
          className="mr-[-0.32em] text-[15px] font-medium tracking-[0.32em] whitespace-nowrap text-(--fs-ink) uppercase"
        >
          Homescout AI
        </span>
      </div>
      <OliveMenuBar className="xl:justify-self-center" />
    </header>
  )
}
