"""Manual, stage-by-stage run of R3.M2.2 (run the resolution turn and validate the body).

Not a test: it asserts nothing and writes nothing to disk. It seeds dummy handoff state as it stands
after R3.M1.4 phase 1 (a work item, its `PredefinedMetricsRecord` with raw Google reviews, its
`WebsiteSearchResult`, and a `MetricsSourceContent` holding web items written through `.record()`
exactly as phase 1 writes them). Discovery and phase 1 are NOT called.

Two amenities:
- A, "Elmstead Community Ice Rink" (official site): five metrics, two factual with a conflicting
  official vs third-party answer, one factual with an EMPTY bucket, two experiential (crowding from
  web + reviews; ice condition from reviews only). Five raw reviews: one rating-only (must be
  skipped), one without a rating, one with only `original_text`, all carrying author names (must be
  left out). Makes ONE live resolution call (TWO with `--force-followup`).
- B, "Brackley Lane Allotments": no evidence, no reviews → the skip rule, 0 calls.
None of this reuses the R3.M2.1 worked pairs (bouldering hall, coworking café) or its runner seed.

From `backend/` (needs OPENAI_API_KEY and/or GROQ_API_KEY; no web or Firecrawl calls):
    stage by stage:      python -m src.services.deep_search.feature_sample_runs.r3_m2_2_resolution_turn_sample_run
    exercise call 2:     ... --force-followup   (runner-only: after call 1 the first kept label is
                                                  moved back to missing; the source is untouched)
    whole workflow:      ... --pipeline         (one real `_resolve_amenity` call per amenity)
    real phase-1 data:   ... --from-sample-outputs [PATH]   (combinable with the flags above)

`--from-sample-outputs` seeds from the LATEST "R3.M1.3 + R3.M1.4 PHASE 1 - OBJECT TRACE" dump in
`deep_search/sample_outputs.py` (or PATH) instead of the dummy seed: that run's category plan
(`MetricSpec`s), its `PredefinedMetricsRecord`s, its website verdicts, and each completed amenity's
real phase-1 `MetricsSourceContent` (rebuilt through `.record()` in dumped order). The dump is
parsed as JSON, never imported. The R3.M1.4 run seeded `reviews=None`, so by default each museum
gets a runner-supplied set of DUMMY Google reviews (`_SAMPLE_OUTPUT_REVIEWS`: fictional, in the
Places API shape, with crowding accounts plus one factual claim the source rules must ignore), so
every input of the resolution turn is present. `--no-dummy-reviews` keeps the dump as it is.
Reviews of other places in that file are never attached. The review checkpoints run for any
amenity with reviews; the skip-rule checkpoint is dummy-seed only.
"""

import argparse
import asyncio
import dataclasses
import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from src.clients.llm_provider import create_structured_llm_caller
from src.clients.mcp_tools import create_mcp_tool_gateway
from src.core.config import get_settings
from src.core.logging import DEEP_SEARCH_LOGGER_NAME, configure_logging
from src.exceptions.deep_search import MetricResolutionProviderError
from src.services.deep_search.feature_prompts.resolution_instruction import (
    render_resolution_input,
)
from src.services.deep_search.feature_schemas.schemas import (
    AmenityResolutionRecord,
    GeoPoint,
    MetricResolutionSource,
    MetricSearchOutcome,
    MetricsSourceContent,
    MetricSpec,
    Phase1Result,
    PredefinedMetricsRecord,
    RouteView,
    TransitView,
    WebsiteSearchResult,
)
from src.services.deep_search.specific_metric_resolution import (
    RESOLUTION_FOLLOWUP_STAGE,
    RESOLUTION_STAGE,
    SpecificMetricResolution,
    _CircuitBreaker,
    _DiscoveryWorkItem,
    _has_resolution_evidence,
    _record_review_evidence,
    _sort_entries_by_label,
)

_RULE = "=" * 78
_RETRIEVED_AT = "2026-11-02T18:40:00+00:00"
_AUTHORS = ("Morgan Ellery", "Priya Natarajan", "Sam Okafor", "Lena Brandt", "Theo Marsh")
_CALL_EVENTS = (
    "llm_provider.attempt", "llm_provider.rejected", "llm_provider.raw_body",
    "metric_resolution.body_unparseable", "r3m1_5.breaker_opened",
)
_RESOLUTION_EVENTS = (
    "metric_resolution.validated", "metric_resolution.extra_label_dropped",
    "metric_resolution.duplicate_label", "metric_resolution.missing_label_retry",
    "metric_resolution.rejected", "metric_resolution.followup_failed",
    "metric_resolution.body_unparseable", "metric_resolution.done",
    "metric_resolution.object_finalized", "llm_provider.attempt", "llm_provider.rejected",
)


