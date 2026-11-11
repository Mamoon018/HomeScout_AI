---
name: HomeScout
description: Agents that run the whole home hunt for renters, under an olive dusk sky.
colors:
  wheat: "#e6d3a3"
  wheat-light: "#efe3c2"
  wheat-glint: "#f4e9cc"
  wheat-spark: "#f6ebc8"
  olive-ink: "#1a2313"
  olive-night: "#1f2a16"
  olive-moss: "#3e4b28"
  olive-sage: "#6b7a45"
  olive-meadow: "#8c9a5c"
  dusk-glow: "rgba(242, 245, 223, 0.22)"
  menu-olive: "#2c3720"
  glass-card: "rgba(255, 255, 255, 0.07)"
  glass-raised: "rgba(255, 255, 255, 0.11)"
  glass-inset: "rgba(14, 20, 9, 0.32)"
  glass-dark: "rgba(16, 22, 10, 0.45)"
  glass-line: "rgba(255, 255, 255, 0.16)"
  cream-text: "#f4f6ec"
  sage-muted: "#c5cab0"
  sage-placeholder: "#aeb3a0"
  hero-lead: "#c2c0aa"
  lime-success: "#bfe36b"
  destructive: "#ef4444"
  step-amber: "#fcd34d"
  step-pink: "#f9a8d4"
  step-orange: "#fdba74"
  step-cyan: "#67e8f9"
  step-coral: "#fca5a5"
  feature-sky: "#7dd3fc"
  feature-sage: "#a8d5c6"
typography:
  display:
    fontFamily: "Manrope, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif"
    fontSize: "52px"
    fontWeight: 500
    lineHeight: 1.06
    letterSpacing: "-0.025em"
  display-keyword:
    fontFamily: "Fraunces, Georgia, serif"
    fontSize: "1.1em"
    fontWeight: 500
    letterSpacing: "-0.01em"
  display-secondary:
    fontFamily: "Manrope, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif"
    fontSize: "30px"
    fontWeight: 400
    lineHeight: 1.2
    letterSpacing: "-0.015em"
  lead:
    fontFamily: "Manrope, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif"
    fontSize: "17px"
    fontWeight: 500
    lineHeight: 1.5
  headline:
    fontFamily: "Manrope, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif"
    fontSize: "44px"
    fontWeight: 600
    lineHeight: "normal"
  title:
    fontFamily: "Manrope, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif"
    fontSize: "20px"
    fontWeight: 600
    lineHeight: 1.4
  title-sm:
    fontFamily: "Manrope, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif"
    fontSize: "18px"
    fontWeight: 500
    lineHeight: 1.375
  body:
    fontFamily: "Manrope, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif"
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.5
  body-sm:
    fontFamily: "Manrope, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.43
  label:
    fontFamily: "Manrope, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif"
    fontSize: "14px"
    fontWeight: 600
    lineHeight: 1.375
  caption:
    fontFamily: "Manrope, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif"
    fontSize: "12px"
    fontWeight: 500
    lineHeight: 1.33
  data:
    fontFamily: "SF Mono, Roboto Mono, monospace"
    fontSize: "12px"
    fontWeight: 400
rounded:
  sm: "4px"
  md: "8px"
  field: "10px"
  button: "12px"
  send: "14px"
  card: "16px"
  panel: "22px"
  pill: "9999px"
spacing:
  space-1: "4px"
  space-2: "8px"
  space-4: "16px"
  space-6: "24px"
  space-12: "48px"
