# R2 Amenity Search: Frontend UI Definition

What R2 is for, what it produces, which of its data the renter should see, and how the renter should experience it. This is the basis for the R2 UI design pass (impeccable), not the design itself.

Grounded in:
- `README.md` (product and Deep Search overview)
- `backend/src/services/deep_search/feature_context/deep_search_context.md` (Neighborhood Quality and Responsibility-2 problem context)
- `backend/src/services/deep_search/amenity_search.py`, `r2_run_coordinator.py`, `feature_schemas/schemas.py`, `backend/src/clients/google_places.py` (what the code actually does today)
- `frontend/src/features/r1-interpretation/` (how R1 was surfaced)

Section numbers match the six questions asked.

**Page context.** R2 has its own page, dedicated to the results for one apartment, just as the Home page is dedicated to R1. The renter has already read the R1 plan on the Home page. So the R2 page shows only what R2 produced and never shows the R1 plan again. See "The R1 plan on the R2 page" in section 4.

---

## 1. Why R2 exists

HomeScout answers one question for a renter: **"Will my life work from this address?"**
Today the renter answers it by hand. They open a map, search one amenity type at a time, and cross-check distances themselves. There is no single view of whether their own list of priorities is met.

R1 decides **what** to look for. It turns the renter's brief into a plan per kind of place: which category, how deep, which facts.
R1 looks nothing up. Its output is a plan, not data.

**R2 is the first moment HomeScout touches the real world.** It takes R1's plan plus the address, and finds the actual places around it, with real facts and real travel times.

Without R2:
- R1's plan has nothing to apply to.
- R3 has no places to investigate.
- Deep Analysis and the Matching Engine have no neighborhood evidence to judge an apartment with.

So R2 exists to turn "what you care about" into "what is actually around this address, and how easy it is to reach".

## 2. R2's goal for the renter

In one line: **show the renter, for every kind of place they care about, what exists near the address and how easy each one is to reach, as facts they can trust.**

The renter wants (from the R2 problem context):

| Want | What it means for R2's output |
|---|---|
| Preference match | Results organized by *their* categories, not a generic map list |
| Real accessibility | Travel time per mode (walk, cycle, drive, transit), not straight-line distance |
| Structured presentation | Grouped by category, then by place, then by fact |
| Right-depth detail | More facts where they care more, fewer where they do not |
| Baseline coverage | Also covers a few categories they did not name (R1 inferred them) |
| Factual correctness | Values exactly as Google holds them, never guessed |
| Honest absence | "Not found" said plainly, never filled in |
| Data-point completeness | Working links, numbers with units (km, minutes) |
| Currency | Values are true as of when they were fetched |