# --------------------------------------------------------------------------------------------------
# Seed (dummy post-phase-1 handoff).
# --------------------------------------------------------------------------------------------------
def _spec(label, question, value_type, evidence_class, verification, *, unit=None, enum_values=()):
    source = (
        MetricResolutionSource(web_target=f"{label} official info", scrape_target="prices page")
        if evidence_class == "factual"
        else MetricResolutionSource(
            web_target=f"{label} visitor write-ups", review_target=f"what visitors say: {question}"
        )
    )
    return MetricSpec(
        label=label,
        question=question,
        value_type=value_type,
        unit=unit,
        enum_values=list(enum_values),
        evidence_class=evidence_class,
        resolution_source=source,
        verification=verification,
        null_policy="null",
        band="specific_attributes",
    )


METRICS_A = [
    _spec("public_skate_adult_price", "What does an adult public-skate ticket cost?",
          "number_with_unit", "factual", "A stated adult price for a public session.", unit="EUR"),
    _spec("skate_hire_included", "Is skate hire included in the public-skate ticket?",
          "boolean", "factual", "An explicit statement about skate hire and the ticket."),
    _spec("locker_availability", "Are lockers available for skaters?",
          "boolean", "factual", "An explicit statement that lockers exist."),
    _spec("saturday_session_crowding", "How crowded are Saturday public sessions?",
          "enum", "experiential", "At least two independent accounts describing Saturdays.",
          enum_values=("quiet", "moderate", "busy")),
    _spec("ice_surface_condition", "What condition is the ice usually in?",
          "enum", "experiential",
          "At least three independent first-hand accounts describing the ice surface.",
          enum_values=("rough", "fair", "smooth")),
]
METRICS_B = [
    _spec("plot_waiting_list_open", "Is the plot waiting list open?", "boolean", "factual",
          "An explicit statement about the waiting list."),
]


def _raw_review(
    n, *, author=None, place="elmstead", rating=None, text=None, original=None,
    original_language="de",
) -> dict:
    """One review in the Places API shape (`sample_outputs.py`), author fields included."""
    review: dict = {
        "name": f"places/{place}/reviews/r{n}",
        "relative_publish_time_description": f"{n} months ago",
        "author_attribution": {
            "display_name": author or _AUTHORS[n - 1],
            "uri": f"https://www.google.com/maps/contrib/{place}{n}/reviews",
            "photo_uri": f"https://lh3.googleusercontent.com/a/{place}{n}",
        },
        "publish_time": f"2026-0{n}-12T10:00:00Z",
    }
    if rating is not None:
        review["rating"] = rating
    if text is not None:
        review["text"] = {"text": text, "language_code": "en"}
    if original is not None:
        review["original_text"] = {"text": original, "language_code": original_language}
    return review


def _rec(place_id, name, address, website, reviews) -> PredefinedMetricsRecord:
    return PredefinedMetricsRecord(
        category_id=7, taxonomy_node="ice_rink", depth="specific_attributes", place_id=place_id,
        name=name, category=None, address=address, website=website, google_maps_uri=None,
        coordinates=None, opening_hours=None, contact_phone=None, rating=4.1, review_volume=212,
        price_level=None, reviews=reviews, routing={}, transit=None,
    )