components:
  button-primary:
    backgroundColor: "{colors.wheat}"
    textColor: "{colors.olive-ink}"
    typography: "{typography.label}"
    rounded: "{rounded.button}"
    height: "44px"
  button-send:
    backgroundColor: "{colors.wheat}"
    textColor: "{colors.olive-ink}"
    rounded: "{rounded.send}"
    size: "44px"
  input:
    backgroundColor: "{colors.glass-dark}"
    textColor: "{colors.cream-text}"
    typography: "{typography.body-sm}"
    rounded: "{rounded.field}"
    height: "36px"
  glass-panel:
    backgroundColor: "{colors.glass-card}"
    textColor: "{colors.cream-text}"
    rounded: "{rounded.panel}"
    padding: "24px"
  feature-card:
    backgroundColor: "{colors.glass-card}"
    textColor: "{colors.wheat}"
    rounded: "{rounded.card}"
    padding: "16px"
  status-pill:
    backgroundColor: "{colors.glass-dark}"
    textColor: "{colors.wheat}"
    typography: "{typography.body-sm}"
    rounded: "{rounded.pill}"
    padding: "8px 14px"
  badge:
    backgroundColor: "{colors.glass-dark}"
    textColor: "{colors.wheat}"
    typography: "{typography.caption}"
    rounded: "{rounded.md}"
  menu:
    backgroundColor: "{colors.menu-olive}"
    textColor: "{colors.cream-text}"
    rounded: "{rounded.md}"
  menu-bar:
    backgroundColor: "{colors.glass-card}"
    rounded: "{rounded.pill}"
    padding: "6px"
  menu-bar-item:
    textColor: "{colors.wheat}"
    typography: "{typography.body-sm}"
    rounded: "{rounded.pill}"
    padding: "8px 16px"
  sign-in-card:
    backgroundColor: "{colors.glass-card}"
    textColor: "{colors.cream-text}"
    rounded: "{rounded.panel}"
    padding: "28px"
    width: "400px"
  workflow-card:
    backgroundColor: "{colors.glass-card}"
    textColor: "{colors.wheat}"
    rounded: "{rounded.send}"
    padding: "11px 12px 12px"
    width: "220px"
  workflow-node:
    backgroundColor: "#3c4a26"
    textColor: "{colors.wheat}"
    rounded: "{rounded.pill}"
    size: "28px"
---

# Design System: HomeScout

## Overview

**Creative North Star: "The Olive Grove at Dusk"**

HomeScout runs the home hunt at the hour when the light goes gold. Every screen sits on an olive sky: deep night-olive on the left, warming to sage and meadow on the right, with a soft glow rising from the top-right corner as if the sun has just set. A wheat-colored crescent moon carries the brand, and scattered pixel stars drift over the field. The agents work through the evening while the renter rests.

The interface floats on that sky as frosted glass. Panels are translucent white over the gradient, blurred, edged with a thin light line and lifted by a soft olive-black shadow. Wheat is the only warm accent: headings, labels, the primary action and anything that marks the renter's attention. Everything else stays cream and sage. The mood is atmospheric and premium. Glow, glass and the gradient are the signature, and hero moments are allowed some drama, but each screen keeps one point of focus.

Olive replaces the earlier Linear system: charcoal surfaces with an indigo accent. That look is retired and must not return.

**Key Characteristics:**
- Olive dusk gradient on `body`, fixed, with a top-right glow; components never paint their own page background.
- Frosted glass surfaces (white at 6–11% alpha, 16–24px blur, thin light border, inner top highlight).
- Wheat as the single warm accent; cream for primary text, sage for secondary text.
- Large, softly rounded containers (16–22px) with tighter radii on controls inside them.
- Manrope for every working word; Fraunces italic only for the one or two keywords a hero headline turns on.
- Per-step and per-feature agent colors appear only as identity signals (icons, key numbers, bars, live dots), never as text or decoration.
- Wheat wires with a traveling light are the motion signature: they show agents handing work along.

## Colors

A warm, low-saturation olive field lit by a single wheat accent, with cream text and a lime signal for success.

### Primary
- **Harvest Wheat** (wheat): The voice of the brand. Page and card headings, form labels, links, the moon logo, primary and send buttons, tracker labels, and the model name in the composer. Hovers mix it 10–12% toward white; active presses mix it 6% toward black.
- **Pale Wheat** (wheat-light): Lighter brand tint for highlight states.
- **Wheat Glint** (wheat-glint): Serif keywords in the sign-in headline, a step brighter than the line around them.
- **Wheat Spark** (wheat-spark): The core of every traveling light: the workflow light and the spark under "the match."
- **Olive Ink** (olive-ink): Text and icons placed *on* wheat, such as the label on the Sign In button and the send icon. Also the darkest stop of the sign-in gradient.

### Secondary
- **Spring Lime** (lime-success): Completed steps and success states. Reserved for "done"; never used as decoration.

### Tertiary
- **Agent Step Palette** (step-amber, step-pink, step-orange, step-cyan, step-coral): One color per Deep Search progress step (categorizing, clarity check, map exploration, area data fetch, tool calls). They tint step tiles at 10%, dash the connector line, border and glow the active pill. Outside the progress timeline they do not appear.
- **Feature Accents** (step-amber Home Wishlist, feature-sky Deep Search, feature-sage Analysis Report, step-pink Matching Engine, step-orange Owners Outreach, step-coral User Feedback): Identify the six features in the sign-in agent workflow. Inside a card they color only icons, the running title, bars, live dots, owner/agent meta labels and key percentages; all content text stays wheat.

