# R2 results page: UI spec (shape brief)

Status: draft for confirmation. No code. Builds on `R2_frontend_ui_definition.md` (what R2 produces and what to show) and the decisions below (what to take from wireframes A, C and D).

## 0. Theme correction

The earlier wireframe canvas was drawn on the dark "Olive Grove at Dusk" theme described in `DESIGN.md`. That is not what ships. Home, sign-in and sign-up render the **Frosted Sage** theme (`theme-olive.css`, commit 6297f73): a light page with white glass panels and dark olive ink. R1's results (`features/r1-interpretation`) are built on it. R2 must match R1, so this spec replaces the dark look. `DESIGN.md` is stale on this point and should be regenerated with `/impeccable document` after R2 ships (not as part of this work).

## 1. Job and audience

- **Surface:** one page per apartment, entered after R2 finishes. Mode: **Operate** (the renter is evaluating, comparing, deciding).
- **Who and state of mind:** a renter who already described their priorities on Home. They now ask one question: *"Are the places I care about reachable the way I would actually get there?"* They may walk, cycle, drive or take transit, and we often do not know which. The page must let them judge each mode, not pick one for them.
- **Primary understanding:** (1) how close is everything on foot, at a glance; (2) for any category, how reachable is each place by each mode; (3) what was not found.
- **Success:** the renter can say "the gym is 6 minutes' walk, the supermarket is only easy by bike" without opening anything else.
- **Truth specific to HomeScout:** travel is a real route time per mode, not straight-line distance (PRODUCT.md, "Real-world truth over proxies"). Say "nearest", never "best": relevance filtering is not built.

## 2. Selected direction

Hybrid of three approved parts, one page, no map.

| Part | From | What it is |
|---|---|---|
| Summary panel with walk strip | A | One glass panel opening the page: the answer in numbers plus a strip of walking-time bands |
| Reach ring | D | Picture of all places at once, **walk time only**, inside the summary panel |
| Category rail + category workspace | C | Rail for navigation (nearest time and count); workspace with category header, notes and two-column place cards |

**Structural thesis:** the summary is the *overview of the whole neighborhood*; the rail and workspace are the *drill-down into one category*. Both read the same finished `result`, so they never disagree.

**Sequence:** heading, then Summary panel (metrics left, ring right), then rail and workspace side by side.

**Focal moment:** the ring. Rings draw outward, then place markers pop in. Everything else is quiet.

## 3. Layout

Container: 1120px max, as R1's stage (`max-w-[1120px]`, page padding 24px, 40px from `md`, 30px from `xl`). Gaps follow the 4px base: 24px between the heading, the panel and the workspace.