R2 deliberately stops at **facts**. It does not judge, score or recommend. Judgments come later (R3 resolves the renter's own questions; Deep Analysis assesses).

## 3. How R2 works, stage by stage, and what each stage produces

```
R1 plan + address + radius
        │
        ▼
Stage 1  Discovery      ──► the places found per category        (saved checkpoint)
        │
        ▼
Stage 2  Enrichment     ──► real travel per place, per mode
        │
        ▼
Stage 3  Attachment     ──► one fact record per place per category  = R2 result
        │
        ▼
     R3 (answers the renter's own questions about each place)
```

### Stage 0. Input (from R1 and the renter)

| Data | Source | Example |
|---|---|---|
| Category plans | R1 result | `category_id: 2`, `taxonomy_node: "gym"`, `depth: "operating_details"`, the predefined metrics list |
| Origin | Renter's address as coordinates | `51.5074, -0.1278` |
| Radius | Renter, default 2 km | `2.0` |

The **depth** of each category is the key link from R1. It decides which facts R2 asks Google for.

### Stage 1. Discovery (M1.1)

What happens:
- One Google Places "Nearby Search" per category.
- Bounded by a hard circle: the address at the center, the radius as the edge.
- Searches for exactly one Google place type per category (the `taxonomy_node`, for example `gym`, `cafe`).
- Ranked by **distance**. Keeps the **10 nearest** per category.
- Asks only for the fields the category's depth allows.
- The found set is frozen. Nothing is re-searched later.

What it produces: `discovered_places`, per category, per place: the raw Google profile.

Insight it carries:
- **How many** of each kind of place exist near the address (0 to 10).
- **Which categories came back empty** inside the radius.
- **The search frame**: the address, the circle, the place type searched.

### Stage 2. Enrichment (M1.2)

What happens:
- For every place found (deduplicated across categories), measures real travel from the address.
- Walk, drive and cycle: Google route summaries, one search per mode.
- Transit: Google Routes, bus, subway and train in one call.
- A mode with no route becomes empty for that place. The place is still kept.
- A transit result Google could only compute in a degraded way is kept and flagged (`used_fallback: true`).

What it produces: `enrichment`, per place: distance and duration per mode, plus transit with its fallback flag.

Insight it carries:
- **How long it really takes** to get to each place, by each mode.
- **Which mode works best** per place (a park 1.2 km away can be 15 minutes walking or 4 minutes cycling).
- **Where travel is hard** (no walking route, no transit route).

### Stage 3. Result attachment (M1.3)

What happens:
- Joins the profile (stage 1) with the travel data (stage 2), per place, per category.
- Converts units: meters to km, seconds to minutes.
- Any missing field becomes `null`. Nothing is invented.

What it produces: the R2 result, one `PredefinedMetricsRecord` per place per category.

| Group | Fields | Fetched at depth |
|---|---|---|
| Identity | `name`, `category`, `address`, `coordinates`, `place_id` | all |
| Links | `website`, `google_maps_uri` | all |
| Access | `routing.walk / drive / cycle` (km, min), `transit` (km, min, fallback) | all |
| Operating details | `opening_hours`, `contact_phone`, `rating`, `review_volume`, `price_level`, `reviews` | `operating_details` and `specific_attributes` only |

A `null` therefore has two meanings, and the UI can tell them apart from `depth`:
- **Not asked for**: the category is `basic_profile`, so operating details were never requested.
- **Not available**: they were requested, and Google had no value.

### What R2 does NOT do today (important for honest UI copy)

The original R2 spec also described relevance filtering and narrowing to a "representative set". **Neither is built.** In the code:
- R2 returns up to the **10 nearest** places of the Google type, as Google labels them.
- A mislabeled place can appear (Google ranks by type and proximity).
- There is no "best of" selection and no judgment.

So the UI must say "nearest", not "best", "top" or "recommended".

## 4. Which stage outputs to show the renter

The test, taken from what worked in R1 ("What I'll look for" was shown because it explains the final output and is complete on its own, like the User Persona panel):

1. **Explains the final output.** It helps the renter see *why* the result looks the way it does.
2. **Complete on its own.** It describes one whole aspect of the neighborhood without needing anything else.
3. **Speaks the renter's language.** Minutes, places and their words, not field masks or IDs.

### Verdict per stage

| Stage | Show? | As what | Why |
|---|---|---|---|
| Input: R1 plan | No, not as content | Used only for order, a gap note where facts weren't requested, and a link back to the R1 plan | The Home page already shows the plan. The R2 page shows only what R2 produced. |
| Discovery | **Yes** | **"What's around"**: the search frame and coverage per category | Complete on its own: it says what exists near the address and what does not. Empty categories are a real finding. |
| Enrichment | **Yes, as the access summary** | **"How easy it is to reach"**: across all places and categories, for example "6 of your 8 kinds of place are within a 10 minute walk", and the nearest place per category by walking time. Shown in the neighborhood summary and category rows. | Travel time is R2's most valuable and most original data. Across the neighborhood it is the headline, and no single place card can show it, because it compares all places and all categories. |
| Attachment | **Yes, as place cards** | **Place cards**: profile, links and operating details, plus travel time by each of the four modes, inside each category | Attachment joins the profile with the travel data, so each place's travel time already lives in its record. Where a category's detail level left facts out, say so once, so it doesn't look like missing data. |
| Handoff to R3 | No | Nothing on the R2 page | The renter's own questions (R1's specific metrics) are already listed in the R1 plan. R3 will show them with their answers. Listing them here as pending would repeat the plan. |

### Enrichment and attachment share one data source

Attachment joins enrichment's travel data into each place record. So the finished `result` already holds `routing` and `transit` inside every place, and enrichment has no separate output to display. Every R2 display reads the same finished `result`, because nothing comes back before the run finishes.

That gives enrichment two roles on the page:

- **For one place**, travel time is part of the place card. It is not a separate display.
- **Across the neighborhood**, travel time is the headline. A single place card can't show it, because it compares all places and all categories. That summary is the only reason enrichment gets its own row above. It is a calculation over the same result, not a second data source.

Either way, travel time stays the most prominent number: first on each place card, and the lead line of the summary.

### The R1 plan on the R2 page

R1's output shapes the R2 page in three ways. None of them shows R1 content again.

1. **Order.** The categories the renter asked for come first. The categories R1 inferred come after, under one group heading (for example "Also worth knowing"). This is a layout rule, not extra text.
2. **A gap note, only where facts are missing.** A `basic_profile` category has no hours, rating or reviews. One short line, only on those categories, explains it: "Hours and reviews weren't checked here." It describes R2's result, not R1's plan. Categories with full facts get no note and no detail-level label.
3. **A link back.** Each category links to its sheet in the R1 plan on the Home page, for a renter who wants to know why it is there and what was planned for it. The explanation lives in one place only.