### Neutral
- **Night Olive** (olive-night): Home page gradient start and fallback page color.
- **Moss** (olive-moss) → **Sage Field** (olive-sage): Home gradient middle and end stops (90°, 0% / 55% / 100%).
- **Meadow** (olive-meadow): Brightest stop of the sign-in gradient (105°, `olive-ink` 0%, #2f3b1f 42%, #5e6b38 78%, meadow 100%), with a stronger ellipse glow (rgba(190, 204, 130, 0.55)).
- **Dusk Glow** (dusk-glow): Radial light in the top-right corner of the home page.
- **Cream** (cream-text): Primary text and input text.
- **Sage Mist** (sage-muted): Body and muted text on the home page.
- **Sage Placeholder** (sage-placeholder): Placeholders and muted text on sign-in, and small labels inside workflow cards.
- **Warm Lead** (hero-lead): The sign-in subtitle; a warmer, brighter grey than sage so the lead holds up at 17px over the sky.
- **Glass Card / Glass Raised / Glass Inset / Dark Glass / Glass Line**: The surface ladder. Cards at 7%, raised tiles and bars at 11%, inset zones and fields darkened with olive-black, borders at 16–18% white.
- **Menu Olive** (menu-olive): Solid surface for dropdowns and popovers that must stay readable over glass.

### Named Rules
**The One Warm Light Rule.** Wheat is the only warm accent in the interface chrome. If a second accent seems needed, use a lighter or darker wheat, or cream, not a new hue.

**The Retired Indigo Rule.** No indigo, violet or neutral charcoal surfaces from the old Linear system. Every dark tone is olive-tinted.

## Typography

**Display Font:** Manrope (with -apple-system, Segoe UI, Roboto, sans-serif)
**Accent Font:** Fraunces italic 500, optical size 9–144 (with Georgia, serif), for headline keywords only
**Body Font:** Manrope
**Label/Mono Font:** SF Mono / Roboto Mono, for numeric values in data panels only

**Character:** A geometric-humanist sans carries every working word; its rounded terminals suit the soft dusk world, and medium/semibold weights keep it confident on glass. A warm, high-contrast italic serif is reserved for the nouns a headline turns on ("apartment", "neighborhood"), like a hand-written note on the page. Fraunces is a deliberate choice from the sign-in spec.

### Hierarchy
- **Display** (500, 52px, 1.06, -0.025em): Sign-in hero, first line group ("Tell us your perfect apartment / and neighborhood."). Wheat. 44px below 1100px wide, 34px below 600px.
- **Display Keyword** (Fraunces italic 500, 1.1em ≈ 57px, -0.01em): The keywords inside a display line, each in an `<em>`. Wheat Glint with a soft dark halo (`text-shadow: 0 1px 12px rgba(16,22,10,0.35)`). Punctuation after a keyword stays in Manrope.
- **Display Secondary** (400, 30px, 1.2, -0.015em): The hero's second line group ("Our agent finds the match."), 16px below the first. 26px / 22px at the smaller breakpoints.
- **Lead** (500, 17px, 1.5): Sign-in subtitle in Warm Lead, max 640px wide with balanced wrapping, 14px below the heading. 16px on phones.
- **Headline** (600, 44px, normal): Home welcome heading ("Start your Homescout"), centered over the composer column, on one line. Wheat.
- **Title** (600, 20px, 1.4): Card titles such as "Welcome back". Wheat.
- **Title Small** (500, 18px, 1.375): Feature card titles. Wheat.
- **Body** (400, 16px, 1.5): Default text; the composer textarea on mobile.
- **Body Small** (400, 14px, 1.43): Subtitles, descriptions, inputs, tracker pills (medium; semibold when active).
- **Label** (600, 14px): Form labels (wheat) and button labels (700 on the primary button).
- **Caption** (500, 12px): Badges and keyboard hints.
- **Panel Label** (600, 12px, 0.06em, uppercase): Metric labels inside feature popovers; values beside them use the mono face.

### Named Rules
**The Wheat Heading Rule.** Every heading and form label is wheat, and every body string is cream or sage. Hierarchy comes from color first and size second.

**The Two Keywords Rule.** Fraunces italic appears only inside display headlines, on at most two keywords per headline. Never on labels, buttons, body text or whole sentences.

## Layout

The app is a single centered column on a full-bleed sky. On the home page, `main` fills the viewport (`min-height: 100svh`), with 16px side padding and 48px vertical padding. Content is capped at a 770px column holding the welcome heading, the composer and the progress timeline, separated by 24–32px gaps. Before the first search the column is vertically centered; once a run starts it moves to the top and the heading fades out (200ms) and leaves the layout.

The sign-in page has a centred Olive Glass menu bar in the top row, with the moon logo at the left. From 1280px wide, a 1380px grid follows: the hero headline sits above the 940 × 500px agent workflow on the left, and the 400px sign-in card sits beside the workflow, centred on it, 40px apart; page side padding is 30px. Below 1280px the order becomes hero, sign-in card, workflow, so signing in never sits under the demo. The workflow scales down to 0.8 when space runs short, then becomes a single list of cards. The dark sign-up page keeps its older two-column layout and feature grid. Spacing follows a 4px base (4, 8, 16, 24, 48). 24px is the default content gutter, and 48px is the gap between sections. Cards pad 20px on mobile and 24px from `md` up.

## Elevation & Depth

Depth comes from glass layering over the gradient, reinforced by soft olive-black shadows. Backdrop blur separates each layer from the sky behind it, a one-pixel inner top highlight makes the edge catch light, and a diffuse drop shadow lifts the panel.

### Shadow Vocabulary
- **Panel float** (`box-shadow: 0 8px 24px rgba(0,0,0,0.18)`): Composer and progress cards at rest.
- **Panel lift** (`box-shadow: 0 8px 16px rgba(0,0,0,0.6)`): Composer on hover.
- **Card glass** (`box-shadow: inset 0 1px 0 rgba(255,255,255,0.10), 0 10px 30px rgba(10,14,6,0.35)`): Feature cards.
- **Auth glass** (`box-shadow: inset 0 1px 0 rgba(255,255,255,0.12), 0 16px 40px rgba(10,14,6,0.35)`): Sign-in card.
- **Popover halo** (`box-shadow: 0 0 0 4px color-mix(in srgb, var(--accent) 12%, transparent), 0 18px 40px rgba(6,9,4,0.5)`): Feature result popovers, ringed in their accent.
- **Step glow** (`box-shadow: 0 0 14px color-mix(in srgb, var(--step-color) 35%, transparent)`): The active progress pill only.
- **Workflow card** (`box-shadow: inset 0 1px 0 rgba(255,255,255,0.10), 0 14px 36px rgba(16,22,10,0.25)`): Workflow cards at rest. The running card swaps to a 1px wheat ring at 35% plus a 30px wheat glow at 22%.
- **Traveling light** (`box-shadow: 0 0 10px 3px rgba(230,211,163,0.85), 0 0 24px 8px rgba(230,211,163,0.35)`): The light on the workflow wires and the spark under "the match."
- **Menu bar** (`box-shadow: inset 0 1px 0 rgba(255,255,255,0.12), 0 10px 30px rgba(10,14,6,0.3)`): The top menu pill.

### Named Rules
**The Steady Glass Rule.** Glass over the brightening right side of the sky gets a dark olive tint inside it, rising left to right (0.10 to 0.56 across the six workflow cards), so muted text stays above 4.5:1 everywhere.

**The Real Blur Rule.** Glass must actually blur what is behind it. Don't hold an opacity animation on a glass element's last frame (use `animation-fill-mode: backwards`), or Chrome stops the blur.

## Shapes

Generous, soft corners on containers and tighter corners on the controls nested inside them. Large panels such as the composer, progress card and sign-in card use 22px. Feature cards use 16px; popovers and workflow cards 14px. The send button is 14px, primary buttons 12px, inputs and step tiles 10px, and small chips and menus 8px. Status pills and step dots are fully round. Borders are always one thin light line (white at 16–18%) or a translucent tint of the accent, never a solid opaque stroke.

## Components

### Buttons
Soft and flat: wheat fills with no border and no shadow.
- **Shape:** Gently rounded (12px); the icon-only send button is a 44px square at 14px.
- **Primary:** Wheat background, olive-ink text at 700, 44px tall, full width in forms.
- **Hover / Focus:** Background mixes 10–12% toward white; pressed mixes 6% toward black; transitions run 300ms ease-out. Focus shows a 3px ring in the brand color at 25%.
- **Disabled:** Lowered opacity on the button, never a gray restyle.

### Chips / Badges
- **Badge** ("see results"): Wheat text, 1px accent border, dark glass fill at 45% (65% on hover or when expanded), 12px medium.
- **Panel chip:** Accent border at 40% and accent fill at 10%, semibold.

### Cards / Containers
- **Corner Style:** 22px panels, 16px feature cards.
- **Background:** Glass Card (white at 6–7%), with `backdrop-filter: blur(16–24px)`.
- **Shadow Strategy:** See Elevation (Panel float, Card glass, Auth glass).
- **Border:** 1px white at 16–18%; brightens on hover.
- **Internal Padding:** 20px mobile, 24px desktop; feature popovers 16px.

### Inputs / Fields
- **Style:** Dark glass fill (olive-black at 45%), 1px white border at 18%, 10px radius, cream text, solid sage placeholder.
- **Focus:** Border turns wheat; no glow ring. In the composer, the whole card border shifts to wheat at 55%.
- **Error / Disabled:** Destructive red (#ef4444) for errors.

### Navigation
- **Menu bar (sign-in):** a frosted pill (white at 7%, 1px white border at 16%, 24px blur, fully round, 6px inset) holding Home, Product, Price, Reviews, About us. Items are wheat Manrope 14px medium in round pills (8px × 16px).
- **Hover / Focus:** an item grows to 1.06× over 200ms with a white 8% fill; keyboard focus adds a 2px wheat outline. Reduced motion keeps the fill and drops the scale.
- **Mobile:** the pill drops under the logo, with 13px items and tighter padding, full width.
- The home page has no menu; it is a single focused column.

### Neighborhood Brief Composer (signature)
The home page's centerpiece: a 770px glass card at 22px radius with three zones. Zone A is a toolbar with the model selector (label in wheat) and a "Reasoning" select. Zone B is a textarea that is slightly darkened (olive-black at 16%), at least 100px and at most 240px tall, with placeholder copy that bolds key words. Zone C is a darker footer bar (28%) holding keyboard hints and the wheat send button.

### Deep Search Progress Timeline (signature)
A glass card listing the agent's steps. On the left, a rounded rail with a wheat border at 50% holds five 40px icon tiles, each tinted with its step color. A dashed connector in the step color runs to a pill on the right. Pending pills are dark glass with dim text. The active pill has a wheat label, a border and glow in its step color, and a pulsing step dot. Completed steps show a lime ring.

### Sign-in Card
A 400px glass panel (22px radius, 24px blur, 28px padding) with a 22px wheat title, 42px dark-glass inputs and a 46px wheat submit button. On wide screens it sits beside the agent workflow, vertically centred on it.

### Agent Workflow (signature)
The product's story on the sign-in page: six 220px glass cards (Home Wishlist through User Feedback) in two staggered lanes, joined by 1.6px wheat wires with rounded corners, arrowheads and junction dots. A 9px Wheat Spark light travels from wire to card, and each card shows a status chip: QUEUED (sage), RUNNING (wheat, with a pulsing accent dot) and DONE (lime). A running card gets a wheat border and glow, its title takes the feature accent, and its progress bars refill. Wires sit at 30% opacity ahead, 80% once traveled and 100% with a 7px glow while carrying the light. The 28px agent node on the left starts each run and doubles as the pause/play control; hover, scrolling off screen and hidden tabs also pause it. Reduced motion shows a still snapshot.

### Wire Underline (signature)
A "mini wire" under a short phrase ("the match."): a 1.6px wheat line at 45% with a soft glow, 6px below the text, and an 8px Wheat Spark that glides along it every 2.8s on the workflow's ease-in-out curve, fading in and out at the ends. Under reduced motion the spark is hidden and the line stays.

### Moon Logo (signature)
A crescent drawn from layered surface, crater and terminator tones. It is wheat on the home page and cream on sign-in pages, always with a soft halo. It is the only brand mark.

## Do's and Don'ts

### Do:
- **Do** paint the olive gradient on `body` with `background-attachment: fixed`, and let every page wrapper stay transparent so the sky shows through.
- **Do** build surfaces as glass: white at 6–11% alpha, 16–24px backdrop blur, a 1px white border at 16–18%, and an inner top highlight.
- **Do** use wheat (#e6d3a3) for headings, labels, links and the primary action, with olive-ink (#1a2313) for anything placed on wheat.
- **Do** switch dropdowns and menus to solid Menu Olive (#2c3720) so they stay readable over glass.
- **Do** keep the step palette tied to progress steps and lime tied to completion.
- **Do** keep content in the 770px column on the home flow, and round containers at 16–22px.
- **Do** keep text inside workflow cards wheat, and let each feature accent mark only signals (icons, key numbers, bars, live dots).
- **Do** reuse the wire-and-light vocabulary (1.6px wheat line, Wheat Spark, `cubic-bezier(.45, 0, .55, 1)`) when motion needs to show agent work moving.

### Don't:
- **Don't** bring back the Linear look: no indigo accent (#5E6AD2), no neutral near-black (#08090A) or charcoal surfaces.
- **Don't** introduce a second warm accent beside wheat.
- **Don't** set Fraunces on anything but headline keywords, and never more than two per headline.
- **Don't** put opaque solid cards on the sky, except menus and popovers that need a solid surface for legibility.
- **Don't** use step colors or the lime success color as decoration.
- **Don't** hold an opacity animation's final frame on a glass element; it breaks the backdrop blur.
