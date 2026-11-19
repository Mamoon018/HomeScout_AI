# R3 Specific Metric Resolution: Frontend UI Definition

What R3 is for, what it produces, which of its data the renter should see, and how the renter should experience it. This is the basis for the R3 UI design pass (impeccable), not the design itself.

Grounded in:
- `PRODUCT.md` (product purpose and principles)
- `backend/src/services/deep_search/feature_context/deep_search_context.md` (Neighborhood Quality problem context, "Responsibility-3: Specific Metric Resolution", C3.1 and C3.2)
- `backend/src/services/deep_search/feature_context/R3_Specific_Metric_Resolution_spec.md` (current scope: phase 1 then resolution; triage and phase 2 deferred)
- `backend/src/services/deep_search/specific_metric_resolution.py`, `r3_run_coordinator.py`, `r3_run_store.py`, `feature_schemas/schemas.py`, `feature_prompts/resolution_instruction.py` (what the code actually does today)
- `backend/src/schemas/specific_metric_resolution.py`, `backend/src/app/api/routes/specific_metric_resolution.py` (the HTTP contract the page reads)
- `backend/src/services/deep_search/sample_output/r3m22_run.txt` (a real resolution run)
- `frontend/src/assets/design/R2_frontend_ui_definition.md` (the precedent this document follows)

Section numbers match the six questions asked.

**Page context.** R3 has its own page, for one apartment, just as R2 has. The renter has already seen the R1 plan on Home and the places on the R2 page. So the R3 page shows only what R3 produced: **answers to the renter's own questions, and the evidence behind each answer.** It does not show R2's travel times or R1's plan again. It borrows only what it needs to make an answer readable: the question's wording from R1 and the place's name from R2. See "What R3 borrows from R1 and R2" in section 4.

---

## 1. Why R3 exists

HomeScout answers one question for a renter: **"Will my life work from this address?"**

R1 decides **what** to look for, including the renter's own specific questions per kind of place ("Does the gym have a powerlifting platform?", "Is the café quiet on weekday afternoons?").
R2 finds **which places** exist near the address, with Google's standard facts and real travel times.

Neither answers the renter's specific questions. Google has no field for "powerlifting platform" or "quiet in the afternoon". Today the renter answers these by hand: they open each place's website, read reviews, search forums, and try to tell whether a blog post is about the right place. They repeat this for every place and every question.

**R3 is where HomeScout does that research for them.** It takes R1's specific questions and R2's places, searches the web for each question about each place, reads the Google reviews where a question is about experience, and commits an answer only when the evidence is good enough. Otherwise it says plainly that the answer couldn't be confirmed.

Without R3:
- The renter's most personal requirements (the ones that make the brief theirs) stay unanswered.
- R2's results are generic. Every renter would see the same gyms with the same facts.
- The later assessment (Deep Analysis, the Matching Engine) has nothing specific to judge against the renter's request.

So R3 exists to turn "what you asked about each kind of place" into **"what is actually true about each place, and where it says so"**.

## 2. R3's goal for the renter

In one line: **answer each of the renter's own questions for every nearby place, with the evidence on show, and say honestly where no answer could be confirmed.**

The renter wants (from the R3 problem context and the Neighborhood Quality wants):

| Want | What it means for R3's output |
|---|---|
| Direct relevance | Each answer is shown against the renter's own question, in their words, not as a generic fact list |
| Characteristic match | They can see which places have the quality they asked for. R3 shows the facts; it does not pick or rank places |
| Metric-level correctness | A value is committed only when the evidence meets that question's bar. Never a guess |
| Judgment traceability | Every answer carries the quote it rests on and a link to its source |
| Honest absence | "Couldn't confirm" with a plain reason, never a filled-in value |
| Data-point completeness | Numbers with their unit ("€25", "24 h"), working source links |
| Currency | Each answer says when it was checked |
| Mixed evidence shown, not hidden | Where sources disagree, both sides are visible, and the answer says it leans one way |

