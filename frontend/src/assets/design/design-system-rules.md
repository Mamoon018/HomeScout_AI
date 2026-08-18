# Linear Design System — Implementation Rules

Companion to `linear_design_system.md` and `tailwind.config.ts`. Covers governance and platform rules that cannot be expressed as Tailwind theme values.

## Golden Rules (Governance)

1. **Dark mode first** — Optimized for dark environments. Pure black (`Neutral-000`) is only for the deepest background layers; use charcoal surfaces (`Neutral-800` / `Neutral-700`) for interactive UI.
2. **Noise is essential** — Never use flat backgrounds on large areas. Apply the noise texture (`IMAGE_2`, via `.texture-noise` + `--texture-noise-image`) at 3–5% opacity (`--texture-noise-opacity`, default 0.04).
3. **Tight tracking** — Hero and section headings use negative letter-spacing (`tracking-Text-Heading` / `-0.02em` to `-0.04em`).
4. **Avoid `rounded-full`** — Default to `rounded-Radius-SM` (4px). Roundness should feel intentional and rigid. Exception: `.status-badge` uses `Radius-MD` per the issue-list spec (pill-shaped at 8px, not full round).
5. **Motion is performance** — Use `duration-Duration-Fast` (150ms) or `duration-Duration-Standard` (250ms) with `ease-Easing-Out`. If an animation feels sluggish, shorten it.

## Responsive (mobile-first)

Breakpoints use Tailwind defaults — unprefixed classes define mobile/base; prefixes override for larger screens only:

| Prefix | Min width |
|--------|-----------|
| (base) | 0px+ |
| `sm`   | 640px+ |
| `md`   | 768px+ |
| `lg`   | 1024px+ |
| `xl`   | 1280px+ |
| `2xl`  | 1536px+ |

## Fonts

- **Primary:** Inter (loaded in `index.html` with `display=swap` on the Google Fonts URL).
- **Sans stack:** `font-sans` → Inter, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica Neue, Arial, sans-serif.
- **Mono stack:** `font-mono` → SF Mono, Roboto Mono, monospace.
- **Rule:** Fallback text renders immediately and swaps to Inter once loaded (no invisible text during load).

## Touch

- **Minimum touch target:** 44×44 CSS px (`min-h-11 min-w-11` or `.touch-target`).
- **Minimum spacing between adjacent targets:** 8px (`gap-Space-2` / `gap-2`).
- **Applies to:** buttons, links, form inputs, icon-only controls, checkboxes, radio buttons.
- **Implementation:** If the visible element is smaller than 44×44px, extend the tappable area via padding or `min-h-11 min-w-11` — do not shrink visible content to fit.
- **Note:** `Interactive-Height` (32px) is the visible control height; pair with padding or pseudo-element expansion for touch compliance.

## Hover

- **Rule:** No interaction or information may be exclusively triggered or revealed by `:hover`.
- **Required pattern:** Every hover state must have an equivalent `:focus-visible`, `:active`, or toggled-state trigger. Prefer states that are visible without interaction when feasible.
- **Applies to:** tooltips, dropdowns, submenus, hover-revealed icons/actions, hover-only affordances.
- **CSS approach:** Pair `:hover` with `:focus-visible` or a state class (see `.btn-ghost`, `.list-row` in `tailwind.config.ts`).
- **Verification:** Confirm each hover interaction works via tap (touch) and keyboard focus before marking complete.

## Component class reference

| Class | Layer | Use |
|-------|-------|-----|
| `.btn-primary` | Component | Primary action button |
| `.btn-secondary` | Component | Secondary action button |
| `.btn-ghost` | Component | Ghost / tertiary button |
| `.feature-card` | Component | Card surface (+ `.texture-noise` on large areas) |
| `.text-field` | Component | Text input field |
| `.global-sidebar` | Composition | 240px navigation sidebar |
| `.breadcrumbs` | Composition | Mono XS breadcrumb trail |
| `.list-row` | Composition | 40px issue/task list row |
| `.status-badge` | Composition | Status pill badge |
| `.texture-noise` | Component | Noise overlay for large surfaces |
| `.touch-target` | Platform | 44×44 minimum hit area |

## Reference

- **Noise texture:** `IMAGE_2` (not yet in repo — set `--texture-noise-image` when asset is added)
- **Source aesthetic:** https://linear.app/
