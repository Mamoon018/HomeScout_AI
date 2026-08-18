# Linear Design System (linear_design_system.md)

This document defines the "Engineered Dark Mode" aesthetic—a design language built for speed, precision, and depth. It follows a strictly hierarchical structure where each layer builds upon the prerequisites established in the layer below.

---

## 1. Design Tokens (The Atomic Layer)
The smallest, immutable units of the system. These raw values represent the system's "DNA."

### Colors (Neutrals & Core)
*   **Neutral-000:** `#000000`
*   **Neutral-900:** `#08090A` (Deep Background)
*   **Neutral-800:** `#121314` (Surface Base)
*   **Neutral-700:** `#1B1C1D` (Surface Elevate)
*   **Neutral-100:** `#F7F8F8` (Primary Text)
*   **Neutral-400:** `#8A8F98` (Secondary Text)
*   **Brand-500:** `#5E6AD2` (Linear Purple)

### Spacing (4px Grid)
*   **Space-1:** `4px`
*   **Space-2:** `8px`
*   **Space-4:** `16px`
*   **Space-6:** `24px`
*   **Space-12:** `48px`

### Typography (Inter & Mono)
*   **Family-Sans:** `Inter, -apple-system, system-ui, sans-serif`
*   **Family-Mono:** `"SF Mono", "Roboto Mono", monospace`
*   **Size-XS:** `12px`
*   **Size-SM:** `14px`
*   **Size-MD:** `16px`
*   **Size-LG:** `20px`
*   **Size-XL:** `32px`
*   **Weight-Regular:** `400`
*   **Weight-Medium:** `500`
*   **Weight-Bold:** `600`

### Radius & Shadows
*   **Radius-SM:** `4px` (Standard for components)
*   **Radius-MD:** `8px` (Cards and containers)
*   **Shadow-Subtle:** `0 1px 2px rgba(0,0,0,0.5)`
*   **Shadow-Elevated:** `0 8px 16px rgba(0,0,0,0.6)`

### Motion
*   **Duration-Fast:** `150ms`
*   **Duration-Standard:** `250ms`
*   **Easing-Out:** `cubic-bezier(0, 0, 0.2, 1)`

---


## Platforms & Devices

###  Browser support
* Chrome: Latest 2 versions 
* Safari: Latest 2 versions 
* Firefox: Latest 2 versions 
* Edge: Latest 2 versions

### Responsive behavior
- Breakpoint scale (mobile-first, Tailwind defaults):
  - Base: 0px+ (mobile)
  - sm: 640px+
  - md: 768px+ (tablet)
  - lg: 1024px+ (desktop)
  - xl: 1280px+
  - 2xl: 1536px+
- Rule: unprefixed classes define the mobile/base state. Breakpoint prefixes add or override for larger screens only.
- Documentation template per component:


### Platform-Specific Considerations

#### Fonts
- Primary: Inter
- Fallback stack (in order): Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif
- Tailwind config value:
  fontFamily: {
    sans: ['Inter', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'Helvetica Neue', 'Arial', 'sans-serif']
  }
- Rule: font-display: swap, so fallback text renders immediately and swaps to Inter once loaded, instead of staying invisible.