R3 deliberately stops at **facts**, even when a fact comes from many visitors' experiences. It does not score, rank, filter or recommend places. "Busy on weekday afternoons" is a fact R3 found. "So this café doesn't suit you" is a judgment that belongs to the later assessment.

## 3. How R3 works, stage by stage, and what each stage produces

```
R1 specific questions + R2 places and Google facts
        │
        ▼
Step 1-2  Plan the work        ──► one work item per place whose category has questions
        │
        ▼
Step 3    Find the website     ──► each place's official website, or none     (saved checkpoint)
        │
        ▼
Step 4a   Search the web       ──► evidence per question (web excerpts)
        │
        ▼
Step 4b   Resolve each answer  ──► per question: answer or "couldn't confirm", with quotes
        │                          (Google reviews added as evidence for experience questions)
        ▼
Step 5    Collect the results  ──► one resolution record per place   = R3 result
        │
        ▼
     Assessment (later; not built)
```

Every place is worked on in parallel, each in its own pipeline.

### Stage 0. Input (from R1 and R2)

| Data | Source | Example |
|---|---|---|
| Specific questions per category | R1 result, `specific_metrics` | `label: "weekday_afternoon_crowding"`, `question`, `value_type: "enum"`, `enum_values`, `evidence_class: "experiential"`, `verification` |
| Places per category | R2 result | `category_id: 4`, `place_id`, name, address, Google `website` |
| Google reviews per place | R2 result (`reviews`), at `operating_details` depth and above | Up to 5 reviews from Google |

Two properties of each question shape the whole run:
- **`evidence_class`.** A **factual** question (price, opening a sauna, free entry with a pass) is answered best by the place's own word. An **experiential** question (crowding, noise, friendliness) can only be answered by visitors, so the place's own site never counts and Google reviews do.
- **`verification`.** The bar the evidence must meet before an answer is committed, written per question by R1 (for example "at least two independent accounts, or one explicit statement").

Only categories with at least one specific question are worked on. A `basic_profile` category has none, so R3 never touches it.

### Steps 1-2. Plan the work (R3 STEP 1-2)

What happens: for every place R2 found in a category that has specific questions, R3 builds one work item: the place plus that category's questions.

What it produces: work items, kept inside the run. Nothing reaches the page.

Insight it carries: **how much was checked**: the number of places and questions in scope. The page can count this from the result.

### Step 3. Find the official website (R3.M1.3)

What happens:
- **Gate.** A deterministic check of Google's `website`: is it really the place's own site, or a social page, booking platform or listing site?
- **Discovery.** If the gate declines it, one web search plus an LLM choice from the results. The LLM picks from numbered candidates and can never invent a URL. No confirmed site means "none".
- This step is saved as a checkpoint (`completed_step: "discovery_batch"`). A retry does not redo it.

What it produces: `website_search_results` per place: `website_url` and `website_origin` (`google`, `discovered`, `none`). Plus audit telemetry (gate and search records).

Insight it carries: **which sources are the place's own word.** For a factual question, a quote from the official site outranks any third-party site.

**Not on the HTTP result today.** The status response returns only the resolution records, not the website verdicts. See Appendix A.

### Step 4a. Search the web (R3.M1.4 phase 1)

What happens:
- The LLM writes one web search per question (Parallel web search). For a factual question with a known website, some queries are scoped to that site, alongside broader ones.
- The app owns the budget: one search and at most one retry per question.
- Each search hit becomes an evidence item (URL, title and excerpt, `retrieved_at`), filed under the question it was searched for.
- A failed search is recorded and the run continues.

What it produces: `phase1` per place:
- `metrics_source_content.items`: every evidence item (source kind, URL, exact text, fetch time, which questions it was for).
- `metric_outcomes`: per question, whether the search came back with results (`ok`), with nothing (`empty`), failed (`failed`), or never ran (`not_searched`).

Insight it carries:
- **Where HomeScout looked** for each answer: how many sources, from which sites.
- **Why an answer is missing**: the web had nothing, versus the search didn't go through.

