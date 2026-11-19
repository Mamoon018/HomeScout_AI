import { cn } from '@/lib/utils'

/** Placeholder targets until these pages exist. */
const MENU_ITEMS = [
  { label: 'Home', href: '#home' },
  { label: 'Product', href: '#product' },
  { label: 'Price', href: '#price' },
  { label: 'Reviews', href: '#reviews' },
  { label: 'About us', href: '#about-us' },
]

/** Frosted Sage menu bar: a frosted pill of ink links that lift slightly on hover. */
export function OliveMenuBar({ className }: { className?: string }) {
  return (
    <nav aria-label="Main" className={cn('max-w-full', className)}>
      <ul
        data-slot="olive-menu"
        className="m-0 flex list-none items-center gap-0.5 rounded-full border border-(--fs-panel-border) bg-(--fs-panel) p-1.5 shadow-(--fs-panel-shadow) backdrop-blur-xl sm:gap-1"
      >
        {MENU_ITEMS.map((item) => (
          <li key={item.label}>
            <a
              href={item.href}
              className={cn(
                'block rounded-full px-2.5 py-1.5 text-[13px] font-medium whitespace-nowrap text-(--fs-ink) no-underline sm:px-4 sm:py-2 sm:text-sm xl:px-3.5',
                'transition-[scale,background-color] duration-200 ease-[cubic-bezier(0.16,1,0.3,1)]',
                'hover:scale-[1.06] hover:bg-(--fs-option-selected)',
                'focus-visible:bg-(--fs-option-selected) focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-(--fs-accent)',
                'motion-reduce:transition-none motion-reduce:hover:scale-100',
              )}
            >
              {item.label}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  )
}
