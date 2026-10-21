"""R3.M1.3 Stage 0 — the official-URL gate (deterministic, no LLM, no search).

`official_url_gate(website, name)` decides whether Google's `PredefinedMetricsRecord.website` can
be trusted as the amenity's own first-party official site *by rule*, before any discovery search.
It returns `official` (trust the Google URL) or `discovery` (fall through to the Stage-1 search).
Specified in `feature_context/R3_Specific_Metric_Resolution_spec.md` (R3.M1.3, "Google-provided URL
handling") and `feature_context/R3_M1_Traceflow.md` (Part 3a).

**Core idea.** Match the brand name against the **SLD label only** (the label left of the public
suffix), ignoring subdomain and suffix. That one choice decides the expensive direction by rule:
`brand.evil.com` → `discovery` (SLD `evil`), while a buried official site
`clinic.reseller.greenvalleydental.co.uk` → `official` (SLD `greenvalleydental`).

**Strict by asymmetry.** A false `official` skips discovery and feeds a wrong site to the crawl
(expensive, uncorrectable); a false `discovery` is cheap and usually re-finds the URL. So the rule
is precise on the OFFICIAL direction and anything ambiguous falls to `discovery`.

**Offline, pinned PSL.** One module-level `TLDExtract(suffix_list_urls=[], cache_dir=None,
fallback_to_snapshot=True, include_psl_private_domains=True)`: it never fetches the Public Suffix
List at runtime and reads the snapshot bundled with the pinned `tldextract` (so the pin *is* the
vendored snapshot; refreshing it is bumping the pin — a deliberate maintenance task). It is warmed
once at import so the first real gate call is not the one that parses the snapshot.
`include_psl_private_domains=True` resolves brand-owned platform subdomains (`brand.wixsite.com`,
`brand.github.io`) to the brand's own SLD → `official`, while foreign apex domains
(`brand.evil.com` → SLD `evil`) are still rejected.

The gate is pure and deterministic. Its per-item decision is persisted to
`state.official_gate_results` (as an `OfficialGateRecord`) for offline audit, so it does not log.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit

import tldextract

# The brand/SLD match needs both operands at least this long, so a short generic SLD does not
# produce a spurious substring hit (e.g. "inn" in "innovation").
MIN_LEN = 5

# Exact-set membership on `registered_domain` (no endswith / substring). A fast-reject
# optimization only — step 4 (SLD match) already rejects foreign SLDs by rule, so this list is not
# load-bearing for correctness; it just skips the name check for well-known non-official hosts.
DENYLIST: frozenset[str] = frozenset(
    {
        # directories / aggregators / review
        "yelp.com",
        "tripadvisor.com",
        "yellowpages.com",
        "business.site",
        "booking.com",
        "opentable.com",
        "zomato.com",
        "doordash.com",
        "ubereats.com",
        # social / video
        "facebook.com",
        "instagram.com",
        "twitter.com",
        "x.com",
        "linkedin.com",
        "youtube.com",
        "tiktok.com",
        "pinterest.com",
        # maps / search platforms
        "google.com",
        "goo.gl",
        "bing.com",
        "apple.com",
    }
)

# One module-level extractor: offline (no runtime PSL fetch), reads the snapshot bundled with the
# pinned tldextract, and resolves brand-owned platform subdomains to the brand's own SLD.
_EXTRACTOR = tldextract.TLDExtract(
    suffix_list_urls=[],
    cache_dir=None,
    fallback_to_snapshot=True,
    include_psl_private_domains=True,
)
# Warm the snapshot once at import so the first gate call in the pre-pass is not the one that pays
# the one-time snapshot parse.
_EXTRACTOR("example.com")

_KEEP_RE = re.compile(r"[a-z0-9]+")

GateVerdict = Literal["official", "discovery"]
GateReasonCode = Literal[
    "presence_empty",
    "no_registrable_domain",
    "denylist_hit",
    "sld_match",
    "sld_no_match",
]


@dataclass(frozen=True)
class GateOutcome:
    """The gate's verdict plus the derived operands the pre-pass copies into `OfficialGateRecord`.

    The raw `name`/`website` are known to the caller (the work item's record) and are not carried
    here. Operand fields are populated only as far as the gate computed them before it exited
    (so they are `None` for an early-exit `reason_code`).
    """

    verdict: GateVerdict
    reason_code: GateReasonCode
    host: str | None = None
    registered_domain: str | None = None
    sld: str | None = None
    suffix: str | None = None
    compact_name: str | None = None
    compact_sld: str | None = None


def compact(value: str) -> str:
    """NFKD → drop combining marks → casefold → keep `[a-z0-9]`. "Café México" → "cafemexico".

    NFKD (not NFKC) decomposes accented letters so the mark can be dropped and the base letter
    kept, rather than deleting the whole character.
    """
    decomposed = unicodedata.normalize("NFKD", value)
    without_marks = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return "".join(_KEEP_RE.findall(without_marks.casefold()))


def _match(compact_name: str, compact_sld: str) -> bool:
    """Both operands `>= MIN_LEN` and one is a substring of the other (bidirectional)."""
    if len(compact_name) < MIN_LEN or len(compact_sld) < MIN_LEN:
        return False
    return compact_name in compact_sld or compact_sld in compact_name


def _host(website: str) -> str:
    """`urlsplit(website).netloc` → lower, strip userinfo and port, `rstrip('.')`.

    An IPv6 literal (`[::1]`) is left bracketed so `tldextract` yields no suffix → `discovery`.
    """
    netloc = urlsplit(website).netloc.strip().lower()
    if "@" in netloc:
        netloc = netloc.rsplit("@", 1)[1]
    if not netloc.startswith("["):
        netloc = netloc.split(":", 1)[0]
    return netloc.rstrip(".")


def official_url_gate(website: str | None, name: str | None) -> GateOutcome:
    """Decide `official` vs `discovery` for one Google `websiteUri` by rule. Pure and total.

    Ordered steps (order matters): presence → host → registrable-domain extract → denylist → SLD
    match → else. The first step that decides returns immediately.
    """
    # 0 PRESENCE — no usable candidate URL to trust.
    if not website or not website.strip():
        return GateOutcome("discovery", "presence_empty")

    # 1 HOST + 2 EXTRACT — need a real registrable domain (SLD + public suffix).
    host = _host(website)
    extracted = _EXTRACTOR(host)
    sld = extracted.domain or None
    suffix = extracted.suffix or None
    if sld is None or suffix is None:
        # IP, localhost, bare host, or an unparsable netloc — nothing to brand-match against.
        return GateOutcome("discovery", "no_registrable_domain", host=host or None)
    registered_domain = f"{sld}.{suffix}"

    # 3 DENYLIST — fast-reject a well-known non-official host (skips the name check).
    if registered_domain in DENYLIST:
        return GateOutcome(
            "discovery",
            "denylist_hit",
            host=host,
            registered_domain=registered_domain,
            sld=sld,
            suffix=suffix,
        )

    # 4 SLD MATCH — the one OFFICIAL path; brand vs the SLD label only.
    compact_name = compact(name) if name else ""
    compact_sld = compact(sld)
    verdict: GateVerdict = "official" if _match(compact_name, compact_sld) else "discovery"
    reason_code: GateReasonCode = "sld_match" if verdict == "official" else "sld_no_match"
    return GateOutcome(
        verdict,
        reason_code,
        host=host,
        registered_domain=registered_domain,
        sld=sld,
        suffix=suffix,
        compact_name=compact_name or None,
        compact_sld=compact_sld,
    )