### Step 4b. Resolve each answer (R3.M2.2)

What happens:
- The place's Google reviews are added as one shared evidence item.
- If no question has any evidence and there are no reviews, the call is skipped: every question becomes "no evidence".
- Otherwise one structured LLM call covers all of the place's questions. For each question it:
  1. Drops evidence that doesn't clearly name this place, and evidence of the wrong kind (visitor accounts for a factual question; the official site for an experiential one).
  2. Notes what each source says: `web_value`, `reviews_value` (and `scrape_value`, always empty today).
  3. Compares them: `relation` (`agree`, `conflict`, `none`).
  4. Checks the verification bar: `verification_met`.
  5. Commits `final_value`, or nothing if the bar is not met.
  6. Flags `opinion_mixed` when the value was chosen between disagreeing sources.
  7. States the `basis`: `web`, `web_and_reviews` or `google_reviews`.
  8. Copies verbatim `evidence` quotes with their URLs, from both sides when opinions are mixed.
- A question missing from the reply gets one follow-up call. A provider failure ends that place's questions as "couldn't check".

What it produces: per place, one `AmenityResolutionRecord`:

| Field | Meaning |
|---|---|
| `kept` | Per question label: the full resolution entry (fields above) |
| `unresolved` | Per question label: a reason (`no_evidence`, `resolution_call_failed`, `resolution_body_invalid`) |
| `outcome` | `completed`, or `resolution_call_failed` / `pipeline_error` when the whole place failed |
| `phase1` | The evidence and search outcomes from step 4a (absent when the place failed) |

**Important:** a question in `kept` is not necessarily answered. An entry with `verification_met: false` has no value. It means "evidence was read, but it didn't meet the bar".