Not on the R2 page: "Because you asked for…" lines, the renter's characteristics, R1's reasons, detail-level labels on every category, the list of facts R1 planned, and R1's specific metrics.

### What to keep hidden

- Field masks, Google place type strings, `place_id`, `taxonomy_node` raw values
- Meters and seconds (only converted km and minutes)
- Step names, checkpoints, retries, the deduplication of places across categories
- Raw discovery output as a separate list. It is the same places as the final result, so showing it twice adds nothing. Show the **frame and counts** of discovery, not the list again.

### Three transparency units (each complete on its own)

**A. The search frame** (from discovery + input)
- Address, radius circle, number of categories searched.
- Per category: "Looked for gyms within 2 km. Found 7, nearest first."
- Empty: "No daycare within 2 km." Said as a finding, not an error.
- Capped: "10 shown, there may be more further out" when a category hits the cap of 10.

**B. The access summary** (enrichment data, read from the finished result)
- Across the neighborhood: how many of the renter's categories are within a short walk (for example 5, 10, 15 minutes).
- Per category: the nearest place by walking time.
- Calculated in the page from every place's `routing` and `transit`. Not a separate data source.
- Per place travel is not part of this unit. It lives in the place card (four modes, minutes first, km second, a transit fallback shown as "estimate", a missing mode shown as "No walking route found").

**C. The gap note** (from R1 depth + attachment)
- Only on categories whose detail level left out operating details (`basic_profile`).
- One line: "Hours and reviews weren't checked here." Turns an empty field into an explained choice.
- No detail-level label on other categories. The level itself is shown in the R1 plan, one link away.

### Live progress

The status endpoint only exposes:
- `running` with no `completed_step`: discovery in progress
- `running` with `completed_step: "discovery"`: places found, travel being measured
- `finished`: everything at once, with `result`
- `failed` with `retryable`

There is **no partial data mid-run** (no counts, no places until `finished`). So progress can show the three stages, with stage 1 confirmed by the checkpoint, and must not show fake counts or fake places while running.

Suggested progress copy:
1. "Finding places around your address" (until `completed_step: "discovery"`)
2. "Measuring real travel times" (after the checkpoint)
3. "Putting the facts together" (brief, then the result)

## 5. How the renter should perceive the data

### The problem, from the renter's side

The renter is deciding whether to spend time on an apartment. Their real friction:
- Map hopping, one category at a time
- A distance number that hides how hard the trip really is
- Lists of everything with no relation to what they asked for
- Not knowing what's missing

What they want to feel after R2: **"I can picture my week from this address, and I trust what I'm seeing."**

### The intended perception

R2 should feel like **a walk around the block from the front door, guided by someone who knows what you care about.** Not a map dump, not a ranking.

| Feel | Means in the UI |
|---|---|
| **Personal** | Organized by the renter's categories, the ones they asked for first, inferred ones after under one group heading. The reason for each lives in the R1 plan, one link away, not repeated here. |
| **Grounded in time** | Minutes are the primary number. Km is secondary. Mode icons, not text labels. |
| **Honest** | Absences are findings. "Nearest", never "best". Fallback transit says "estimate". Nothing looks more certain than it is. |
| **Open and soft** | Plain first-person voice, as in R1 ("Here's what I found around…"). No dense tables at the top level. Short sentences. |
| **Layered** | Summary first, depth on demand. The renter is never forced through every fact. |
| **Factual, not judgmental** | Show ratings and review counts as facts with their volume. No scores, no badges like "great". R3 and Deep Analysis do the judging. |

### Information layers (summary to detail)

1. **Neighborhood summary.** The address, the radius, how many categories were found, and the access headline (for example "6 of your 8 kinds of place are within a 10 minute walk"). A visual of places grouped by walking time is a good fit. It must be labeled as walking time per place, not presented as a true travel-time map.
2. **Category rows.** One per category: name, number found, nearest place with its walk time, the empty or capped notes, the gap note where it applies, and a link back to this category in the R1 plan.
3. **Place cards.** Name and type, address, the four travel modes, links (Google Maps, website, phone). At deeper levels: open now and today's hours, rating with review count, price level, review excerpts.
4. **Detail on demand.** Full weekly hours, all reviews, "How I searched this category" (the search frame for that category).

### Value formatting rules

