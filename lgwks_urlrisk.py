"""
lgwks_urlrisk — G3 scope curator (Issue #7, ADR-001 §5, constitution L9).

The ML/threat layer the Director asked for: it does NOT just blocklist — it **cherry-picks or blocks
each declared slug** from the scope on TWO axes, before the set is frozen and again over time:

  axis 1 — MALWARE risk      : list membership (URLhaus-style CC0 feed) + static lexical features
                               (no fetch) -> 0..100. Stripe-Radar bands.
  axis 2 — CORRUPTED INTENT  : how far a slug's accumulated crawl evidence has DRIFTED from the
                               declared intent (meant_vec). Starts ~0; grows over runs. A slug that
                               began on-purpose but drifts — or was smuggled in — is blocked even if
                               it is not malware. This is the meant<->true divergence (three-track
                               intent log) applied to a single scope item, accumulated over time.

Decision per slug: ALLOW (cherry-pick) | REVIEW (human lane) | BLOCK. Runs at scope-declaration to
curate the frozen set, and re-runs over time to catch corruption.

Deterministic + stdlib today (the malware scorer is real lexical math; the feed is a local file).
The transformer (URL classifier, world-class weights) and the GNN (grows on the domain graph) slot
in behind `provider=`; absent provider falls back to deterministic, never fails. Models never get
to ALLOW something the deterministic list-hit blocks — law gates imagination (FACTORY_SPEC OS Rule).
"""

from __future__ import annotations

import json
import math
import re
import urllib.parse
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

# Stripe-Radar-style bands (ADR-001 §5): low=cherry-pick, mid=review, high=block.
ALLOW_MAX = 64
REVIEW_MAX = 74
# Corrupted-intent: a slug whose evidence has drifted this far from declared intent is not on-purpose.
INTENT_CORRUPTION_REVIEW = 0.55
INTENT_CORRUPTION_BLOCK = 0.75

SUSPICIOUS_TLDS = {"zip", "mov", "xyz", "top", "tk", "ml", "ga", "cf", "gq", "click", "country", "kim"}
SUSPICIOUS_TOKENS = {"login", "verify", "secure", "account", "update", "confirm", "webscr", "signin",
                     "wallet", "bonus", "free", "gift", "unlock", "support-", "-support"}


def slugify_target(url: str) -> str:
    """Stable slug id for a scope entry (host+path, scheme/fragment stripped, lowercased)."""
    p = urllib.parse.urlparse(url.strip())
    base = f"{p.netloc}{p.path}".lower().rstrip("/")
    return re.sub(r"[^a-z0-9._/-]+", "-", base) or url.lower()


def _shannon(s: str) -> float:
    if not s:
        return 0.0
    counts = Counter(s)
    n = len(s)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


@dataclass
class SlugRisk:
    slug: str
    url: str
    malware: float          # 0..100
    intent_corruption: float  # 0..1
    decision: str           # allow | review | block
    reasons: list[str]


def _malware_score(url: str, feed: set[str]) -> tuple[float, list[str]]:
    """Stage 1 list membership (instant block) + Stage 2 static lexical features. No fetch."""
    reasons: list[str] = []
    p = urllib.parse.urlparse(url)
    host, path = p.netloc.lower(), (p.path or "")
    slug = slugify_target(url)
    # Stage 1 — threat-feed membership (URLhaus CC0 / GSB-Web-Risk local DB shape): hard block.
    if host in feed or slug in feed or url.lower() in feed:
        return 100.0, ["threat-feed match (URLhaus/GSB local)"]
    # Stage 2 — lexical features, each contributes to a 0..100 score (XGBoost-style, here transparent).
    score = 0.0
    hostname = host.split(":")[0]
    if re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", hostname):          # IP-literal host
        score += 35; reasons.append("ip-literal host")
    if hostname.startswith("xn--") or "xn--" in hostname:        # punycode/homoglyph
        score += 25; reasons.append("punycode host")
    tld = hostname.rsplit(".", 1)[-1] if "." in hostname else ""
    if tld in SUSPICIOUS_TLDS:
        score += 20; reasons.append(f"suspicious tld .{tld}")
    depth = hostname.count(".")
    if depth >= 4:
        score += 15; reasons.append(f"deep subdomain ({depth})")
    ent = _shannon(hostname)
    if ent > 3.5:                                                # DGA-like high-entropy host
        score += 20; reasons.append(f"high host entropy {ent:.1f}")
    digits = sum(c.isdigit() for c in hostname)
    if hostname and digits / len(hostname) > 0.3:
        score += 10; reasons.append("digit-heavy host")
    if len(url) > 120:
        score += 10; reasons.append("very long url")
    low = (host + path).lower()
    hits = [t for t in SUSPICIOUS_TOKENS if t in low]
    if hits:
        score += min(20, 7 * len(hits)); reasons.append(f"phishing tokens {hits[:3]}")
    if host and "@" in url.split("//", 1)[-1].split("/", 1)[0]:  # userinfo trick
        score += 30; reasons.append("userinfo-in-authority")
    return min(100.0, score), reasons


from lgwks_vecmath import cosine as _cosine  # one source of truth for cosine similarity


def _intent_corruption(slug: str, intent_vec: list[float] | None,
                       history: dict[str, dict]) -> tuple[float, list[str]]:
    """Accumulated drift of a slug's evidence centroid from the declared intent (meant_vec).
    history[slug] carries {evidence_vec, runs}; corruption = 1 - cos(intent, evidence), EMA over runs."""
    if intent_vec is None:
        return 0.0, []
    h = history.get(slug)
    if not h or "evidence_vec" not in h:
        return 0.0, []   # no evidence yet -> not corrupted, just unproven
    drift = 1.0 - _cosine(intent_vec, h["evidence_vec"])
    runs = h.get("runs", 1)
    reasons = []
    if drift >= INTENT_CORRUPTION_REVIEW:
        reasons.append(f"intent drift {drift:.2f} over {runs} run(s)")
    return round(drift, 4), reasons