1. **Heading row:** `h2` in the R1 pattern: Manrope 24px/600, ink, with **one** Fraunces italic teal keyword (`#1F7A80`): "What's *around* {address}". A status mark on the right (DoneMark pattern). Under it, one muted line: the radius and travel modes ("Within 2 km · walk, cycle, drive, transit").
2. **Summary panel** (28px radius glass, `--fs-panel`, `backdrop-blur-[24px]`, 24 to 28px padding). Two columns, nothing spanning the full width, so no row is left half empty. Every metric avoids a walk-only bias: a neighbourhood that is good by transit or car must not look bad because it is far on foot.
   - **Left column (flexible, from 520px), top to bottom:**
     - **Time limit:** "Within 5 / 10 / 15 / 20 min" (pill buttons, default 10). It drives the whole panel: mode fit, the strip's dimming, Options within reach and the ring's disc.
     - **Mode fit** (the make-or-break metric), headed "Categories you can reach within {N} min". Four buttons in a row, Walk, Cycle, Drive, Transit, each with icon and label, a 32px count "4 of 6" (all categories, including those with nothing found), and one 10px **bead per category** in its category colour: filled when the category's nearest place is within the limit by that mode, hollow when it isn't, dashed grey when nothing was found. A bead's hover text names the category and its nearest time. A count compares modes; the beads show which category drops out.
     - **Lens:** the selected mode-fit button (olive fill, on-accent text, default Walk) is the lens. The strip and Options within reach re-read by that mode. The caption beside the heading says "Pick a way of getting around to see the panel by it". The ring does not follow the lens; it stays walking.
     - **Strip,** headed "How far every place is {on foot | by bike | by car | by transit}", with "{n} places have no route {by mode}" on the right when that applies. One 10px bar divided into five bands. Each segment's width is its share of places; a count and a range label sit under each band, every label carrying its unit: "up to 5 mins", "5 to 10 mins", "10 to 15 mins", "15 to 20 mins", "over 20 mins"; empty bands stay as faint slots so the axis never changes. Bands beyond the limit dim.
     - **Place balls:** above each band, every place in it is a 12px ball, **piled like ..^..**: the widest row sits on the bar and holds the nearest places, and each row above is one ball narrower and centred, so balls rest in the gaps below (rows overlap by 1px). The bottom row is as wide as it needs to be (n balls: the smallest w with w(w+1)/2 >= n, so 4 balls pile 3/1, 9 pile 4/3/2, 18 pile 6/5/4/3), so a full band widens rather than towering. Coloured by category (same colour as on the ring). Hover shows a small solid tooltip in a fixed order: **category** (bold, in its colour), then time, then place, e.g. "Café · 6 min walk · Röstwerk" (time and place are one text run, so the place's name exists once as its own text on the page). Click selects the category. Balls beyond the limit dim. **Selected category:** its balls keep their size (growing would push into neighbours in the pile); they take a dark ink border and a soft halo, and send out **two rings** in the category colour, half a beat apart (1.4 s each, growing to about 2.6× and fading). The rings are pseudo-elements, so they never move a neighbour, and they must be noticeable at a glance, not on close inspection. Under reduced motion only the ink border and halo remain. Supplementary picture (`aria-hidden`).
     - **Options within reach and Not found**, side by side under the strip (wrapping on narrow widths):
       - **Options within reach** (inset tile, about two thirds). Headed "Options within reach", subtitle "No. of options within selected time range". One row per category with places, **thinnest first**: colour dot and name, a **ten-pip ladder** (the pip shape of R1's depth ladder) filled in the category colour for each option in reach, and a count ("3 options", "10+ options" when capped, "1 option only", "None in reach"). One option or none shows the count in rose. A row selects its category below. Counts are lower bounds when a category is capped.
       - **Not found** (inset tile, about one third). When categories are empty: a rose-tinted tile, "Nothing found within 2 km", each missing category as a chip, and "If one of these is a must-have, this area may not suit you. Nothing beyond 2 km was checked." When none are empty: a quiet tile with a green check, "Every category has a place within 2 km".
   - **Right column (340px), top to bottom:** "{n} places found within 2 km", right-aligned, the number at 22px (the total sits here, not in a tile: the cap inflates it and it says nothing about fit); the ring's **legend**; the ring's **caption**; then the **Reach ring**. Names and caption come first so the renter knows the colours before reading the balls. See 4.
   - Rejected metrics, so they are not reintroduced: "Walk to reach everything" (walk-biased); a single "nearest on foot" figure; a summary sentence.
3. **Rail and workspace** (grid: 280px rail, 1fr workspace, 20px gap, rail sticky under the page top).
   - **Rail:** a glass panel listing categories in R1's order. Each row: family-tinted icon tile (36px), category name, below it the muted line "{n} places", and on the right the **nearest walk time** in tabular type. Selected row: `--fs-option-selected` fill and a 1px accent border (no side stripe). Categories with nothing found stay in the list, muted, with "None found".
   - **Workspace:** one category at a time.
     - **Category header** (inside one glass panel, not a card inside a card): icon tile, category name (16px/600), a note line, and on the right the place count with a **"Why is this category included?"** link under it (a small pill with a scroll icon and an outward arrow), shown for **every** category, asked-for or added. It opens Home (`/home`), which shows the plan this search was run from. Then a **mode strip** of four cells for the *category's nearest place by each mode* (Walk, Cycle, Drive, Transit). That strip is the fast way to compare modes for a whole category.
     - **Notes** under the header, plain muted text, only those that apply: "Showing the nearest 10" when capped; "Some times are estimates" when `used_fallback`; "Not in your brief; added because it usually matters" for inferred categories (the gap note). The link back to the plan is the header's "Why is this category included?" pill; jumping straight to this category on Home still needs the per-category anchor flagged in the definition doc.
     - **Place cards:** two columns on the 1fr workspace (about 400px each), 10px gap, `place-grid` style: 16px radius, 1px border, 14 to 16px padding.

## 4. Components

### Reach ring (walk only)
- **Meaning:** the centre is the apartment. Distance from the centre is **walking minutes**. The ring shows **only the nearest place of each category** (one ball per category, 5 balls for 5 categories); the full set lives in the strip and the cards. Direction means nothing, because the data has no bearing; the angle is only rank order (see Geometry). The caption no longer says so in words; it reads "Walking only ring" (highlighted) and "One ball per category: its nearest place."
- **Geometry:** concentric rings at 5, 10, 15 and 20 minutes, labelled on one axis as "5 mins", "10 mins", "15 mins", "20 mins". Each label sits on a small frosted backing (4px radius) so it stays legible where it crosses its circle line, like a map scale. Categories are laid out clockwise from the nearest, evenly spaced; the angle is rank order, not geography.
- **Markers:** 11px balls in the **category colour** (see Visual language), white ring. A category whose nearest place is beyond 20 minutes is not drawn on the ring (it remains in the legend, the strip and the rail).
- **Name tags:** every ring ball carries its category name as a small frosted tag (11px/600, white at 62% with a 6px blur, a hairline border in the category colour, text in the category colour mixed toward ink). The tag sits 11px from the ball on the side facing **away** from the apartment, so names fan outward and never crowd the centre; a ball past radius 104px points its tag back **inward** so it stays inside the outer ring. Near the top or bottom the tag is centred above or below the ball. Tags are quiet by default; the selected category's tag firms up (ink, bold, more opaque); out-of-reach tags fade with their ball. Tags never take pointer events.
- **Focus shade:** a soft 150-degree shade over the side of the ring holding the most close places (each ball inside the chosen reach weighs more the nearer it is). It moves when the reach changes. It means "where the nearest places are", never a compass bearing.
- **Reach disc:** the panel's time limit grows a disc over the rings and dims balls outside it. The disc eases over 420 ms. The ring has no control of its own.
- **Legend:** above the ring, under the place total, one button per category (coloured ball and name), ordered nearest first. It selects the category and matches the ring's balls.
- **Caption:** above the ring, under the legend. It begins with a highlighted **"Walking only ring"** chip (olive tint, olive border, footprints icon, 12px/700), because the rest of the panel can be read by another mode, then "One ball per category: its nearest place." The earlier sentence about direction is removed.
- **Centre:** the apartment, drawn with the traveling-dot gradient (`--fs-dot`, `--fs-dot-glow`), the only warm accent on the page.
- **Interaction:** hover a ball for the same tooltip as the strip (category, then walk time, then place); click selects its category in the rail. Hovering the legend and rail rows does not move the ring.
- **Accessibility:** the ring is a supplementary picture and is `aria-hidden`; the same numbers are in the rail, the strip and the cards. It must never be the only way to learn anything.

### Place card
- Name (15 to 16px, 600, ink) with, at its right, the "Nearest" tag (first card only) and a **Maps** link (small pill with a pin icon, opens the place on Google Maps in a new tab; the real build builds the URL from the place id).
- One meta line: five **gold stars** filled to the rating, the score and review count ("4.6 (812)"), price, and **today's opening hours** ("Today 7:00–22:00", "Open 24 hours") in place of "Open now". Only the parts that exist show. A basic-depth category has none of these; the card then carries name, Maps link and travel only, with no empty slots. The card's height does not change.
- **Travel block:** four cells, always in the order Walk, Cycle, Drive, Transit. Each cell: icon, minutes (tabular), a thin bar, and kilometres in muted small text for Walk. The **Walk cell leads** (accent fill, ink on it); the others are quieter. All bars share **one scale across the whole page (0 to 30 minutes, clipped)**, so a renter can compare modes within a card and cards with each other. A clipped bar shows "30+".
- **States inside a cell:** estimate gets a small "est." marker; unavailable mode shows an en dash and "No route", never zero.
- Cards are **not interactive** (no detail page yet), so no hover lift, matching R1's place cards.

### Rail row, mode strip, strip band
Same family tile and chip vocabulary as R1 (`.cat-tile`, `.chip`). Count and minute figures use `tabular-nums`. Mode strip cells reuse the travel-block cell, one level down in emphasis.

## 5. Visual language (what R2 reuses, not what it invents)

| Area | Rule, taken from what ships |
|---|---|
| Surface | `--fs-panel` (white 62%), `--fs-panel-border`, `--fs-panel-shadow`, 24px blur for panels; `--fs-card` for cards; inset zones `--fs-tile` (olive 7%) with `--fs-tile-border`. Page background comes from `body`; R2 paints none of its own. |
| Radius | Panels 22 to 28px, cards 16px, tiles 11 to 14px, chips and pills round. |
| Text | Ink `--fs-ink` for content, `--fs-muted` for secondary, 4.5:1 minimum. Manrope everywhere; Fraunces italic only for the one heading keyword. |
| Colour | Olive accent `--fs-accent` for the lead mode and selection. Category identity on the ring, strip, legend and rail dot uses one **category colour** each: Supermarket `#b35a12`, Gym `#1d6fa3`, Park `#55761f`, Café `#1f7a80`, Pharmacy `#8b4a7a`, Swimming pool `#8a907a` (assign by category in the real build; the first five are the theme's deep step tones plus a mauve). Rail tiles and place cards keep the four **family** palettes from `r1.css`. Stars are `#a8690c` on `#d3d7c3`. Teal `#1F7A80` only as the heading keyword and the summary's key figures. Status uses rose (`Step-2`) for "needs attention" and `--fs-done` for finished. No second warm accent; no wheat (retired with the dark theme), no indigo. |
| Icons | lucide-react, 1.7 stroke, 19 to 20px in 34 to 44px tiles. Categories via `TaxonomyIcon` (taxonomy node, so the same icon as the Home plan). Modes: `FootprintsIcon` (Walk), `BikeIcon` (Cycle), `CarIcon` (Drive), `TrainFrontIcon` (Transit). |
| Glass | Real blur on every glass layer. Entrance animations use `animation-fill-mode: backwards` and never hold a final opacity frame (R1 comment and DESIGN.md "Real Blur Rule"). |
| Hover | Only on things that act: rail rows (`hover:bg-(--fs-tile)`, 200ms, `ease-Easing-Out`), ring markers, buttons. Focus is `focus-visible:ring-2 ring-Brand-500/60`, outline offset 2px. Cards and strip bands have no lift. |

## 6. Motion

One authored moment per surface, as in R1. All delays come from a `--d` variable.

- **Arrival:** heading fades in; the summary panel uses `r1-panel` (480ms, rise 14px and settle from 0.985); rail and workspace follow at 140ms steps.
- **Strip:** segments grow from the left using `r1-pip` (420ms), 80ms apart.
- **Ring (focal):** rings draw outward over 600ms (`cubic-bezier(.2,.8,.2,1)`), then markers pop with `r1-chip-pop` (450ms, 40ms stagger, capped at 600ms total), the apartment dot last.
- **Category switch:** workspace content cross-fades; cards rise with `r1-card-rise` 60ms apart, capped so ten cards finish under 600ms. Ring and strip do not move.
- **Loading:** `r1-sheen` skeletons in the panel and the rail; the status line says it is still working after 12 seconds (R1's slow wait).
- **Reduced motion:** every animation removed; shapes appear complete; transitions off (the R1 media block).
- Wires and the traveling light are the product's "agents handing work along" motif and do not belong on a results page. Do not use them here, apart from the single apartment dot.

## 7. States and ranges

| State | Treatment |
|---|---|
| Running | Skeleton summary, skeleton rail rows, "Looking around the apartment". The run status carries no partial data, so nothing is filled early. |
| Finished | Everything above. Typical 3 to 8 categories, up to 10 places each; roughly 10 to 60 markers on the ring. |
| One category, none found | Rail row muted ("None found"); workspace shows a quiet sentence with the radius ("Nothing found within 2 km"), no empty grid. |
| Capped | "Showing the nearest 10" note. Counts in the rail and summary say "10" and never imply a total. |
| Estimated travel | "est." in the cell; the note names it once. |
| Whole result empty | One panel, no ring or strip: "Nothing found around this apartment" and a way back to Home. |
| Failed, retryable | R1's RunNotice pattern: plain reason, **Try again** primary button (retry resumes after discovery). |
| Failed, final | Same notice, **Back to Home** only. |
| 401, 404, 409, 422, 503 | 401 returns to sign-in; 404 is "This search can't be found"; 409 and 503 use the retry notice; 422 means the input was wrong and goes back to Home. |

## 8. Responsiveness

Desktop first. From 900px: as described. Below 900px the summary panel stacks (time limit, mode fit, strip, Options within reach, Not found, then total, legend, caption and ring); mode fit becomes a 2 by 2 grid below 640px. Below 1024px the rail becomes a horizontally scrolling row of chips pinned under the page top; the workspace is one column below 640px. The ring never goes below 240px; if the panel is narrower, it spans the full width.

## 9. Anti-goals

No map. No dark theme. No wheat, indigo or a second warm hue. No "best" or ranking language. No scores, grades or verdicts about the apartment (this page is evidence; judgments belong to later stages). No panel inside a panel, apart from tiles inside the category header. No wires or traveling lights. No gradient text. No placeholder counts or fabricated places on the shipped page.

## 10. Open decisions (a builder must not invent these)

1. **Radius:** the renter chooses it, but the status response does not echo it and the search is currently a fixed 2 km circle. Where is it set (Home composer or on this page), and does changing it start a new run? Until decided, show it read-only.
2. **Address to coordinates:** R2 needs coordinates; no geocoding step exists. The heading needs an address string.
3. **Fetch time:** the result has no timestamp, so the page cannot say how fresh the data is.
4. **Home anchor:** the "link back" needs a per-category anchor on the Home plan.
5. **Lead mode:** Walk leads on every card because the ring is walk-only. Should a renter be able to switch the lead mode later?
6. **Category colours:** the category palette above is new (R1 colours by family, four hues). Confirm it, and decide how colours are assigned when a renter has more than six categories.
7. **Hours and Maps data:** today's hours need the standard depth; the Maps link needs the place id from discovery. Both are shown only when present.
8. **Route to the page:** URL shape and how the renter reaches it from the Home result (per apartment, `run_id`).