def _seed():
    """Fresh seed per mode: (work_item, rec, website, phase1) for A and B."""
    reviews_a = [
        _raw_review(1, rating=4.0, text=(
            "Saturday 2pm public skate was rammed, barely room to glide. Ice was smooth though."
        )),
        _raw_review(2, rating=5.0, text=(
            "Took the kids on a Saturday morning ⛸️\n\nQuiet first hour, busier after 11. "
            "Skate hire was included in our ticket which was nice."
        )),
        _raw_review(3, rating=3.0),  # rating-only: nothing to quote
        _raw_review(4, text="The ice gets choppy by the end of the evening session."),
        _raw_review(5, rating=2.0, original="Samstags total überfüllt, man steht nur herum."),
    ]
    rec_a = _rec("elmstead", "Elmstead Community Ice Rink",
                 "14 Rinkside Way, Elmstead 60412", "https://elmsteadicerink.example/", reviews_a)
    store_a = MetricsSourceContent()
    official = ("https://elmsteadicerink.example/prices",
                "Prices | Elmstead Community Ice Rink\n"
                "Public skate sessions: adults €9.50, children €6. Skate hire €3 extra per session.")
    listing = ("https://citydaysout.example/elmstead-ice-rink",
               "Elmstead Community Ice Rink – City Days Out\n"
               "Adult entry is around €8 and skates are included.")
    for url, text in (official, listing):
        for label in ("public_skate_adult_price", "skate_hire_included"):
            store_a.record("web", url, text, _RETRIEVED_AT, label)
    store_a.record("web", "https://weekendwithkids.example/ice-rinks-ranked",
                   "Ice rinks ranked\nElmstead Community Ice Rink on a Saturday afternoon is "
                   "packed; arrive at opening if you want space.", _RETRIEVED_AT,
                   "saturday_session_crowding")
    store_a.record("web", "https://localskatenotes.example/elmstead",
                   "Skating at Elmstead\nSaturdays at the Elmstead rink are busy but manageable "
                   "before noon.", _RETRIEVED_AT, "saturday_session_crowding")
    a = (
        _DiscoveryWorkItem(7, "elmstead", "ice_rink", "specific_attributes", METRICS_A),
        rec_a,
        WebsiteSearchResult("https://elmsteadicerink.example/", "google"),
        _phase1(store_a),
    )
    rec_b = _rec("brackley", "Brackley Lane Allotments", "Brackley Lane, Elmstead 60419", None, None)
    b = (
        _DiscoveryWorkItem(7, "brackley", "allotment", "specific_attributes", METRICS_B),
        rec_b,
        WebsiteSearchResult(None, "none"),
        _phase1(MetricsSourceContent()),
    )
    return [a, b]


def _phase1(store: MetricsSourceContent) -> Phase1Result:
    return Phase1Result(messages=[], metrics_source_content=store, metric_outcomes={},
                        uncovered_labels=(), turns_run=1)


# --------------------------------------------------------------------------------------------------
# Seed from a real R3.M1.4 run (`--from-sample-outputs`).
# --------------------------------------------------------------------------------------------------
DEFAULT_SAMPLE_OUTPUTS = Path(__file__).resolve().parents[1] / "sample_outputs.py"
# The section header the R3.M1.4 runner writes before its JSON dump (the latest one is used).
_PHASE1_DUMP_MARKER = "R3.M1.3 + R3.M1.4 PHASE 1 - OBJECT TRACE"


def _load_phase1_dump(path: Path) -> dict:
    """Parse the latest R3.M1.4 object-trace dump. It is a JSON literal, so it is never imported."""
    text = Path(path).read_text(encoding="utf-8")
    at = text.rfind(_PHASE1_DUMP_MARKER)
    if at < 0:
        raise SystemExit(f"no '{_PHASE1_DUMP_MARKER}' section in {path}")
    dump, _end = json.JSONDecoder().raw_decode(text, text.index("{", at))
    return dump


def _metric_from_dump(data: dict) -> MetricSpec:
    return MetricSpec(
        **{
            **data,
            "enum_values": list(data["enum_values"]),
            "resolution_source": MetricResolutionSource(**data["resolution_source"]),
        }
    )


def _record_from_dump(data: dict) -> PredefinedMetricsRecord:
    fields = dict(data)
    if isinstance(fields.get("coordinates"), dict):
        fields["coordinates"] = GeoPoint(**fields["coordinates"])
    fields["routing"] = {
        mode: RouteView(**leg) if isinstance(leg, dict) else None
        for mode, leg in (fields.get("routing") or {}).items()
    }
    if isinstance(fields.get("transit"), dict):
        fields["transit"] = TransitView(**fields["transit"])
    return PredefinedMetricsRecord(**fields)


def _phase1_from_dump(data: dict) -> Phase1Result:
    """Rebuild the phase-1 handoff. The store is refilled through `.record()` in the dumped item
    order (new `evidence_id`s; ids and timestamps are never shown to the LLM)."""
    store = MetricsSourceContent()
    for item in data["metrics_source_content"]["items"]:
        for label in sorted(item["metric_labels"]) or [None]:
            store.record(
                item["source_kind"], item["url"], item["shaped_text"], item["retrieved_at"], label
            )
    return Phase1Result(
        messages=data["messages"],
        metrics_source_content=store,
        metric_outcomes={
            label: MetricSearchOutcome(**row) for label, row in data["metric_outcomes"].items()
        },
        uncovered_labels=tuple(data["uncovered_labels"]),
        turns_run=data["turns_run"],
    )