def load_feed(feed_path: Path | None) -> set[str]:
    """Local threat feed (one host/url per line; '#' comments). URLhaus CC0 bulk dump shape."""
    if not feed_path or not feed_path.exists():
        return set()
    out = set()
    for line in feed_path.read_text(encoding="utf-8").splitlines():
        line = line.strip().lower()
        if line and not line.startswith("#"):
            out.add(line)
    return out


def score_slug(url: str, intent_vec: list[float] | None, feed: set[str],
               history: dict[str, dict]) -> SlugRisk:
    slug = slugify_target(url)
    malware, mreasons = _malware_score(url, feed)
    corruption, creasons = _intent_corruption(slug, intent_vec, history)
    reasons = mreasons + creasons
    # Decision: worst axis governs (defense in depth — either can block).
    if malware >= REVIEW_MAX + 1 or corruption >= INTENT_CORRUPTION_BLOCK:
        decision = "block"
    elif malware > ALLOW_MAX or corruption >= INTENT_CORRUPTION_REVIEW:
        decision = "review"
    else:
        decision = "allow"
    return SlugRisk(slug=slug, url=url, malware=round(malware, 1),
                    intent_corruption=corruption, decision=decision, reasons=reasons)


@dataclass
class Curation:
    kept: list[str]          # cherry-picked — enter the frozen scope
    review: list[SlugRisk]   # human lane
    blocked: list[SlugRisk]  # never enter scope
    scored: list[SlugRisk]
    provider: str            # effective scorer (transformer/gnn fall back to deterministic today)


def curate_scope(declared_urls: list[str], intent_vec: list[float] | None = None,
                 feed_path: Path | None = None, history_path: Path | None = None,
                 provider: str = "deterministic") -> Curation:
    """The G3 gate: take the AI's declared slugs, cherry-pick the clean ones into the frozen scope,
    block malware/corrupted-intent, route the borderline to review. `provider` selects the scorer;
    transformer/gnn fall back to deterministic here (models never override a feed BLOCK)."""
    feed = load_feed(feed_path)
    history: dict[str, dict] = {}
    if history_path and history_path.exists():
        for line in history_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                history[rec["slug"]] = rec
    scored = [score_slug(u, intent_vec, feed, history) for u in declared_urls]
    effective = provider if provider == "deterministic" else "deterministic"  # transformer/gnn not wired
    return Curation(
        kept=[s.url for s in scored if s.decision == "allow"],
        review=[s for s in scored if s.decision == "review"],
        blocked=[s for s in scored if s.decision == "block"],
        scored=scored,
        provider=effective,
    )


def adapt_granularity(slugs: list[str], history: dict[str, dict],
                      collapse_at: int = 3, agree_drift: float = 0.25) -> dict[str, list[str]]:
    """Over time, REDUCE or INCREASE slug granularity from the ML chains (the Director's *.google.com).

    REDUCE (collapse): when >= `collapse_at` sibling subdomains of one registrable domain have all
    been seen with LOW, AGREEING intent-drift, replace them with a single `*.domain` wildcard slug —
    the network learned they behave as one node, so scope compresses.
    INCREASE (expand): a `*.domain` wildcard whose children DISAGREE (drift spread is wide) is split
    back into the specific children that still belong — the wildcard was too coarse.

    Returns {"reduce": [wildcards...], "expand": [specific slugs...]} as proposals (human/critic gated;
    never silently rewrites the frozen scope — this feeds the next declaration round)."""
    def registrable(host: str) -> str:
        parts = host.split(".")
        return ".".join(parts[-2:]) if len(parts) >= 2 else host

    by_domain: dict[str, list[str]] = {}
    for s in slugs:
        host = s.split("/", 1)[0]
        if host.startswith("*."):
            by_domain.setdefault(host[2:], [])   # existing wildcard
        else:
            by_domain.setdefault(registrable(host), []).append(s)

    reduce_to: list[str] = []
    expand_to: list[str] = []
    for domain, members in by_domain.items():
        drifts = [history.get(m, {}).get("drift", 0.0) for m in members if m in history]
        if len(members) >= collapse_at and drifts and max(drifts) < agree_drift:
            reduce_to.append(f"*.{domain}")                       # collapse — they behave as one
        elif drifts and (max(drifts) - min(drifts)) >= agree_drift:
            expand_to.extend(m for m in members if history.get(m, {}).get("drift", 0.0) < agree_drift)
    return {"reduce": sorted(set(reduce_to)), "expand": sorted(set(expand_to))}


def record_evidence(slug: str, evidence_vec: list[float], history_path: Path) -> None:
    """Accumulate a slug's evidence centroid (EMA) so corrupted-intent can grow over time."""
    history: dict[str, dict] = {}
    if history_path.exists():
        for line in history_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                history[rec["slug"]] = rec
    h = history.get(slug, {"slug": slug, "evidence_vec": evidence_vec, "runs": 0})
    prev = h.get("evidence_vec", evidence_vec)
    alpha = 0.3
    h["evidence_vec"] = [round(alpha * n + (1 - alpha) * p, 6) for n, p in zip(evidence_vec, prev)]
    h["runs"] = h.get("runs", 0) + 1
    history[slug] = h
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text(
        "\n".join(json.dumps(v, sort_keys=True) for v in history.values()) + "\n", encoding="utf-8")
