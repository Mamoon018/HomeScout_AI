# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Renters looking for an apartment. They are tired of searching listing sites one at a time, messaging dozens of owners and losing track of the replies, and checking by hand whether an apartment and its neighborhood actually fit their priorities. They want to describe what matters in plain language and let the work happen for them while they stay informed.

## Product Purpose

HomeScout is an agentic apartment-search assistant. Agents search for apartments across many websites, evaluate each apartment and its neighborhood in depth, call and follow up with owners about inquiries, and keep working in the background while keeping the renter in the loop.

The product is organized into five features: Deep Search, Deep Analysis, Matching Engine, Owners Outreach, and User Feedback. The app also surfaces these as result areas, including Home Wishlist and Analysis Report. Deep Search is the most mature: it interprets the renter's requirements, discovers neighborhood amenities, and resolves specific, in-depth facts about them.

Success: the renter decides which apartments are worth pursuing with less manual effort and more confidence, because the evidence behind each judgment is visible.

## Positioning

What sets HomeScout apart from a listings site or a map search:

- **Agents work in the background.** They search across listing sites, call owners and follow up for the renter, and report progress instead of waiting for the renter to drive every step.
- **It judges fit against the renter's own priorities.** It reads a plain-language brief, infers categories the renter would plausibly care about but didn't mention, and gives more depth where the renter cares more.
- **Its judgments are traceable.** Every assessment stays structurally separate from the facts behind it, so the renter can see why, not just a verdict.
- **It measures real travel access.** It uses the actual route, travel mode and time, not straight-line distance.
- **It uses many tools to dig deep.** Web search, web extraction, and Places and Routes data find the specific information a renter asked about (for example, "a quiet café with wifi"), not generic place metrics.

## Operating Context

- The renter starts by writing a natural-language brief describing the neighborhood and home they want, in the composer on the home page.
- The system may pause to ask one grounded clarification question when a requirement is ambiguous, then resumes.
- Long-running agent work is shown as live progress steps (for example: categorizing the request, clarity check, map exploration, area data fetch, tool calls).
- Results arrive per feature area: Deep Search, Home Wishlist, Analysis Report, Matching Engine, Owners Outreach (communication), and User Feedback.
- Owner communication stays in one thread; HomeScout handles follow-ups.

## Capabilities and Constraints

- Stack in place: React 19 + Vite + Tailwind/shadcn frontend; FastAPI backend; Supabase authentication (with captcha on signup); Google Places (New) and Routes APIs; LLMs via OpenAI with Groq fallback.
- Deep Search, requirement interpretation (built): extraction, category resolution with clarification, persona inference, depth assignment, metric definition.
- Deep Search, amenity search (built): place discovery around a listing, with predefined quality metrics and travel-based accessibility.
- Deep Search, specific metric resolution (in development): agents use web search and extraction tools to resolve requirement-specific facts about places.
- Apartment listing search across websites, apartment-quality analysis, Matching Engine, Owners Outreach (calls and follow-ups), and User Feedback are part of the product but less mature or not yet built. Design must not present them as shipped capabilities with real data until they are.
- Terminology: "Deep Search", "neighborhood brief", "priorities", "amenities", "depth", "metrics", "agents".

## Evidence on Hand

Real outputs exist from three Deep Search stages and may be shown as examples:

1. **User requirements**: the renter's brief as a structured specification (categories, priority, depth, metrics). See `backend/src/services/deep_search/sample_output/sample_outputs.py`.
2. **Amenity search**: places discovered in a neighborhood with predefined metrics. See `backend/src/services/deep_search/sample_output/search_nearby_response.json` and `backend/src/services/deep_search/feature_sample_runs/data/m1_1_discovered_places.json`.
3. **Specific metric resolution**: in-depth, requirement-specific facts about places. See `backend/src/services/deep_search/sample_output/r3m22_run.txt`.

There are no real users, testimonials, customer logos, usage numbers, press, or pricing. Do not fabricate them. Scores, listing counts and budgets in the current UI are mock data.

## Product Principles

1. **Keep the renter in the loop.** Background work is always visible: what agents are doing, what they found, and what needs the renter.
2. **Priorities come first.** The renter's stated needs drive what is searched and how deeply; inferred needs rank below them.
3. **Show the why.** Separate facts from judgments and let the renter trace any verdict back to its evidence.
4. **Real-world truth over proxies.** Prefer actual travel time and specific verified facts to straight-line distance and generic ratings.
5. **Don't overclaim.** Represent unbuilt or partial capabilities honestly.

## Accessibility & Inclusion

WCAG 2.2 AA. No additional audience-specific requirements established.