# Runner-supplied DUMMY Google reviews for the two museums of the dumped R3.M1.4 run, which seeded
# `reviews=None`. Fictional people and wording, in the Places API shape. Each set exercises every
# reviews path: crowding accounts for the experiential metric (Rijksmuseum: agree with the web,
# busy; Van Loon: split, to exercise `opinion_mixed`), one FACTUAL claim the source rules must
# ignore (Museumkaart entry / an adult price), a rating-only review (skipped, not numbered), a
# review with no rating, a Dutch review carried only in `original_text`, and a blank line / emoji.
_SAMPLE_OUTPUT_REVIEWS = {
    "rijks": [
        _raw_review(1, place="rijks", author="Joris Verbeek", rating=5.0, text=(
            "Went on a Tuesday afternoon around 2pm and the Gallery of Honour was packed, you "
            "queue just to get a glimpse of The Night Watch. Still worth every minute."
        )),
        _raw_review(2, place="rijks", author="Hannah Okoye", rating=4.0, text=(
            "Weekday afternoons are busy, school groups everywhere until about 3pm. The upper "
            "floors were calmer.\n\nTip: the Cuypers library is stunning and almost empty 📚"
        )),
        _raw_review(3, place="rijks", author="Marco Bellini", rating=3.0),  # rating-only
        _raw_review(4, place="rijks", author="Sofie Lindqvist", text=(
            "Entry was free with our Museumkaart, we just scanned it at the gate. Thursday "
            "afternoon crowds were heavy around the Vermeers."
        )),
        _raw_review(5, place="rijks", author="Pieter de Graaf", rating=4.0, original_language="nl",
                    original="Woensdagmiddag erg druk bij De Nachtwacht, maar in de vleugel met "
                             "Aziatische kunst was het rustig."),
    ],
    "vanloon": [
        _raw_review(1, place="vanloon", author="Claire Dumont", rating=5.0, text=(
            "Visited on a Monday afternoon and had most rooms to ourselves. The garden and the "
            "coach house were completely quiet."
        )),
        _raw_review(2, place="vanloon", author="Tomasz Nowak", rating=5.0, text=(
            "A calm canal-house museum, even on a weekday afternoon in July. Nice contrast to "
            "the crowds at the big museums 🌷"
        )),
        _raw_review(3, place="vanloon", author="Rachel Stein", rating=2.0, text=(
            "Came on a Wednesday afternoon and a large tour group filled the small rooms, so it "
            "felt cramped for half an hour.\n\nThe adult ticket was €17.50, which felt steep "
            "for the size of the house."
        )),
        _raw_review(4, place="vanloon", author="Ahmed Rahimi", rating=4.0),  # rating-only
        _raw_review(5, place="vanloon", author="Femke Jansen", original_language="nl",
                    original="Doordeweeks 's middags heerlijk rustig, je loopt er zonder te "
                             "wachten in."),
    ],
}


def _seed_from_sample_outputs(path: Path, *, dummy_reviews: bool = True) -> list:
    """(work_item, rec, website, phase1) per amenity whose phase 1 completed in the dumped run.

    With `dummy_reviews`, a record the dump left without reviews gets its runner-supplied set from
    `_SAMPLE_OUTPUT_REVIEWS` (by place_id), so Step 1 and the reviews section are exercised too.
    """
    dump = _load_phase1_dump(path)
    inputs, final = dump["inputs"], dump["final_state"]
    plans = {plan["category_id"]: plan for plan in inputs["category_metric_plans"]}
    # The R3.M1.4 run wrote `phase1_results`; a later dump of this pipeline names it
    # `resolution_results`. Either carries the per-amenity `phase1` object.
    pipeline_store = final.get("phase1_results") or final.get("resolution_results") or {}
    amenities = []
    for key_text, record in pipeline_store.items():
        if record.get("phase1") is None:
            print(f"  (skipping {key_text}: outcome={record.get('outcome')}, no phase-1 evidence)")
            continue
        category_text, place_id = key_text.split("/", 1)
        plan = plans[int(category_text)]
        work_item = _DiscoveryWorkItem(
            int(category_text), place_id, plan["taxonomy_node"], plan["depth"],
            [_metric_from_dump(m) for m in plan["specific_metrics"]],
        )
        rec = _record_from_dump(inputs["predefined_records"][category_text][place_id])
        if dummy_reviews and not rec.reviews and place_id in _SAMPLE_OUTPUT_REVIEWS:
            rec = dataclasses.replace(rec, reviews=_SAMPLE_OUTPUT_REVIEWS[place_id])
            print(f"  ({key_text}: dump has no reviews; attached "
                  f"{len(rec.reviews)} runner-supplied DUMMY reviews)")
        amenities.append((
            work_item,
            rec,
            WebsiteSearchResult(**final["website_search_results"][key_text]),
            _phase1_from_dump(record["phase1"]),
        ))
    if not amenities:
        raise SystemExit(f"no amenity with completed phase-1 evidence in {path}")
    keys = [f"{w.category_id}/{w.place_id}" for w, *_rest in amenities]
    print(f"  seeded from {path} (run started {dump['run']['started_at']}): {keys}")
    return amenities


