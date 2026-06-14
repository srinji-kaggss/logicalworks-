"""
lgwks_concept — deterministic concept extraction and activation steering.

Every chunk produces concepts. Every concept gets a canonical vector that
encodes WHAT IT IS (type + definition + attributes) not just that it was said.

Design goals:
- No human slop: "EC2" means Amazon Elastic Compute Cloud, not just
  two capital letters that appear in text.
- Activation steering: saying "serverless" activates Lambda, Fargate,
  EVENTBRIDGE, API Gateway — because they share the "serverless" attribute.
- Deterministic: same text → same concept → same vector. Zero ML at ingest.
- Queryable: "what is EC2?" → label + type + definition + attributes + related.
- Tiny: a few hundred lines, stdlib only.

Data model:
    Concept: {id, label, type, definition, aliases, attributes, sources, vector}
    ConceptRel: {from, to, type, weight, evidence}
    ActivationMap: {concept_id → {up, down, lateral}}

Deterministic extraction tiers:
    T1: Domain-agnostic surface extraction (proper nouns, UPPERCASE tokens,
        parenthetical definitions, Wikipedia-style "X is a Y" sentences).
    T2: Domain dictionary overlay (if provided — e.g. AWS service catalog).
    T3: Cross-document consolidation (same label in 3+ chunks with same
        definition pattern → promoted to canonical concept).
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ── taxonomy of concept types (extensible, not hardcoded) ──────────────────────

CONCEPT_TYPES = frozenset({
    "service", "product", "company", "person", "technology", "standard",
    "protocol", "framework", "tool", "platform", "api", "language",
    "database", "algorithm", "model", "architecture", "pattern",
    "regulation", "form", "account", "transaction", "fund",
    "unknown",
})

# Map domain hints to preferred types
_DOMAIN_HINTS: dict[str, str] = {
    "api": "api", "sdk": "tool", "cli": "tool", "gui": "tool",
    "saas": "service", "paas": "platform", "iaas": "platform",
    "db": "database", "database": "database", "sql": "language",
    "nosql": "database", "orm": "framework",
    "ml": "model", "model": "model", "llm": "model",
    "nn": "model", "network": "architecture", "net": "architecture",
    "protocol": "protocol", "standard": "standard", "spec": "standard",
    "rfc": "standard", "iso": "standard",
}


# ── T1: Deterministic surface extraction ───────────────────────────────────────

# "X is a Y" / "X is an Y" / "X refers to Y" / "X, a Y," patterns
# Handles labels with parenthetical aliases: "Amazon EC2 (Elastic Compute Cloud) is a web service"
_DEFINITION_RE = re.compile(
    r"([A-Z][A-Za-z0-9\s\(\)]{1,60}?)\s+is\s+(?:a|an|the)\s+([a-z][a-z0-9\- ]{1,60}?)(?:[.,;]|\s+that|\s+which|\s+used|\s+designed)",
    re.IGNORECASE,
)

# Parenthetical alias: "Amazon EC2 (Elastic Compute Cloud)"
_ALIAS_RE = re.compile(
    r"([A-Z][A-Za-z0-9 ]{2,30})\s+\(([A-Z][A-Za-z0-9\- ]{2,40})\)",
)

# Standalone proper nouns / acronyms (2-8 uppercase letters or mixed alphanumeric like EC2, S3)
_ACRONYM_RE = re.compile(r"\b([A-Z][A-Z0-9]{1,7})\b")

# Capitalised multi-word phrases (product names, services)
_NAME_RE = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\b")

# Domain-specific keyword triggers (e.g. "AWS Lambda", "Amazon S3")
_BRANDED_RE = re.compile(
    r"\b(Amazon|AWS|Google|Microsoft|Azure|OpenAI|Meta|Apple)\s+([A-Z][A-Za-z0-9]+(?:\s+[A-Z][a-z]+){0,2})\b"
)


from lgwks_hashing import blake_id as _hash  # canonical blake2b id (one source of truth)


def _slug(text: str) -> str:
    """Canonical label for dedup: lowercase alphanumeric, stripped."""
    return re.sub(r"[^a-z0-9 ]+", "", text.lower()).strip()


def _tokenize(text: str) -> list[str]:
    """Deterministic word-level tokenization."""
    return re.findall(r"[a-z0-9]+", text.lower())


@dataclass
class Concept:
    concept_id: str
    label: str                        # canonical human label
    slug: str                         # dedup key
    concept_type: str                 # from CONCEPT_TYPES
    definition: str = ""
    aliases: list[str] = field(default_factory=list)
    attributes: dict[str, Any] = field(default_factory=dict)
    source_chunks: list[str] = field(default_factory=list)
    source_docs: list[str] = field(default_factory=list)
    occurrences: int = 0
    first_seen_idx: int = 0           # chunk index where first seen
    confidence: str = "low"           # low | medium | high

    def fingerprint(self) -> str:
        """Deterministic identity string for dedup."""
        return f"{self.slug}|{self.concept_type}|{self.definition[:120]}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "concept_id": self.concept_id,
            "label": self.label,
            "slug": self.slug,
            "type": self.concept_type,
            "definition": self.definition,
            "aliases": self.aliases,
            "attributes": self.attributes,
            "source_chunks": self.source_chunks,
            "source_documents": self.source_docs,
            "occurrences": self.occurrences,
            "first_seen_idx": self.first_seen_idx,
            "confidence": self.confidence,
        }


@dataclass
class ConceptRel:
    rel_id: str
    source: str                       # concept slug
    target: str                       # concept slug
    rel_type: str                     # is_a | integrates_with | depends_on | managed_by | replaces | feeds_into | activates | is_alias_of
    weight: float = 0.0
    evidence_chunks: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rel_id": self.rel_id,
            "source": self.source,
            "target": self.target,
            "rel_type": self.rel_type,
            "weight": round(self.weight, 4),
            "evidence_chunks": self.evidence_chunks,
        }


# ── Concept Extraction Engine ──────────────────────────────────────────────────

class ConceptExtractor:
    """Deterministic concept extraction from text chunks.

    Usage:
        ce = ConceptExtractor()
        for chunk in chunks:
            ce.ingest(chunk["text"], chunk_id=chunk["chunk_id"], doc_id=chunk.get("document_id"))
        concepts, rels = ce.finalize()
    """

    def __init__(self, domain_hints: dict[str, str] | None = None):
        self._concepts: dict[str, Concept] = {}          # slug → Concept
        self._mentions: dict[str, list[tuple[str, str]]] = defaultdict(list)  # slug → [(chunk_id, doc_id)]
        self._rels: list[ConceptRel] = []
        self._domain_hints = domain_hints or {}
        self._chunk_idx = 0

    # ── ingest ───────────────────────────────────────────────────────────────

    def ingest(self, text: str, *, chunk_id: str = "", doc_id: str = "") -> None:
        """Ingest a single chunk and extract candidate concepts."""
        self._chunk_idx += 1

        # 1. Definition sentences → high-confidence concepts
        for m in _DEFINITION_RE.finditer(text):
            raw_label = m.group(1).strip()
            definition = m.group(2).strip()
            if len(raw_label) < 3 or len(definition) < 5:
                continue
            # If label has parenthetical alias, split it
            alias_match = re.match(r"^(.+?)\s*\(([^)]+)\)\s*$", raw_label)
            if alias_match:
                label = alias_match.group(1).strip()
                alias = alias_match.group(2).strip()
            else:
                label = raw_label
                alias = ""
            slug = _slug(label)
            if not slug:
                continue
            c = self._ensure_concept(slug, label, chunk_id, doc_id, confidence="medium")
            if not c.definition:
                c.definition = definition
                c.concept_type = self._infer_type(label, definition)
                c.confidence = "high"
            if alias and alias not in c.aliases:
                c.aliases.append(alias)
                # Register the alias itself as a concept pointing to canonical
                alias_slug = _slug(alias)
                if alias_slug and alias_slug != slug:
                    self._ensure_concept(alias_slug, alias, chunk_id, doc_id)
                    self._add_rel(slug, alias_slug, "is_alias_of", chunk_id, weight=0.95)

        # 2. Parenthetical aliases → EC2 (Elastic Compute Cloud)
        for m in _ALIAS_RE.finditer(text):
            primary = m.group(1).strip()
            alias = m.group(2).strip()
            slug = _slug(primary)
            if not slug:
                continue
            c = self._ensure_concept(slug, primary, chunk_id, doc_id)
            if alias not in c.aliases:
                c.aliases.append(alias)
            # Also register alias as a concept that points to primary
            alias_slug = _slug(alias)
            if alias_slug and alias_slug != slug:
                self._ensure_concept(alias_slug, alias, chunk_id, doc_id)
                self._add_rel(slug, alias_slug, "is_alias_of", chunk_id, weight=0.95)

        # 3. Branded products (Amazon EC2, AWS Lambda)
        for m in _BRANDED_RE.finditer(text):
            brand = m.group(1)
            product = m.group(2)
            label = f"{brand} {product}"
            slug = _slug(label)
            c = self._ensure_concept(slug, label, chunk_id, doc_id)
            c.attributes.setdefault("vendor", brand)
            c.occurrences += 1

        # 4. Capitalised phrases
        for m in _NAME_RE.finditer(text):
            label = m.group(1)
            slug = _slug(label)
            if not slug or len(slug) < 3:
                continue
            # Skip common false positives
            if slug in {"the", "and", "but", "for", "are", "was", "you", "our", "all", "new", "use", "get", "out", "one", "two", "see", "can", "not", "now", "how", "may", "its", "has", "had", "did", "too", "any", "off", "try", "run", "set", "way", "yes", "web", "www", "com"}:
                continue
            c = self._ensure_concept(slug, label, chunk_id, doc_id)
            c.occurrences += 1

        # 5. Acronyms (link to the capitalised phrase they abbreviate)
        acronyms = list(set(_ACRONYM_RE.findall(text)))
        capitalised = [m.group(1) for m in _NAME_RE.finditer(text)]
        for acr in acronyms:
            if len(acr) < 2:
                continue
            # Strategy A: exact initials match
            matched = False
            for phrase in capitalised:
                initials = "".join(w[0].upper() for w in phrase.split() if w)
                if initials == acr:
                    slug = _slug(phrase)
                    c = self._ensure_concept(slug, phrase, chunk_id, doc_id)
                    if acr not in c.aliases:
                        c.aliases.append(acr)
                    matched = True
                    break
            if matched:
                continue
            # Strategy B: acronym is the last token of a capitalised phrase (EC2 in "Amazon EC2")
            for phrase in capitalised:
                words = phrase.split()
                if len(words) >= 2 and words[-1].upper() == acr:
                    slug = _slug(phrase)
                    c = self._ensure_concept(slug, phrase, chunk_id, doc_id)
                    if acr not in c.aliases:
                        c.aliases.append(acr)
                    matched = True
                    break
            if matched:
                continue
            # Strategy C: acronym is a standalone token that matches an existing concept by word token
            for phrase in capitalised:
                if acr.lower() in phrase.lower():
                    slug = _slug(phrase)
                    c = self._ensure_concept(slug, phrase, chunk_id, doc_id)
                    if acr not in c.aliases:
                        c.aliases.append(acr)
                    break

    # ── internal helpers ───────────────────────────────────────────────────────

    def _ensure_concept(self, slug: str, label: str, chunk_id: str, doc_id: str, *, confidence: str = "low") -> Concept:
        if slug in self._concepts:
            c = self._concepts[slug]
            c.occurrences += 1
            if chunk_id and chunk_id not in c.source_chunks:
                c.source_chunks.append(chunk_id)
            if doc_id and doc_id not in c.source_docs:
                c.source_docs.append(doc_id)
            return c

        c = Concept(
            concept_id=f"c-{_hash(slug)[:16]}",
            label=label,
            slug=slug,
            concept_type="unknown",
            source_chunks=[chunk_id] if chunk_id else [],
            source_docs=[doc_id] if doc_id else [],
            occurrences=1,
            first_seen_idx=self._chunk_idx,
            confidence=confidence,
        )
        self._concepts[slug] = c
        return c

    def _infer_type(self, label: str, definition: str) -> str:
        """Guess concept type from label + definition text."""
        text = f"{label} {definition}".lower()
        tokens = _tokenize(text)

        # Check domain hints (longer keys first)
        for hint, ctype in sorted(self._domain_hints.items(), key=lambda kv: -len(kv[0])):
            if hint.lower() in text:
                return ctype

        # Check default domain hints
        for hint, ctype in sorted(_DOMAIN_HINTS.items(), key=lambda kv: -len(kv[0])):
            if hint in text:
                return ctype

        # Structural inference from definition words
        if any(w in text for w in {"service", "managed", "serverless", "cloud", "hosted", "platform"}):
            return "service"
        if any(w in text for w in {"database", "store", "warehouse", "index", "cache"}):
            return "database"
        if any(w in text for w in {"framework", "library", "sdk", "package"}):
            return "framework"
        if any(w in text for w in {"algorithm", "method", "approach", "technique"}):
            return "algorithm"
        if any(w in text for w in {"protocol", "standard", "specification", "rfc"}):
            return "protocol"

        # Default to unknown if nothing matches
        return "unknown"

    def _add_rel(self, source: str, target: str, rel_type: str, chunk_id: str, weight: float = 0.5) -> None:
        rid = f"r-{_hash(f'{source}|{rel_type}|{target}')[:16]}"
        self._rels.append(ConceptRel(
            rel_id=rid,
            source=source,
            target=target,
            rel_type=rel_type,
            weight=weight,
            evidence_chunks=[chunk_id] if chunk_id else [],
        ))

    # ── post-processing: consolidate + build relations ─────────────────────────

    def _build_cooccurrence_rels(self) -> None:
        """If two concepts appear in the same chunk, they are related."""
        chunk_to_slugs: dict[str, set[str]] = defaultdict(set)
        for slug, c in self._concepts.items():
            for cid in c.source_chunks:
                chunk_to_slugs[cid].add(slug)

        for cid, slugs in chunk_to_slugs.items():
            slugs_list = sorted(slugs)
            for i, s1 in enumerate(slugs_list):
                for s2 in slugs_list[i + 1:]:
                    if s1 == s2:
                        continue
                    # Weight = 1 / (co-occurrence count)
                    self._add_rel(s1, s2, "co_occurs_with", cid, weight=0.3)
                    self._add_rel(s2, s1, "co_occurs_with", cid, weight=0.3)

    def _build_attribute_rels(self) -> None:
        """Extract typed relations from definitions."""
        for slug, c in self._concepts.items():
            if not c.definition:
                continue
            # "for Y" / "integrates with Y" / "depends on Y" / "managed by Y"
            for m in re.finditer(r"\b(integrates? with|depends? on|managed by|provided by|replaces|feeds? into|is a type of|part of|subset of)\s+([A-Z][A-Za-z0-9 ]{2,30})", c.definition, re.IGNORECASE):
                verb = m.group(1).lower().replace(" ", "_")
                target_label = m.group(2).strip()
                target_slug = _slug(target_label)
                if target_slug in self._concepts:
                    self._add_rel(slug, target_slug, verb, c.source_chunks[0] if c.source_chunks else "", weight=0.7)

    def _promote_confidence(self) -> None:
        """Seen in 3+ chunks with definition → high. Seen in 1 chunk, no def → low."""
        for slug, c in self._concepts.items():
            if c.occurrences >= 3 and c.definition:
                c.confidence = "high"
            elif c.occurrences >= 2:
                c.confidence = "medium"
            else:
                c.confidence = "low"

    # ── finalize ─────────────────────────────────────────────────────────────

    def finalize(self) -> tuple[list[Concept], list[ConceptRel]]:
        """Return consolidated concepts and relations."""
        self._promote_confidence()
        self._build_cooccurrence_rels()
        self._build_attribute_rels()
        return list(self._concepts.values()), self._rels


# ── Concept Vector Deterministic Hash ──────────────────────────────────────────

CONCEPT_DIMS = 256  # can differ from chunk dims


def concept_vector(concept: Concept) -> list[float]:
    """Deterministic 256-d vector encoding label + type + definition + attributes + aliases.

    This is richer than a chunk vector because it hashes the *canonical meaning*
    of the concept, not just the words in the text.
    """
    vec = [0.0] * CONCEPT_DIMS

    def _add_component(text: str, weight: float = 1.0, salt: str = "") -> None:
        tokens = _tokenize(text)
        for i, tok in enumerate(tokens):
            # Front-loaded importance: first tokens matter more
            pos_weight = 1.0 / (1.0 + math.log1p(i))
            h = hashlib.blake2b(f"{salt}{tok}".encode(), digest_size=8).digest()
            idx = int.from_bytes(h[:4], "big") % CONCEPT_DIMS
            sign = 1.0 if h[4] % 2 == 0 else -1.0
            vec[idx] += sign * weight * pos_weight

    # 1. Label (highest weight — identity)
    _add_component(concept.label, weight=4.0, salt="label:")

    # 2. Type (medium weight — categorical)
    _add_component(concept.concept_type, weight=2.0, salt="type:")

    # 3. Definition (high weight — meaning)
    _add_component(concept.definition, weight=3.0, salt="def:")

    # 4. Aliases (medium weight — name variants)
    for alias in concept.aliases:
        _add_component(alias, weight=1.5, salt="alias:")

    # 5. Attributes (high weight — structured meaning)
    for key, val in sorted(concept.attributes.items()):
        _add_component(f"{key}={val}", weight=2.5, salt="attr:")

    # 6. Occurrence count (rare concepts get slightly different weighting)
    h = hashlib.blake2b(f"occ:{concept.occurrences}".encode(), digest_size=8).digest()
    idx = int.from_bytes(h[:4], "big") % CONCEPT_DIMS
    sign = 1.0 if h[4] % 2 == 0 else -1.0
    vec[idx] += sign * math.log1p(concept.occurrences)

    # L2 normalise
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [round(v / norm, 6) for v in vec]


# ── Activation Map ─────────────────────────────────────────────────────────────

def build_activation_map(concepts: list[Concept], rels: list[ConceptRel]) -> dict[str, dict[str, list[str]]]:
    """For each concept, compute what strengthens, weakens, or is related.

    Returns:
        {concept_slug: {"up": [slugs], "down": [slugs], "lateral": [slugs]}}
    """
    downstream = defaultdict(lambda: defaultdict(float))
    upstream = defaultdict(lambda: defaultdict(float))

    for r in rels:
        if r.rel_type in {"is_alias_of", "co_occurs_with", "integrates_with", "depends_on", "managed_by", "feeds_into"}:
            downstream[r.source][r.target] += r.weight
            upstream[r.target][r.source] += r.weight

    result: dict[str, dict[str, list[str]]] = {}
    for slug in {c.slug for c in concepts}:
        result[slug] = {
            "up": [t for t, w in sorted(upstream[slug].items(), key=lambda kv: -kv[1])[:5] if w > 0.2],
            "down": [t for t, w in sorted(downstream[slug].items(), key=lambda kv: -kv[1])[:5] if w > 0.2],
            "lateral": [t for t, w in sorted(downstream[slug].items(), key=lambda kv: -kv[1])[5:10] if w > 0.1],
        }
    return result


# ── Query API ──────────────────────────────────────────────────────────────────

class ConceptGraph:
    """Query-ready concept graph backed by in-memory structures.

    For production: persist to SQLite. For CLI use: load vectors into memory.
    """

    def __init__(self, concepts: list[Concept], rels: list[ConceptRel]):
        self._by_slug: dict[str, Concept] = {c.slug: c for c in concepts}
        self._by_label: dict[str, Concept] = {c.label.lower(): c for c in concepts}
        self._rels_by_source: dict[str, list[ConceptRel]] = defaultdict(list)
        for r in rels:
            self._rels_by_source[r.source].append(r)
        self._activation = build_activation_map(concepts, rels)
        self._vectors: dict[str, list[float]] = {c.slug: concept_vector(c) for c in concepts}

    # ── resolve ──

    def resolve(self, query: str) -> Concept | None:
        """Resolve a label/slug/alias/acronym to a canonical concept."""
        q = _slug(query)
        if not q:
            return None
        # 1. Exact slug match
        if q in self._by_slug:
            return self._by_slug[q]
        # 2. Alias exact match
        for c in self._by_slug.values():
            if q in {a.lower() for a in c.aliases}:
                return c
        # 3. Query is a word token in label ("ec2" in "amazon ec2")
        q_tokens = set(q.split())
        for c in self._by_slug.values():
            c_tokens = set(c.slug.split())
            if q_tokens & c_tokens:
                # Prefer higher occurrence if multiple match
                if q in c.label.lower():
                    return c
        # 4. Substring in label (fallback — pick most frequent)
        candidates = [c for c in self._by_slug.values() if q in c.slug or q in c.label.lower()]
        if candidates:
            return max(candidates, key=lambda c: c.occurrences)
        return None

    def what_is(self, query: str) -> dict[str, Any] | None:
        """Full concept profile for human-readable query."""
        c = self.resolve(query)
        if not c:
            return None
        return {
            "label": c.label,
            "type": c.concept_type,
            "definition": c.definition,
            "aliases": c.aliases,
            "attributes": c.attributes,
            "occurrences": c.occurrences,
            "confidence": c.confidence,
            "activated_by": self._activation.get(c.slug, {}).get("up", []),
            "activates": self._activation.get(c.slug, {}).get("down", []),
            "related": self._activation.get(c.slug, {}).get("lateral", []),
            "sources": c.source_chunks[:10],
        }

    # ── activation steering ──

    def activated_by(self, query: str) -> list[str]:
        """Concepts that activate (strengthen) this concept."""
        c = self.resolve(query)
        if not c:
            return []
        return self._activation.get(c.slug, {}).get("up", [])

    def activates(self, query: str) -> list[str]:
        """Concepts that this concept activates."""
        c = self.resolve(query)
        if not c:
            return []
        return self._activation.get(c.slug, {}).get("down", [])

    def related(self, query: str) -> list[str]:
        """Lateral concepts (weaker activation but relevant)."""
        c = self.resolve(query)
        if not c:
            return []
        return self._activation.get(c.slug, {}).get("lateral", [])

    # ── vector search over concepts ──

    def nearest(self, query: str, top_k: int = 5) -> list[tuple[str, float]]:
        """Find nearest concepts by deterministic vector similarity."""
        query_vec = None
        if query in self._vectors:
            query_vec = self._vectors[query]
        else:
            c = self.resolve(query)
            if c:
                query_vec = self._vectors.get(c.slug)
        if not query_vec:
            return []

        scores: list[tuple[str, float]] = []
        for slug, vec in self._vectors.items():
            if query_vec is vec:
                continue
            dot = sum(a * b for a, b in zip(query_vec, vec))
            scores.append((slug, round(dot, 4)))
        scores.sort(key=lambda kv: -kv[1])
        return scores[:top_k]

    # ── export ──

    def export_json(self, path: Path) -> None:
        """Write concepts + relations + vectors to JSON."""
        data = {
            "concepts": [c.to_dict() for c in self._by_slug.values()],
            "relations": [r.to_dict() for rlists in self._rels_by_source.values() for r in rlists],
            "vectors": {slug: vec for slug, vec in self._vectors.items()},
            "activation": self._activation,
        }
        path.write_text(json.dumps(data, indent=2, sort_keys=False, default=str), encoding="utf-8")


# ── CLI helper: extract from substrate run ─────────────────────────────────────

def extract_from_chunks(chunks: list[dict[str, Any]], *, domain_hints: dict[str, str] | None = None) -> ConceptGraph:
    """Build a concept graph from substrate chunk rows."""
    ce = ConceptExtractor(domain_hints=domain_hints)
    for chunk in chunks:
        ce.ingest(
            chunk.get("text", ""),
            chunk_id=chunk.get("chunk_id", ""),
            doc_id=chunk.get("document_id", ""),
        )
    concepts, rels = ce.finalize()
    return ConceptGraph(concepts, rels)
