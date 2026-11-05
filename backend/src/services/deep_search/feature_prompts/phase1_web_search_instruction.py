"""R3.M1.4 step 1 (Phase-1 Loop) — instruction content for the metric web-search turns.

Content, not logic. One builder, `build_phase1_search_instruction(...)`, produces the system
instruction for both phase-1 turns (turn 1 and the optional retry turn): the retry turn replays the
same shared history, so the retry rule is stated here once and nothing is re-sent.

What the model is told (spec R3.M1.4 "Phase 1 instruction content"):
- emit ONE `web_search` per metric, for ALL metrics, in the first turn, each tagged `metric_label`;
- on a retry turn, re-emit a call only for metrics whose tool result `failed`;
- host scoping is per metric and computed by the app: a `factual` metric with an official site gets
  at least one `site:<host>` query ALONGSIDE off-site queries; an `experiential` metric (or any metric
  when there is no official site) gets no host-scoped query.
`scrape_target` / `review_target` are deliberately not shown in phase 1.

The worked example (a public library) is intentionally unlike any live sample-run seed.
"""

import json
from urllib.parse import urlsplit

from src.services.deep_search.feature_schemas.schemas import MetricSpec

USER_TURN_CONTENT = (
    "Make the web_search tool calls now: exactly one call per metric listed above, all of them in "
    "this turn, each tagged with its metric_label."
)

_TASK_STATEMENT = """\
You gather web evidence for a set of metrics about ONE amenity. You do not answer the metrics and
you do not write prose. Your only job is to issue web_search tool calls that would surface evidence
for each metric. The search results come back to you as tool messages."""

_SEARCH_RULES = """\
SEARCH RULES

- Make exactly ONE web_search call per metric, for EVERY metric listed below, all in this first turn.
  Never spread the metrics across turns and never skip a metric.
- Tag every call with `metric_label` set to the exact label of the metric it serves.
- Set `objective` to one short sentence naming the amenity and what the metric asks.
- Set `search_queries` to two or three concise keyword queries, 3-6 words each. Search operators
  are allowed. Use the metric's `web_target` as the search direction.
- Follow each metric's `host_scoping` instruction exactly:
  - "include_site_query": put at least one query scoped with `site:<host>` (the host given) AND at
    least one broader query that is not scoped to that site. Never scope every query to the site.
  - "no_site_query": do not scope any query to the amenity's own site."""

_TOOL_RESULT_FORMAT = """\
TOOL RESULTS

Each call is answered by one tool message whose content is JSON:
- {"status": "ok", "metric_label": ..., "hits": [{"url", "title", "text"}, ...]} — results found.
- {"status": "empty", "metric_label": ..., "hits": []} — the search finished and found nothing.
- {"status": "failed", "metric_label": ..., "failure": "..."} — the call did not complete, or was not
  run (the reason says why)."""

_RETRY_RULE = """\
RETRY RULE

After your calls are answered you may get ONE more turn. On that turn, re-emit a web_search call
ONLY for the metrics whose tool result has status "failed" (match them to your own calls by
tool_call_id). You may reword the queries. Never re-search a metric whose result was "ok" or
"empty": "empty" is a final answer, not a failure. There is no third turn."""

_WORKED_EXAMPLE = """\
WORKED EXAMPLE (illustration only; a different amenity)

Amenity: "Northgate Branch Library", official site https://www.northgatelibrary.org
Metrics:
- open_on_sundays (factual, host_scoping include_site_query, host northgatelibrary.org)
- quiet_study_space (experiential, host_scoping no_site_query)
Good calls:
- web_search{metric_label: "open_on_sundays",
  objective: "Find whether Northgate Branch Library opens on Sundays",
  search_queries: ["site:northgatelibrary.org Sunday hours", "Northgate Branch Library Sunday hours"]}
- web_search{metric_label: "quiet_study_space",
  objective: "Find visitor experiences of quiet study space at Northgate Branch Library",
  search_queries: ["Northgate Library quiet study reviews", "Northgate Branch Library noise level"]}"""


def _host_of(website_url: str | None) -> str | None:
    """The bare host of the official site (no `www.`), or None when there is no site."""
    if not website_url:
        return None
    host = urlsplit(website_url).netloc.split("@")[-1].split(":")[0].lower().rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    return host or None


def _render_metric(metric: MetricSpec, host: str | None) -> dict:
    """One metric as the model sees it, with the app-computed host-scoping instruction."""
    scoped = host is not None and metric.evidence_class == "factual"
    rendered: dict = {
        "label": metric.label,
        "question": metric.question,
        "value_type": metric.value_type,
        "unit": metric.unit,
        "enum_values": metric.enum_values,
        "evidence_class": metric.evidence_class,
        "verification": metric.verification,
        "web_target": metric.resolution_source.web_target,
        "host_scoping": "include_site_query" if scoped else "no_site_query",
    }
    if scoped:
        rendered["site_host"] = host
    return rendered


def build_phase1_search_instruction(
    name: str | None,
    address: str | None,
    taxonomy_node: str,
    website_url: str | None,
    metrics: list[MetricSpec],
) -> str:
    """Assemble the phase-1 system instruction for one amenity and all of its metrics."""
    host = _host_of(website_url)
    identity = {
        "amenity_name": name if name else "(name unavailable)",
        "amenity_type": taxonomy_node,
        "address_verbatim": address if address else "(address unavailable)",
        "official_website": website_url if website_url else "none",
    }
    rendered_metrics = [_render_metric(metric, host) for metric in metrics]
    return "\n\n".join(
        [
            _TASK_STATEMENT,
            _SEARCH_RULES,
            _TOOL_RESULT_FORMAT,
            _RETRY_RULE,
            _WORKED_EXAMPLE,
            "AMENITY\n" + json.dumps(identity, ensure_ascii=False, indent=2),
            "METRICS\n" + json.dumps(rendered_metrics, ensure_ascii=False, indent=2),
        ]
    )