# --------------------------------------------------------------------------------------------------
# Log collection and printing.
# --------------------------------------------------------------------------------------------------
class _RecordCollector(logging.Handler):
    """Keeps the structured records so this script can print provider attempts and R3.M2.2 lines."""

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.records: list[dict] = []
        self._cursor = 0

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.records.append(json.loads(record.getMessage()))
        except json.JSONDecodeError:
            pass

    def new_events(self, *names: str) -> list[dict]:
        """Events since the last call (all of them when no names are given)."""
        fresh = self.records[self._cursor:]
        self._cursor = len(self.records)
        return [r for r in fresh if not names or r.get("event") in names]


def _section(title: str) -> None:
    print(f"\n{_RULE}\n{title}\n{_RULE}")


def _print_rendered_buckets(event: dict) -> None:
    """The `metric_resolution.input_rendered` log line, one block per metric bucket."""
    print(f"  [{event['event']}] stage={event['stage']} user_turn_chars={event['user_turn_chars']}"
          f" amenity={json.dumps(event['amenity'], ensure_ascii=False)}")
    for bucket in event["buckets"]:
        print(f"    bucket {bucket['label']} ({bucket['evidence_class']}): "
              f"{bucket['evidence_items']} item(s)")
        for n, item in enumerate(bucket["evidence"], start=1):
            print(f"      [{n}] {item['source']} {item['url']}")
            for line in item["text"].splitlines():
                print(f"          | {line}")
    reviews = event["google_reviews"]
    print(f"    google_reviews: {'null' if reviews is None else ''}")
    for line in (reviews or {}).get("text", "").splitlines():
        print(f"      | {line}")


def _print_events(events: list[dict]) -> None:
    for event in events:
        if event.get("event") == "metric_resolution.input_rendered":
            _print_rendered_buckets(event)
            continue
        if event.get("event") == "llm_provider.raw_body":
            print(f"  [{event['event']}] stage={event['stage']} provider={event['provider']}")
            print("  raw body:")
            for line in json.dumps(event["body"], indent=2, ensure_ascii=False).splitlines():
                print(f"    {line}")
            continue
        fields = {k: v for k, v in event.items() if k not in ("event", "timestamp", "run_id")}
        print(f"  [{event.get('event')}] {json.dumps(fields, ensure_ascii=False)}")


def _print_seed(work_item, rec, website, store) -> None:
    print(f"  amenity: {rec.name!r}  address={rec.address!r}  website_url={website.website_url!r}")
    print(f"  raw reviews: {len(rec.reviews or [])}")
    for metric in work_item.specific_metrics:
        items = store.items_for(metric.label)
        print(f"  - {metric.label} ({metric.evidence_class}, {metric.value_type}"
              f"{', ' + metric.unit if metric.unit else ''}): {len(items)} evidence item(s)")
        for item in items:
            print(f"      {item.url}  | {item.shaped_text.splitlines()[-1][:80]!r}")


def _print_sort(sort) -> None:
    print(f"  kept:      {list(sort.kept)}")
    print(f"  extra:     {list(sort.extra)}")
    print(f"  duplicate: {list(sort.duplicate)}")
    print(f"  missing:   {list(sort.missing)}")


def _print_record(record: AmenityResolutionRecord) -> None:
    print(f"  ({record.category_id}, {record.place_id}): outcome={record.outcome} "
          f"resolution_calls={record.resolution_calls} failed_stage={record.failed_stage} "
          f"failed_cause={record.failed_cause}")
    for label, entry in record.kept.items():
        print(f"    kept {label}: final_value={entry.final_value!r} "
              f"verification_met={entry.verification_met} basis={entry.basis} "
              f"relation={entry.relation} opinion_mixed={entry.opinion_mixed}")
        print(f"         web_value={entry.web_value!r} reviews_value={entry.reviews_value!r}")
        for quote in entry.evidence:
            print(f"         quote[{quote.source}] {quote.url}: {quote.quote!r}")
    for label, reason in record.unresolved.items():
        print(f"    unresolved {label}: {reason}")


