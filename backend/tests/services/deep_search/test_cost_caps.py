"""Test-cost caps: MAX_CATEGORIES / MAX_SPECIFIC_METRICS (R1 plans) and MAX_PLACES_PER_CATEGORY (R2)."""

import asyncio
import json
import logging

import pytest

from src.core.config import Settings
from src.core.logging import DEEP_SEARCH_LOGGER_NAME
from src.services.deep_search.amenity_search import AmenitySearch, create_amenity_search
from src.services.deep_search.feature_schemas.schemas import (
    DISCOVERY_MAX_RESULTS,
    PREDEFINED_METRICS_BY_DEPTH,
    CategoryMetricPlan,
    GeoPoint,
    MetricResolutionSource,
    MetricSpec,
)
from src.services.deep_search.requirement_interpretation import (
    UserRequirementsInterpretation,
    create_requirement_interpretation,
)


def _metric(label: str) -> MetricSpec:
    return MetricSpec(
        label=label,
        question=f"What is the {label}?",
        value_type="boolean",
        unit=None,
        enum_values=[],
        evidence_class="factual",
        resolution_source=MetricResolutionSource(
            web_target=f"{label} facts", scrape_target=f"{label} page"
        ),
        verification="stated explicitly",
        null_policy="null",
        band="specific_attributes",
    )


def _plan(category_id: int, metric_count: int) -> CategoryMetricPlan:
    depth = "specific_attributes" if metric_count else "basic_profile"
    return CategoryMetricPlan(
        category_id=category_id,
        taxonomy_node=f"node_{category_id}",
        depth=depth,
        predefined_metrics=list(PREDEFINED_METRICS_BY_DEPTH[depth]),
        specific_metrics=[_metric(f"m{category_id}_{i}") for i in range(metric_count)],
    )


class _StubCaller:
    """Only `providers` is read at construction; no call is made by the cap logic."""

    providers = ()

    async def aclose(self) -> None:
        pass


def _interpretation(**caps) -> UserRequirementsInterpretation:
    return UserRequirementsInterpretation(_StubCaller(), **caps)


def _settings(**caps) -> Settings:
    return Settings.model_construct(
        supabase_url="https://example.supabase.co",
        supabase_publishable_key="sb_publishable_test_key",
        google_maps_api="test-google-maps-api-key",
        openai_api_key="sk-test",
        openai_extraction_model="gpt-4o-2024-08-06",
        groq_api_key="gk-test",
        groq_extraction_model="openai/gpt-oss-120b",
        llm_provider_order="openai,groq",
        **caps,
    )


def _env_settings() -> Settings:
    """Real validation (not model_construct), with no .env file, so the caps come from the env."""
    return Settings(
        _env_file=None,
        SUPABASE_URL="https://example.supabase.co",
        SUPABASE_PUBLISHABLE_KEY="k",
        GOOGLE_MAPS_API="g",
        OPENAI_API_KEY="sk-test",
        GROQ_API_KEY="gk-test",
    )


# ---- Settings --------------------------------------------------------------------------------


def test_caps_default_to_no_limit(monkeypatch) -> None:
    for name in ("MAX_CATEGORIES", "MAX_PLACES_PER_CATEGORY", "MAX_SPECIFIC_METRICS"):
        monkeypatch.delenv(name, raising=False)
    settings = _env_settings()
    assert settings.max_categories is None
    assert settings.max_places_per_category is None
    assert settings.max_specific_metrics is None


def test_caps_read_from_env(monkeypatch) -> None:
    monkeypatch.setenv("MAX_CATEGORIES", "2")
    monkeypatch.setenv("MAX_PLACES_PER_CATEGORY", "2")
    monkeypatch.setenv("MAX_SPECIFIC_METRICS", "2")
    settings = _env_settings()
    assert (settings.max_categories, settings.max_places_per_category, settings.max_specific_metrics) == (2, 2, 2)


def test_cap_below_one_is_rejected(monkeypatch) -> None:
    monkeypatch.setenv("MAX_CATEGORIES", "0")
    with pytest.raises(ValueError):
        _env_settings()


# ---- R1 plan caps ----------------------------------------------------------------------------


@pytest.fixture
def deep_search_caplog(caplog):
    """Capture homescout.deep_search lines despite the logger's propagate=False handler."""
    deep_logger = logging.getLogger(DEEP_SEARCH_LOGGER_NAME)
    previous = deep_logger.propagate
    deep_logger.propagate = True
    with caplog.at_level(logging.INFO, logger=DEEP_SEARCH_LOGGER_NAME):
        yield caplog
    deep_logger.propagate = previous