Insight it carries (this is R3's core):
- **The answer**, in the question's terms.
- **How it was decided**: which kind of source it rests on, and whether sources disagreed.
- **The receipts**: the exact sentences and where they came from.
- **Why there is no answer**, where there isn't one.

A real example (a museum, from `r3m22_run.txt`):

| Question | Answer | Basis | Mixed? | Source notes |
|---|---|---|---|---|
| Free entry with a Museumkaart? | Yes | web | no | web: "free with a Dutch Museumkaart" |
| Adult ticket price | 25 (EUR) | web | yes | web: "split: €25 (multiple official pages)…" |
| Busy on weekday afternoons? | busy | web and reviews | yes | web: "split: busy midday/early afternoon…"; reviews: "busy or crowded (4 reviews)" |

### Step 5. Collect the results (R3 STEP 5)

What happens: every place's record is collected into the run's result, in order. If every place failed at the provider, the whole run fails.

What it produces: the HTTP `result`: a list of `{category_id, place_id, value}`, where `value` is the `AmenityResolutionRecord` as JSON.

### What R3 does NOT do today (important for honest UI copy)

The full R3 design has more stages than are built. In the code today:
- **No site scraping.** Triage and phase 2 (reading the official site's pages with Firecrawl) are deferred. Evidence is web-search excerpts plus Google reviews. `scrape_value` is always empty and `basis` is never `scrape`. Copy must say "searched the web" and "read the reviews", never "read the place's website in depth" or "crawled".
- **No code checks on the answer yet.** R3.M2.3 (value matches the question's type, unit and options) and R3.M2.4 (every quote really appears in the evidence) are not built. Today's answers and quotes are the LLM's resolution, filtered for label coverage only.
- **No combined record.** R3.M2.5 (`ResolvedMetric`, `SpecificMetricsRecord`, `AmenityMetricsSet`, with `support` and `as_of`) is not built. The page reads the temporary `AmenityResolutionRecord`.
- **No selection or judgment.** R3 answers every question for every place R2 found. It never narrows to the best places or says which place fits.

So the UI must say "answered", "couldn't confirm", "what sources say", and never "verified", "matches you" or "recommended".

## 4. Which stage outputs to show the renter

The same test as R1 and R2:

1. **Explains the final output.** It helps the renter see *why* an answer is what it is.
2. **Complete on its own.** It describes one whole aspect without needing anything else.
3. **Speaks the renter's language.** Their question, plain answers, site names. Not labels, enums or field names.

### Verdict per stage

| Stage | Show? | As what | Why |
|---|---|---|---|
| Input: R1 questions | **Only the question's wording**, as the label of each answer | "Is the café quiet on weekday afternoons?" heading its answers | An answer like "Yes" or "busy" means nothing without its question. The question frames the answer; it is not the plan repeated. The rest of the plan (depth, metric type, null policy) stays on Home. |
| Input: R2 places | **Only identity**: name, and address on demand | The name on each place row or card, plus a link to that place on the R2 page | The renter must know which place an answer is about. Travel times live on the R2 page. |
| Plan the work | **Yes, as coverage counts** | "I checked 3 questions across 18 places" | Complete on its own: it states the scope of the research. Shows nothing was skipped. |
| Find the website | **Not as its own display** | At most an "Official site" tag on sources from it (needs the website URL in the result, Appendix A) | The step is plumbing. Its value to the renter is only in telling the place's own word from third-party sources. |
| Search the web | **Yes, inside each answer's evidence** | "Where I looked": the number of sources and their site names. Used to explain a missing answer. | Shows the work was done. Explains "the web had nothing on this" versus "the search didn't go through". Raw excerpts are not listed separately; quotes are shown instead. |
| Resolve each answer | **Yes, the core of the page** | The answer per question per place, the source notes when opinions differ, the basis, the verbatim quotes with links, and the reason when unanswered | This is R3's output and its most original data. It is complete per question. |
| Collect | **Yes, as the cross-place summary** | Per question, across all places: "4 of 7 gyms: yes · 1: no · 2 couldn't confirm"; or "Entry €18 to €25 across 4 museums" | No single place card can show it. It is the R3 equivalent of R2's access summary: the comparison across places for one question. A count of facts, not a ranking. |

### The two views R3's data supports

R3's data is a grid: **questions × places**. Two readings of that grid matter, and the page needs both:

- **By question** (the headline). "Which of these gyms has a powerlifting platform?" This is how the renter thinks about their brief, and it is the comparison only R3 can offer. One row per question, the places' answers side by side or summarized.
- **By place** (the drill-down). "What do I know about this gym?" A place card with every answer for that place, each with its evidence.

Both read the same result, so they can never disagree.

### What R3 borrows from R1 and R2

R3's result holds only labels and place IDs. Making it readable needs two joins. Neither shows R1 or R2 content again.

1. **From R1, by `category_id` and `label`:** the question's wording, its `unit` (to show "€25", not "25"), its `enum_values` (to show all possible options in a summary, including ones no place has), and its `evidence_class` and `verification` (detail on demand only).
2. **From R2, by `category_id` and `place_id`:** the place's name and address. A link per place to its card on the R2 page, for travel times.
3. **Order:** categories the renter asked for come first, inferred categories after, as on the R2 page.

Not on the R3 page: travel times, ratings, opening hours, R1's reasons or depth labels, the persona, and the categories that have no questions. Those categories get one quiet line ("Gyms and parks had nothing specific to check. See them on the places page.") so their absence is explained, not mysterious.

### What to keep hidden

- Snake_case labels (`adult_ticket_price`), raw enums (`web_and_reviews`, `refined_by_scrape`), `relation` as a term
- `evidence_id`, `resolution_calls`, `attempts_used`, `failed_stage`, `failed_cause`, breaker or step names
- The LLM conversation (`phase1.messages`), search queries and prompts
- Website-gate and discovery telemetry
- The full text of every search excerpt as a list. Show the quotes the answer rests on; the full source is one link away.
- `value_type` and `null_policy` as words

### Four transparency units (each complete on its own)

**A. The coverage line** (from planning and collect)
- "I checked {n} of your questions across {m} places."
- "{a} answered · {u} couldn't be confirmed."
- Not a score. A statement of the work done.

**B. The answer** (from resolution)
- The question, then the answer in its terms: "Yes", "No", "€25", "Busy".
- One line on what it rests on: "From web sources", "From web sources and Google reviews", "From Google reviews".
- Where `opinion_mixed` is true: an "Opinions differ" mark and both sides' notes: "Web: busy midday · Reviews: busy (4 reviews)". The answer is shown as leaning, not settled.
- "Checked {date}".

**C. The receipts** (from resolution evidence plus search evidence)
- Each quote verbatim, in quotation marks, with its source: site name and link, or "Google review".
- Opinions differ: quotes from both sides, labeled by side.
- "Where I looked": "{k} sources searched" with their site names.
- On demand: "What counted as proof" (the question's `verification` bar) and "Why reviews were (not) used" (from `evidence_class`).

**D. The honest gap** (from unresolved reasons and search outcomes)
- One plain reason per unanswered question. See the copy table in section 5.
- A whole place that failed: one line on the place, not one per question.

### Live progress

The status endpoint only exposes:
- `running` with no `completed_step`: setup and website discovery in progress
- `running` with `completed_step: "discovery_batch"`: websites found, questions being researched
- `finished`: everything at once, with `result`
- `failed` with `retryable` (one retry; a retry skips website discovery if it was saved)

There is **no partial data mid-run**: no per-place progress, no answers until `finished`. A run **takes minutes**, much longer than R1 or R2. So progress must set the expectation of time, and must never show fake counts or fake answers.

Suggested progress copy:
1. "Finding each place's own website" (until `completed_step: "discovery_batch"`)
2. "Researching your questions: searching the web and reading reviews" (after the checkpoint; the long step)
3. "Writing up what I found" (brief, then the result)

Plus one line under the steps: "This takes a few minutes. You can leave this page; I'll keep going." (Only if the page can resume the run on return: R2's page already keeps its run in storage, `runStorage.ts`.)

## 5. How the renter should perceive the data

### The problem, from the renter's side

The renter has a short list of things that make a place right for them, beyond what a map shows. Their real friction:
- Opening every place's website, one by one, and hunting for one fact
- Reading reviews and not knowing whether they are typical
- Finding a blog post and not knowing whether it is about this place, or still true
- Giving up and not knowing what they didn't find out

What they want to feel after R3: **"My own questions were taken seriously, someone checked properly, and I can see exactly where each answer comes from."**

### The intended perception

R3 should feel like **a friend who did the homework for you and brings back their notes**: the answer first, the receipts underneath, and candid about what they couldn't find out. Not a database, not a verdict.

| Feel | Means in the UI |
|---|---|
| **Personal** | Organized by the renter's own questions, in their words. Their asked-for categories first. |
| **Answer-first** | The answer is the first thing read, large and plain. Evidence sits underneath, one step down. |
| **Evidenced** | Every answer has a quote and a source link within one tap. Quotes are verbatim, in quotation marks. |
| **Candid** | Mixed opinions are shown as mixed, with both sides. A leaning answer looks like a leaning answer. |
| **Honest** | "Couldn't confirm" is a normal state with its own calm look, not an error. No answer is dressed up as more certain than it is. |
| **Current** | "Checked {date}" on answers. Facts change, and the page says when this one was true. |
| **Open and soft** | First-person voice ("Here's what I found out…", "I couldn't confirm this"). Short sentences. No dense tables at the top level. |
| **Factual, not judgmental** | "Yes", "Busy", "€25". Counts like "4 of 7". No "great match", no stars, no ranking, no "best for you". The assessment comes later. |

### Information layers (summary to detail)

1. **Research summary.** Heading in the R1/R2 pattern, for example "What I found *out* about your questions". The coverage line (unit A). One summary row per question: the question, and the answers across places at a glance (a count per Yes/No, per enum option, or a value range), with "couldn't confirm" counted openly.
2. **Question view.** One question, every place: a row per place with its answer, an "Opinions differ" mark where it applies, and "couldn't confirm" rows kept in the list (not hidden at the bottom).
3. **Place card.** One place, all its answers: name, then each question with its answer and basis line, and a link to the place on the R2 page.
4. **Detail on demand.** Per answer: the quotes and their sources, both sides when mixed, "Where I looked", "What counted as proof", and the check date.

### Value formatting rules

| Field | Show as |
|---|---|
| `final_value`, boolean | "Yes" / "No", next to the question so the question gives it meaning |
| `final_value`, number | The number with R1's `unit`: "€25", "24 h", "300 m". A currency code as its symbol. |
| `final_value`, enum | The option in plain words (`"very_busy"` as "Very busy") |
| `final_value`, date_time | Local date and time ("Opens 6 Jan 2027") |
| `opinion_mixed: true` | "Opinions differ" mark, plus each side's note: "Web: … · Reviews: …". The answer reads as "Leans busy". |
| `basis` | `web`: "From web sources" · `web_and_reviews`: "From web sources and Google reviews" · `google_reviews`: "From Google reviews" |
| `web_value`, `reviews_value` | Shown only when opinions differ or sources conflict, as the sides' notes. Otherwise hidden: the answer says it. |
| `evidence[].quote` | Verbatim in quotation marks. Source: the site's name (domain) linked to `url`, or "Google review" |
| `retrieved_at` (latest behind the answer) | "Checked 14 Nov" |
| Search hits for a question | "{k} sources searched", with site names on demand |
| `kept` with `verification_met: false` | "Couldn't confirm. I found mentions, but not enough to be sure." |
| `unresolved: no_evidence`, search `empty` | "Couldn't confirm. Nothing about this turned up online." |
| `unresolved: no_evidence`, search `failed` | "Couldn't confirm. The search didn't go through." |
| `unresolved: resolution_call_failed` / `resolution_body_invalid` | "Couldn't check this one. Something went wrong on my side." |
| Place `outcome` not `completed` | One line on the place: "I couldn't research this place." |
| Category with no questions | One quiet line: "Nothing specific to check here", with a link to the places page |

## 6. The product goal and how R3 proves it is working

### HomeScout's goal

HomeScout wants to remove the manual work of judging an apartment and its neighborhood. The renter describes what they want in plain language. HomeScout's agents interpret it, gather evidence, evaluate, rank and follow up, and keep the renter in the loop. Its promise is "the evidence behind each judgment is visible" (PRODUCT.md).

Neighborhood quality is built from three blocks:

| Block | Role | What the renter learns |
|---|---|---|
| R1 | Interpret the brief | "HomeScout understood what I care about, and the specific things I want to know." |
| R2 | Find the real places and their standard facts | "These are the places around this address, and this is how easy they are to reach." |
| **R3** | **Answer the renter's own questions per place** | **"This gym really has a powerlifting platform; this café is busy in the afternoon, and here's where it says so."** |

R3 is where HomeScout stops being a better map and becomes a researcher. R1 promised that the renter's specific questions would be checked. R3 is where that promise is kept, or visibly not kept. If R3 feels vague or overconfident, the renter goes back to doing the research themselves, and the whole idea of delegating the search fails.

R3 is also the first block that relies on the open web rather than Google's structured data. So it is where trust is most at risk, and where showing the evidence matters most.

### How the UI shows R3 is doing its job

| The renter should be able to see | Shown by |
|---|---|
| Every question they were promised was checked | Each R1 question appears, for every place, answered or with a reason |
| The answers speak to their request | The question's wording heads every answer |
| Answers come from real sources | A verbatim quote and a working link behind every answer |
| Experience questions were asked of visitors, fact questions of the place | The basis line, and "Why reviews were (not) used" on demand |
| Disagreement wasn't hidden | "Opinions differ" with both sides |
| Nothing was made up | "Couldn't confirm" with a plain reason; no value without a quote |
| The answers are current | "Checked {date}" |

The success test from the renter's side: **after reading R3, they can say, for each of their own questions, which places it is true for, how sure that is, and where it says so, without searching the web themselves.**

---

## Appendix A. Data facts and gaps the UI must handle

| # | Fact or gap | Impact on UI |
|---|---|---|
| 1 | The result is the **temporary** `AmenityResolutionRecord`. R3.M2.3 (conformance), R3.M2.4 (quote check) and R3.M2.5 (`ResolvedMetric`, `AmenityMetricsSet`) are not built. | Read the result through one normalizer into a page model (as R2 does with `normalizeR2Run.ts`), so the switch to `ResolvedMetric` later changes one file. |
| 2 | `kept` holds entries with `verification_met: false` and no value. | "Answered" = in `kept`, `verification_met: true`, and `final_value` not null. Everything else is "couldn't confirm". |
| 3 | `final_value` is not yet checked against the question's type, unit or options. | If a value doesn't fit (a string for a yes/no question, an option not in `enum_values`), show "couldn't confirm" rather than guess a rendering. Decide whether to wait for R3.M2.3 instead. |
| 4 | Quotes are not yet checked to appear verbatim in the evidence (R3.M2.4). | Decide whether to show quotes before R3.M2.4 ships, or show them with the source link prominent. The page should not run its own check: that belongs in the backend. |
| 5 | The result carries labels, not question text, and no unit or options. | The R3 page loads the R1 run and joins on `category_id` + `label` for `question`, `unit`, `enum_values`, `evidence_class`, `verification`. |
| 6 | The result carries `place_id`, not the place's name or address. | The R3 page loads the R2 run and joins on `category_id` + `place_id`. |
| 7 | The status response does not echo `r2_run_id` (or `r1_run_id`). | The page must keep them from the start request (as R2 keeps its inputs), or the backend adds them. |
| 8 | The website verdict (`website_url`, `website_origin`) is not on the result. | An "Official site" tag on sources needs it. Without it, show the site's domain only, and never guess which domain is official. |
| 9 | `phase1.messages` (the full LLM conversation, with prompts and every tool result) is inside each record, and every evidence excerpt is too. For 10 places × several categories this is a large payload. | Ask the backend to drop `messages` from the HTTP result. The page uses only `metrics_source_content.items` (for quote dates and "Where I looked") and `metric_outcomes`. |
| 10 | No `as_of` per answer yet. Quotes carry `url` but no `retrieved_at`. | Take the date from the matching evidence item (by URL, or the `google_reviews` item for review quotes), the latest one behind the answer. All are the same run, so the run's finish time is a safe fallback. |
| 11 | Review quotes come from a block with author, photo and time removed. | Show them as "Google review". Check Google Maps Platform attribution rules for review text shown without its author before release (not verified here). |
| 12 | Categories without specific questions are absent from the result. | Derive them from R1 (`specific_metrics` empty) for the one quiet "nothing to check" line. |
| 13 | Phase 2 (site scraping) is deferred: `scrape_value` is always null, `basis` is never `scrape`, `relation` is never `refined_by_scrape`. | Copy says "searched the web", never "read the website". Keep the formatting rule for `scrape` ready but unused. |
| 14 | Only one checkpoint (`discovery_batch`) and no partial results; runs take minutes. | Two-step progress plus a time expectation. No fake per-place progress. |
| 15 | How R3 is started is not decided: automatically after R2 finishes, or by the renter from the R2 page. | Decide the entry point and the route (for example `/research`, mirroring `/proximity`). |
| 16 | The same place can appear under two categories with different questions. | Treat each `(category, place)` as its own card. Optionally note "also under…". |
| 17 | A run where every place failed at the provider ends `failed`; partial failures end `finished` with some places failed. | A finished run can still contain whole-place failures. Show them per place (section 5), not as a page error. |
| 18 | `opinion_mixed` can be true even when the source note looks agreeing (the museum price above: "split: €25…"). | Show the sides' notes as written. Don't hide the mark because the notes look alike. |