def _reviews_text(store: MetricsSourceContent) -> str | None:
    texts = [i.shaped_text for i in store.items if i.source_kind == "google_reviews"]
    return texts[0] if texts else None


def _normalize(text: str) -> str:
    """Whitespace collapse + case folding (the R3.M2.4 approach-1 normalization)."""
    return " ".join(text.split()).casefold()


def _quotable_reviews(reviews) -> int:
    """How many raw reviews carry text (counted here independently of the service's shaping)."""
    count = 0
    for review in reviews or ():
        texts = [(review.get(field) or {}).get("text") for field in ("text", "original_text")]
        if any(isinstance(text, str) and text.strip() for text in texts):
            count += 1
    return count


def _review_checkpoints(key, rec, store, record, metrics, report) -> None:
    """Reviews-item and reviews-use checks, for any amenity whose record carries reviews."""
    items = [i for i in store.items if i.source_kind == "google_reviews"]
    text = items[0].shaped_text if items else ""
    report(len(items) == 1 and items[0].metric_labels == set() and items[0].url is None,
           f"{key}: one google_reviews item, url None, no metric labels")
    authors = [(r.get("author_attribution") or {}).get("display_name") for r in rec.reviews]
    report(bool(text) and not any(name and name in text for name in authors),
           f"{key}: reviews text carries no author names")
    numbers = [int(n) for n in re.findall(r"^Review (\d+)(?: \(★\d+\))?:", text, flags=re.M)]
    expected = _quotable_reviews(rec.reviews)
    report(numbers == list(range(1, expected + 1)),
           f"{key}: rating-only reviews skipped, numbering contiguous "
           f"({len(numbers)} of {len(rec.reviews)} written, expected {expected})")
    factual = {m.label for m in metrics if m.evidence_class == "factual"}
    report(not any(q.source == "google_reviews"
                   for label in factual if label in record.kept
                   for q in record.kept[label].evidence),
           f"{key}: no factual entry cites a google_reviews quote")
    paired = [e for e in record.kept.values() if e.basis == "web_and_reviews"]
    report(all(e.relation in ("agree", "conflict") for e in paired),
           f"{key}: web_and_reviews values pair with agree/conflict ({len(paired)} such)")
    used = [label for label, e in record.kept.items() if e.reviews_value is not None]
    print(f"         (info) entries with a reviews_value: {used}")


def _checkpoints(amenities, records, *, dummy_seed: bool) -> None:
    _section("CHECKPOINTS (reported, not enforced)")

    def report(ok: bool, text: str) -> None:
        print(f"  [{'PASS' if ok else 'MISS'}] {text}")

    for work_item, rec, _website, phase1 in amenities:
        key = (work_item.category_id, work_item.place_id)
        record = records[key]
        store = phase1.metrics_source_content
        metrics = work_item.specific_metrics
        labels = {m.label for m in metrics}
        report(not set(record.kept) & set(record.unresolved)
               and set(record.kept) | set(record.unresolved) == labels,
               f"{key}: every label is in exactly one of kept / unresolved")
        report(record.resolution_calls <= 2,
               f"{key}: at most 2 resolution calls ({record.resolution_calls})")
        factual = {m.label for m in metrics if m.evidence_class == "factual"}
        report(all(record.kept[l].reviews_value is None for l in factual if l in record.kept),
               f"{key}: factual entries have reviews_value null")
        reviews = _reviews_text(store)
        misses = 0
        for label, entry in record.kept.items():
            bucket = [_normalize(item.shaped_text) for item in store.items_for(label)]
            for quote in entry.evidence:
                needle = _normalize(quote.quote)
                if quote.source == "google_reviews":
                    found = reviews is not None and needle in _normalize(reviews)
                else:
                    found = bool(needle) and any(needle in text for text in bucket)
                if not found:
                    misses += 1
                    print(f"         not found: {label} [{quote.source}] {quote.quote[:90]!r}")
        report(misses == 0, f"{key}: every quote is in that metric's bucket or the reviews text "
               "(normalized, as R3.M2.4 approach 1)")
        if rec.reviews:
            _review_checkpoints(key, rec, store, record, metrics, report)

    if not dummy_seed:
        return
    b = records.get((7, "brackley"))
    report(b is not None and b.resolution_calls == 0
           and set(b.unresolved.values()) == {"no_evidence"},
           "B: skip rule → 0 calls, every metric no_evidence")