def test_no_caps_returns_plans_unchanged() -> None:
    plans = [_plan(0, 3), _plan(1, 0), _plan(2, 4)]
    assert _interpretation()._apply_plan_caps(plans) is plans


def test_category_cap_prefers_categories_with_specific_metrics() -> None:
    # Categories 0 and 2 have no specifics; 1 and 3 do. Cap 2 must keep 1 and 3.
    plans = [_plan(0, 0), _plan(1, 3), _plan(2, 0), _plan(3, 2), _plan(4, 1)]
    kept = _interpretation(max_categories=2)._apply_plan_caps(plans)
    assert [p.category_id for p in kept] == [1, 3]


def test_category_cap_fills_with_basic_categories_in_compile_order() -> None:
    plans = [_plan(0, 0), _plan(1, 2), _plan(2, 0)]
    kept = _interpretation(max_categories=2)._apply_plan_caps(plans)
    assert [p.category_id for p in kept] == [0, 1]


def test_metric_cap_keeps_first_metrics_and_leaves_predefined() -> None:
    plans = [_plan(0, 4), _plan(1, 1)]
    kept = _interpretation(max_specific_metrics=2)._apply_plan_caps(plans)
    assert [m.label for m in kept[0].specific_metrics] == ["m0_0", "m0_1"]
    assert [m.label for m in kept[1].specific_metrics] == ["m1_0"]
    assert kept[0].predefined_metrics == plans[0].predefined_metrics
    # The input plans are not mutated.
    assert len(plans[0].specific_metrics) == 4


def test_all_three_caps_at_two(deep_search_caplog) -> None:
    caplog = deep_search_caplog
    plans = [_plan(i, 3) for i in range(7)]
    kept = _interpretation(max_categories=2, max_specific_metrics=2)._apply_plan_caps(plans)
    assert [p.category_id for p in kept] == [0, 1]
    assert all(len(p.specific_metrics) == 2 for p in kept)

    events = [json.loads(r.getMessage()) for r in caplog.records]
    caps = {e["dimension"]: (e["before"], e["after"]) for e in events if e["event"] == "metric_compilation.cap_applied"}
    assert caps == {"categories": (7, 2), "specific_metrics": (6, 4)}


def test_no_log_when_cap_removes_nothing(deep_search_caplog) -> None:
    caplog = deep_search_caplog
    plans = [_plan(0, 1)]
    _interpretation(max_categories=5, max_specific_metrics=5)._apply_plan_caps(plans)
    assert not [r for r in caplog.records if "cap_applied" in r.getMessage()]


def test_r1_factory_reads_caps_from_settings() -> None:
    interpretation = create_requirement_interpretation(
        _settings(max_categories=2, max_specific_metrics=3), llm_caller=_StubCaller()
    )
    assert interpretation._max_categories == 2
    assert interpretation._max_specific_metrics == 3


# ---- R2 place cap ----------------------------------------------------------------------------


class _RecordingPlacesClient:
    def __init__(self) -> None:
        self.routing_calls: list[dict] = []

    async def search_nearby_routing(self, **kwargs):
        self.routing_calls.append(kwargs)
        return type("R", (), {"places": [], "routing_summaries": []})()

    async def aclose(self) -> None:
        pass


class _NoRoutes:
    async def aclose(self) -> None:
        pass


@pytest.mark.parametrize(
    ("cap", "expected"),
    [(None, DISCOVERY_MAX_RESULTS), (2, 2), (DISCOVERY_MAX_RESULTS + 5, DISCOVERY_MAX_RESULTS)],
)
def test_discovery_request_uses_place_cap(cap, expected) -> None:
    search = AmenitySearch(_RecordingPlacesClient(), _NoRoutes(), max_places_per_category=cap)
    request = search.build_discovery_request(_plan(0, 2), GeoPoint(50.1, 8.6), 2.0)
    assert request.max_result_count == expected


def test_routing_re_search_uses_same_place_cap() -> None:
    client = _RecordingPlacesClient()
    search = AmenitySearch(client, _NoRoutes(), max_places_per_category=2)
    asyncio.run(search._route_one_mode(_plan(0, 2), "walk", GeoPoint(50.1, 8.6), 2.0))
    assert client.routing_calls[0]["max_result_count"] == 2


def test_r2_factory_reads_place_cap_from_settings(monkeypatch) -> None:
    import src.services.deep_search.amenity_search as module

    monkeypatch.setattr(module, "create_places_async_client", lambda s: _RecordingPlacesClient())
    monkeypatch.setattr(module, "create_routes_async_client", lambda s: _NoRoutes())
    search = create_amenity_search(_settings(max_places_per_category=2), llm_caller=_StubCaller())
    assert search._max_result_count == 2
