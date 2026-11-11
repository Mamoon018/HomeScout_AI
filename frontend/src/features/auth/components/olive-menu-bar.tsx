import { cn } from '@/lib/utils'

/** Placeholder targets until these pages exist. */
const MENU_ITEMS = [
  { label: 'Home', href: '#home' },
  { label: 'Product', href: '#product' },
  { label: 'Price', href: '#price' },
  { label: 'Reviews', href: '#reviews' },
  { label: 'About us', href: '#about-us' },
]

/** Olive Glass menu bar: a frosted pill of wheat links that lift slightly on hover. */
export function OliveMenuBar({ className }: { className?: string }) {
  return (
    <nav aria-label="Main" className={cn('max-w-full', className)}>
      <ul
        data-slot="olive-menu"
        className="m-0 flex list-none items-center gap-0.5 rounded-full border border-white/16 bg-white/7 p-1.5 shadow-[inset_0_1px_0_rgba(255,255,255,0.12),0_10px_30px_rgba(10,14,6,0.3)] backdrop-blur-xl sm:gap-1"
      >
        {MENU_ITEMS.map((item) => (
          <li key={item.label}>
            <a
              href={item.href}
              className={cn(
                'block rounded-full px-2.5 py-1.5 text-[13px] font-medium whitespace-nowrap text-[#e6d3a3] no-underline sm:px-4 sm:py-2 sm:text-sm xl:px-3.5',
                'transition-[scale,background-color] duration-200 ease-[cubic-bezier(0.16,1,0.3,1)]',
                'hover:scale-[1.06] hover:bg-white/8',
                'focus-visible:bg-white/8 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#e6d3a3]',
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