# --------------------------------------------------------------------------------------------------
# Modes.
# --------------------------------------------------------------------------------------------------
async def _walk_amenity(service, collector, amenity, breaker, run_id, force_followup: bool):
    """R3.M2.2 steps 1→5 for one amenity, one titled section per stage."""
    work_item, rec, website, phase1 = amenity
    store = phase1.metrics_source_content
    key = (work_item.category_id, work_item.place_id)
    metrics = work_item.specific_metrics
    tag = f"{key[0]}/{key[1]} {rec.name!r}"

    _section(f"STEP 1: _record_review_evidence — {tag}")
    written = _record_review_evidence(rec, store, datetime.now(timezone.utc).isoformat())
    item = next((i for i in store.items if i.source_kind == "google_reviews"), None)
    print(f"  reviews written: {written}")
    if item is not None:
        print(f"  item: source_kind={item.source_kind} url={item.url!r} "
              f"metric_labels={item.metric_labels} retrieved_at={item.retrieved_at}")
        for line in item.shaped_text.splitlines():
            print(f"    | {line}")

    _section(f"STEP 2: skip rule — {tag}")
    has_evidence = _has_resolution_evidence(metrics, store)
    print(f"  has metric evidence or reviews: {has_evidence}")
    if not has_evidence:
        record = AmenityResolutionRecord(
            category_id=key[0], place_id=key[1], outcome="completed", kept={},
            unresolved={m.label: "no_evidence" for m in metrics}, phase1=phase1,
            resolution_calls=0,
        )
        print("  skip → every metric no_evidence, 0 calls")
        _print_record(record)
        return record

    _section(f"STEP 3: call 1 ({RESOLUTION_STAGE}) — rendered user turn — {tag}")
    print(render_resolution_input(rec.name, rec.address, website.website_url, metrics, store))
    collector.new_events()
    result = await service._run_resolution_call(
        metrics, rec, website, store, RESOLUTION_STAGE, breaker, key, run_id
    )
    _section(f"STEP 3: provider attempts + raw body — {tag}")
    _print_events(collector.new_events(*_CALL_EVENTS))

    _section(f"STEP 4a/b: parse + sort by label — {tag}")
    first = _sort_entries_by_label(result, [m.label for m in metrics])
    service._log_label_sort(first, len(metrics), RESOLUTION_STAGE, key, run_id)
    _print_sort(first)
    _print_events(collector.new_events(*_RESOLUTION_EVENTS))
    kept = dict(first.kept)
    missing = list(first.missing)
    calls = 1
    if force_followup and kept:
        label = next(iter(kept))
        del kept[label]
        missing = [m.label for m in metrics if m.label in set(missing) | {label}]
        print(f"  --force-followup: moved {label!r} back to missing (runner-only simulation)")

    unresolved: dict[str, str] = {}
    if missing:
        _section(f"STEP 4c: follow-up ({RESOLUTION_FOLLOWUP_STAGE}) for {missing} — {tag}")
        missing_metrics = [m for m in metrics if m.label in set(missing)]
        if not _has_resolution_evidence(missing_metrics, store):
            print("  skip rule on the missing metrics: no evidence and no reviews → no_evidence")
            unresolved.update({label: "no_evidence" for label in missing})
        else:
            print(render_resolution_input(
                rec.name, rec.address, website.website_url, missing_metrics, store
            ))
            try:
                followup = await service._run_resolution_call(
                    missing_metrics, rec, website, store, RESOLUTION_FOLLOWUP_STAGE, breaker,
                    key, run_id,
                )
                calls += 1
            except MetricResolutionProviderError as exc:
                if exc.cause != "circuit_open":
                    calls += 1
                print(f"  follow-up failed: stage={exc.stage} cause={exc.cause} → "
                      f"{missing} resolution_call_failed; kept entries stand")
                unresolved.update({label: "resolution_call_failed" for label in missing})
            else:
                _print_events(collector.new_events(*_CALL_EVENTS))
                second = _sort_entries_by_label(followup, missing)
                service._log_label_sort(second, len(missing), RESOLUTION_FOLLOWUP_STAGE, key, run_id)
                _print_sort(second)
                kept.update(second.kept)
                unresolved.update({label: "resolution_body_invalid" for label in second.missing})
                _print_events(collector.new_events(*_RESOLUTION_EVENTS))
    else:
        _section(f"STEP 4c: no missing labels → no follow-up call — {tag}")

    _section(f"STEP 5: AmenityResolutionRecord (assembled from the stage outputs) — {tag}")
    record = AmenityResolutionRecord(
        category_id=key[0], place_id=key[1], outcome="completed",
        kept={m.label: kept[m.label] for m in metrics if m.label in kept},
        unresolved={m.label: unresolved[m.label] for m in metrics if m.label in unresolved},
        phase1=phase1, resolution_calls=calls,
    )
    _print_record(record)
    return record


