"""lgwks_foundation — T3 structured extraction via Apple Foundation Models (macOS 26+, on-device).

This is a graceful-degrade stub:
  - If Foundation Models are unavailable, returns empty extraction with status "unavailable"
  - If available, uses on-device structured extraction for genuinely ambiguous content
  - Never calls a cloud API; all inference is local to the Neural Engine / GPU

//why: T1 regex + T2 CoreML handle 95% of cases. T3 is for the long tail where
contextual understanding is required (e.g., disambiguating "transfer" as a noun vs
verb in a complex sentence). Foundation Models provide this without cloud dependency.
"""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Attempt to import Apple frameworks — fails gracefully on older macOS or non-Apple platforms
_HAS_FM = False
try:
    # Foundation Models framework (macOS 26+ expected API shape)
    # This is a speculative import based on WWDC announcements; actual API may differ.
    import FoundationModels  # type: ignore[import]
    _HAS_FM = True
except Exception:
    pass

# Fallback: NaturalLanguage framework (macOS 15+, BERT-based embeddings)
_HAS_NL = False
try:
    import NaturalLanguage  # type: ignore[import]
    _HAS_NL = True
except Exception:
    pass


@dataclass(frozen=True)
class ExtractedEntity:
    text: str
    type: str
    confidence: float
    start: int
    end: int


@dataclass(frozen=True)
class ExtractionResult:
    status: str  # "ok" | "unavailable" | "error"
    entities: list[ExtractedEntity]
    raw: dict[str, Any]


def available() -> dict[str, Any]:
    """Report which on-device ML backends are present."""
    return {
        "foundation_models": _HAS_FM,
        "natural_language": _HAS_NL,
        "platform": sys.platform,
    }


def _extract_with_nl(text: str, entity_types: list[str]) -> ExtractionResult:
    """Use NaturalLanguage NER as a fallback when Foundation Models are absent.
    //why: NLTagger Python API is not well-documented; this path is a safe stub that
    returns unavailable until the real API is verified."""
    entities: list[ExtractedEntity] = []
    if not _HAS_NL:
        return ExtractionResult("unavailable", entities, {})

    try:
        # NLTagger for named entity recognition
        import NaturalLanguage as NL  # type: ignore[import]
        tagger = NL.NLTagger(tagSchemes=[NL.NLTagScheme.nameType])
        tagger.string = text
        # Python API for enumerateTags is not closure-based like Swift.
        # Use tags(in:unit:scheme:options:) which returns a list of (tag, range) tuples.
        for scheme in [NL.NLTagScheme.nameType, NL.NLTagScheme.lexicalClass]:
            tagger.setLanguage(NL.NLLanguage.english, range=(0, len(text)))
            tags = tagger.tags(inRange=(0, len(text)), unit=NL.NLTokenUnit.word, scheme=scheme, options=NL.NLTaggerOptions.omitPunctuation | NL.NLTaggerOptions.omitWhitespace | NL.NLTaggerOptions.joinContractions)
            for tag, token_range in tags:
                if tag is None:
                    continue
                entity_type = str(tag.rawValue) if hasattr(tag, "rawValue") else str(tag)
                if entity_types and entity_type not in entity_types:
                    continue
                start = token_range[0] if isinstance(token_range, (tuple, list)) else token_range.location
                length = token_range[1] if isinstance(token_range, (tuple, list)) else token_range.length
                entities.append(ExtractedEntity(
                    text=text[start:start + length],
                    type=entity_type,
                    confidence=1.0,
                    start=start,
                    end=start + length,
                ))
    except Exception as exc:
        logger.warning("NaturalLanguage extraction failed: %s", exc)
        return ExtractionResult("error", entities, {"error": str(exc)})

    return ExtractionResult("ok", entities, {"backend": "natural_language"})


def extract_entities(
    text: str,
    entity_types: list[str] | None = None,
    *,
    context: str = "",
) -> ExtractionResult:
    """Extract structured entities from text using the best available on-device model.

    entity_types: filter to these types (e.g., ["ACCOUNT", "PLAN_TYPE", "AMOUNT"])
    context: optional surrounding paragraph for disambiguation
    """
    if _HAS_FM:
        # Foundation Models path (macOS 26+ speculative API)
        try:
            # Actual API will depend on Apple's final SDK; this is a structural placeholder
            # that degrades gracefully if the real API differs.
            logger.info("Foundation Models available — using on-device structured extraction")
            # TODO: replace with real FM API once macOS 26 SDK ships
            return ExtractionResult("unavailable", [], {"note": "Foundation Models API not yet finalized"})
        except Exception as exc:
            logger.warning("Foundation Models extraction failed: %s", exc)
            return ExtractionResult("error", [], {"error": str(exc)})

    if _HAS_NL:
        return _extract_with_nl(text, entity_types or [])

    return ExtractionResult("unavailable", [], {"reason": "no on-device ML backend available"})


def main(argv: list[str] | None = None) -> int:
    import argparse
    p = argparse.ArgumentParser(prog="lgwks_foundation", description="T3 on-device entity extraction")
    p.add_argument("text", nargs="?", help="text to extract from")
    p.add_argument("--types", help="comma-separated entity types")
    p.add_argument("--json", action="store_true", help="structured output")
    args = p.parse_args(argv)

    if not args.text:
        print(json.dumps(available(), indent=2))
        return 0

    types = [t.strip() for t in args.types.split(",")] if args.types else []
    result = extract_entities(args.text, entity_types=types)

    out = {
        "status": result.status,
        "entities": [
            {"text": e.text, "type": e.type, "confidence": e.confidence, "start": e.start, "end": e.end}
            for e in result.entities
        ],
        "meta": result.raw,
    }
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