#### Touch
- Minimum touch target size: 44px × 44px (width × height), matches Apple Human Interface Guidelines and is at or above WCAG 2.5.5 minimum (44×44 CSS px).
- Minimum spacing between adjacent touch targets: 8px, to reduce mis-taps between neighboring controls.
- Applies to: buttons, links, form inputs, icon-only controls, checkboxes, radio buttons.
- Implementation rule: if the visible element (icon, text) is smaller than 44×44px, extend the tappable/clickable area via padding or a min-width/min-height utility, not by resizing the visible element itself.
- Tailwind reference values: min-h-11 min-w-11 (44px, since Tailwind's default spacing scale places 11 at 2.75rem = 44px).

#### Hover
- Rule: no interaction or information may be exclusively triggered or revealed by :hover.
- Required pattern: every hover-triggered state must have an equivalent trigger on tap/click (:focus, :active, or onClick) and, where feasible, must not be hidden by default (visible without interaction).
- Applies to: tooltips, dropdown menus, submenus, hover-revealed icons or actions, hover-only visual affordances (e.g. an edit icon that only appears on hover).
- CSS approach: pair `:hover` styles with `:focus-visible` or a toggled state class so keyboard and touch users reach the same state as mouse users.
- Verification check: for each hover-based interaction, confirm it also works via tap on a touch device and via keyboard focus, before marking it complete.


## 2. Foundational Styles (Semantic Layer)
Mapping tokens to intent and meaning.

### Color Meaning
*   **App-Background:** `Neutral-900`
*   **Surface-Primary:** `Neutral-800`
*   **Surface-Secondary:** `Neutral-700`
*   **Text-Heading:** `Neutral-100` (Tracking: -0.02em)
*   **Text-Body:** `Neutral-400`
*   **Action-Primary:** `Brand-500`
*   **Border-Subtle:** `rgba(255, 255, 255, 0.08)`

### Layout Principles
*   **Section-Gap:** `Space-12` (Vertical spacing between major sections)
*   **Content-Gutter:** `Space-6` (Standard horizontal padding)
*   **Interactive-Height:** `32px` (Standard height for buttons/inputs)

---

## 3. Component Styles (Visual Layer)
UI elements built using semantic foundations.

### Buttons
*   **Primary:** Background: `Action-Primary`, Text: `Neutral-100`, Radius: `Radius-SM`.
*   **Secondary:** Background: `Surface-Secondary`, Border: `Border-Subtle`, Text: `Neutral-100`.
*   **Ghost:** Transparent background, visible on hover with `Surface-Secondary`.

### Cards & Containers
*   **Feature-Card:** Surface: `Surface-Primary`, Border: `Border-Subtle`, Shadow: `Shadow-Subtle`.
*   **Texture:** Overlaid with `Subtle Noise (IMAGE_2)` at 3-5% opacity to add "tactile" depth.

### Inputs
*   **Text-Field:** Background: `Neutral-900` (inset), Border: `Border-Subtle`, Text: `Neutral-100`. Focus state adds a subtle glow of `Brand-500`.

---

## 4. Composition Patterns (Structural Layer)
How components combine into functional groups.

### Navigation Hierarchy
*   **Global-Sidebar:** Fixed width (240px), Surface-Elevate, using `Size-SM` typography for item labels.
*   **Breadcrumbs:** `Mono` family, `Size-XS`, separated by `/` with `Neutral-400` color.

### Issue/Task List
*   **Row-Structure:** Height `40px`, alternating hover states, icons aligned to `Space-4` grid.
*   **Status-Badges:** Pill-shaped, `Radius-MD`, low-saturation background tints with high-contrast text.

---


## 5. Documentation & Usage Rules (The Governance Layer)
Guidelines for maintaining the "Linear" feel.

### The "Golden Rules"
1.  **Dark Mode First:** The system is optimized for dark environments. Pure black should only be used for the deepest background layers; use charcoal for interactive surfaces.
2.  **Noise is Essential:** Never use flat backgrounds for large areas. Always apply the noise texture (`IMAGE_2`) to prevent "digital sterility."
3.  **Tight Tracking:** Hero headings should use negative letter-spacing (`-0.02em` to `-0.04em`) to look "engineered."
4.  **Avoid Rounded-Full:** Use `Radius-SM` (4px) for almost everything. Roundness should feel intentional and rigid, not bubbly.
5.  **Motion is Performance:** Animations should be fast and linear-to-out. If an animation feels "sluggish," it is too long.

---

### Implementation Context
*   **Reference Image:** `{{DATA:IMAGE:IMAGE_2}}` (Noise Texture)
*   **Source URL:** `https://linear.app/`