async def _run_stages(service, collector, amenities, force_followup: bool, dummy_seed: bool):
    breaker = _CircuitBreaker(threshold=3)
    run_id = uuid4().hex
    _section("SEED STATE (as after R3.M1.4 phase 1)")
    for work_item, rec, website, phase1 in amenities:
        _print_seed(work_item, rec, website, phase1.metrics_source_content)
    records = {}
    for amenity in amenities:
        key = (amenity[0].category_id, amenity[0].place_id)
        records[key] = await _walk_amenity(
            service, collector, amenity, breaker, run_id, force_followup
        )
    print(f"\n  breaker: counter={breaker.counter} open={breaker.open}")
    _checkpoints(amenities, records, dummy_seed=dummy_seed)


async def _run_pipeline(service, collector, amenities, dummy_seed: bool) -> None:
    breaker = _CircuitBreaker(threshold=3)
    run_id = uuid4().hex
    records = {}
    for work_item, rec, website, phase1 in amenities:
        key = (work_item.category_id, work_item.place_id)
        _section(f"PIPELINE: _resolve_amenity({key}) — {rec.name!r}")
        _print_seed(work_item, rec, website, phase1.metrics_source_content)
        records[key] = await service._resolve_amenity(work_item, rec, website, phase1, breaker, run_id)
        _print_events(collector.new_events(
            *_RESOLUTION_EVENTS, "metric_resolution.input_rendered", "llm_provider.raw_body"
        ))
        _print_record(records[key])
    print(f"\n  breaker: counter={breaker.counter} open={breaker.open}")
    _checkpoints(amenities, records, dummy_seed=dummy_seed)


async def run(
    force_followup: bool, pipeline: bool, sample_path: Path | None, dummy_reviews: bool = True
) -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    service_logger = logging.getLogger(DEEP_SEARCH_LOGGER_NAME)
    service_logger.setLevel(logging.DEBUG)
    collector = _RecordCollector()
    service_logger.addHandler(collector)

    amenities = (
        _seed() if sample_path is None
        else _seed_from_sample_outputs(sample_path, dummy_reviews=dummy_reviews)
    )
    dummy_seed = sample_path is None
    caller = create_structured_llm_caller(settings)
    # The gateway is constructed (no I/O) but never opened: R3.M2.2 makes no tool calls.
    service = SpecificMetricResolution(
        tool_gateway=create_mcp_tool_gateway(settings), llm_caller=caller, owns_caller=True
    )
    try:
        if pipeline:
            await _run_pipeline(service, collector, amenities, dummy_seed)
        else:
            await _run_stages(service, collector, amenities, force_followup, dummy_seed)
    except MetricResolutionProviderError:
        # The attempt trail (incl. the SDK detail) is the only place the real cause is shown.
        _section("PROVIDER ATTEMPTS (before the failure)")
        _print_events(collector.new_events(*_CALL_EVENTS, *_RESOLUTION_EVENTS))
        raise
    finally:
        await caller.aclose()


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(
        description="Run R3.M2.2 (resolution turn + body validation) against a real LLM call."
    )
    parser.add_argument("--force-followup", action="store_true",
                        help="after call 1, move the first kept label back to missing (stage mode)")
    parser.add_argument("--pipeline", action="store_true",
                        help="run the whole `_resolve_amenity` workflow once per amenity")
    parser.add_argument("--from-sample-outputs", nargs="?", const=str(DEFAULT_SAMPLE_OUTPUTS),
                        default=None, metavar="PATH",
                        help="seed from the latest R3.M1.4 run dump instead of the dummy seed "
                             "(default PATH: deep_search/sample_outputs.py)")
    parser.add_argument("--no-dummy-reviews", action="store_true",
                        help="with --from-sample-outputs: keep the dump's records as they are "
                             "(no runner-supplied reviews)")
    args = parser.parse_args()
    sample_path = Path(args.from_sample_outputs) if args.from_sample_outputs else None
    try:
        asyncio.run(run(args.force_followup, args.pipeline, sample_path,
                        dummy_reviews=not args.no_dummy_reviews))
    except MetricResolutionProviderError as exc:
        _section("FAILED")
        print(f"exception: {type(exc).__name__}")
        print(f"stage:     {exc.stage}")
        print(f"cause:     {exc.cause}")
        print(f"message:   {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