| Field | Show as |
|---|---|
| `duration_min` | Rounded whole minutes ("6 min"). Under 1 min: "1 min". |
| `distance_km` | One decimal ("0.4 km") |
| `transit.used_fallback: true` | "about 7 min" plus an "estimate" note |
| A mode that is `null` | "No walking route found" (and similar per mode) |
| `rating` + `review_volume` | "4.3 from 812 reviews". Never a rating without its count. |
| `price_level` (Google integer) | 0 unspecified (hide), 1 Free, 2 Inexpensive, 3 Moderate, 4 Expensive, 5 Very expensive. Shown as a scale, for example `££` and its word. |
| `opening_hours.open_now` | "Open now" or "Closed now", with "as of when I checked" |
| `opening_hours.weekday_descriptions` | Today's line first, full week on demand |
| `contact_phone` | Tappable link |
| `website`, `google_maps_uri` | Labeled links ("Website", "Open in Google Maps") |
| `reviews` | Short excerpt, star rating, author name, relative time. Keep Google's author attribution. |
| Not asked for (basic depth) | Not shown as an empty field. One gap note on the category: "Hours and reviews weren't checked here." |
| Not available (requested, no value) | "Not listed on Google" |

## 6. The product goal and how R2 proves it is working

### HomeScout's goal

HomeScout wants to remove the manual work of judging an apartment and its neighborhood. The renter describes what they want in plain language. HomeScout's agents interpret it, gather evidence, evaluate, rank and follow up, and keep the renter in the loop.

Neighborhood quality is built from three blocks:

| Block | Role | What the renter learns |
|---|---|---|
| R1 | Interpret the brief | "HomeScout understood what I care about and how much." |
| **R2** | **Find the real places and their facts** | **"These are the places around this address, and this is how easy they are to reach."** |
| R3 | Answer the renter's own questions per place | "This café really has wifi, this gym is quiet in the evening." |

R2 is the evidence base. Every later judgment (R3, Deep Analysis, the Matching Engine) reasons from R2's places and facts. If R2 feels thin or untrustworthy, nothing built on it will be trusted.

### How the UI shows R2 is doing its job

| The renter should be able to see | Shown by |
|---|---|
| Every category R1 planned was actually searched | Each R1 category appears in R2, including empty ones |
| The search matched their request | The address and radius stated up front, their categories first, and a link back to the R1 plan per category |
| Access is real, not a straight line | Four modes with minutes per place |
| The detail matches how much they care | Richer place cards where they asked for detail, and a gap note where facts weren't checked |
| Nothing was made up | "Not listed on Google", "No walking route found", "estimate" |

The success test from the renter's side: **after reading R2, they can say what is near the address, how long each thing takes to reach, and what is missing, without opening a map.**

---

## Appendix A. Data facts and gaps the UI must handle

| # | Fact or gap | Impact on UI |
|---|---|---|
| 1 | R2 needs `origin` as latitude/longitude. The composer asks the renter to paste an address into the brief, and the backend has no geocoding step. | Decide where the address becomes coordinates before R2 can start. |
| 2 | `radius_km` is accepted by the API (default 2), but the composer shows a static "2 km". | Decide whether the renter can change the radius (the "Scoped Search" want). |
| 3 | The status response has no fetch time. | "As of" can only use the time the page received `finished`. A backend `fetched_at` would make it exact. |
| 4 | The status response does not echo `origin`, `radius_km` or `r1_run_id`. | The page must keep them from the start request, or the backend adds them. |
| 5 | Whether a category was asked for or inferred, and its depth, live in the R1 result, not in R2's. | The R2 page loads the R1 run too. Join R2 categories to R1's `explicit_categories` by `category_id`; a category not in that list is inferred. Used for order and the gap note only, not shown as content. |
| 5a | The link back needs a target. The Home page has no per-category anchor or route for the R1 plan today. | Add a stable anchor per category sheet on the Home page (for example by `category_id`), or a route to a given R1 run's plan. |
| 6 | The same place can appear under two categories. | Show it in both, optionally noting "also counted under…". |
| 7 | No relevance filtering or narrowing is built. Up to 10 nearest per category. | Copy says "nearest", never "best". |
| 8 | `taxonomy_node` is a Google place type such as `gym` or `cafe`. (The earlier sample showed `"Fitness > Gym"`; the real value is the Google type.) | Map it to a readable label, as R1 already does with `taxonomyLabel`. |
| 9 | `price_level` arrives as Google's integer enum. | Use the mapping in section 5. |
| 10 | Google Places content (ratings, reviews) is displayed. | Check Google Maps Platform attribution rules for Places data and review authors before release (not verified here). |
| 11 | Results are only available when `finished`. | Progress UI shows stages only, never partial data. |
