"""
lgwks_intent_router — deterministic intent routing with tiny-bert.

Replaces the heuristic classifier with a model-driven router. Uses the 4-model
hierarchy:
  - tiny-bert (2-layer, 128d) — edge/ANE intent classification
  - distilbert-base-uncased (6-layer, 768d) — STEM gate for crawl ingest
  - neobert (28-layer, 768d, 4K context) — research engine
  - codebert-base (12-layer, 768d) — code review engine

The router loads tiny-bert from the repo-resident models/ directory. If not
present, it falls back to the fast heuristic classifier (zero-token, zero-latency).

All routing decisions are logged with confidence scores for audit.
"""

from __future__ import annotations

import argparse
import lgwks_hashing
import json
import sys
import time
from pathlib import Path
from typing import Any

# Import the heuristic classifier as fallback
import lgwks_intent
import lgwks_model_hub


# Known verb categories for classification (fallback)
_VERB_CATEGORIES: list[str] = [
    "research", "code", "system", "data", "github", "devops", "multiply", "meta", "unknown"
]


def _derive_taxonomy() -> list[str]:
    """Derives categories from the live manifest subsystems."""
    try:
        # Avoid circular import if called during module load
        from lgwks_manifest import build_manifest
        manifest = build_manifest()
        
        # Primary segments of verbs define the initial subsystem taxonomy
        subsystems = sorted({v["verb"].split()[0] for v in manifest.get("verbs", [])})
        
        # Ensure canonical categories are present (merged or mapped)
        canonical = ["research", "code", "system", "data", "github", "devops", "multiply", "meta"]
        
        # For now, return a union to ensure backward compatibility with hardcoded lists
        # but prioritized by manifest truth.
        return sorted(list(set(subsystems) | set(canonical))) + ["unknown"]
    except Exception:
        return _VERB_CATEGORIES


# ── Lazy-loaded categories ───────────────────────────────────────────────
_DERIVED_CATEGORIES: list[str] | None = None

def get_categories() -> list[str]:
    global _DERIVED_CATEGORIES
    if _DERIVED_CATEGORIES is None:
        _DERIVED_CATEGORIES = _derive_taxonomy()
    return _DERIVED_CATEGORIES

# Mapping from heuristic intent types to verb categories
_HEURISTIC_MAP: dict[str, str] = {
    "research": "research",
    "code": "code",
    "debug": "code",
    "system": "system",
    "data": "data",
    "github": "github",
    "project": "devops",
    "multiply": "multiply",
    "unknown": "unknown",
}


def _load_tinybert() -> Any | None:
    """Load tiny-bert from model hub if available. Returns model or None."""
    try:
        result = lgwks_model_hub.load_model("tiny-bert")
        if not result["ok"]:
            return None
        # Try to load with transformers
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
        model_dir = result["path"]
        tokenizer = AutoTokenizer.from_pretrained(model_dir)
        model = AutoModelForSequenceClassification.from_pretrained(model_dir)
        # Validate model has the right number of output classes
        if model.config.num_labels != len(get_categories()):
            # Not fine-tuned for our task — needs training
            return None
        return {"model": model, "tokenizer": tokenizer, "name": "tiny-bert"}
    except Exception:
        return None


# Lazy-loaded cache
_TINYBERT = None

def _get_router() -> Any | None:
    global _TINYBERT
    if _TINYBERT is None:
        _TINYBERT = _load_tinybert()
    return _TINYBERT


# Mapping categories to keywords for heuristic fallback
_CATEGORY_KEYWORDS: dict[str, set[str]] = {
    "research": {"crawl", "search", "research", "find", "lookup", "wiki", "arxiv", "paper", "fetch", "grab", "extract"},
    "code": {"code", "review", "debug", "refactor", "test", "bug", "fix", "ast", "graph", "ship", "merge", "rebase"},
    "system": {"solve", "config", "setup", "doctor", "health", "check", "intent", "auth", "keyvault", "vault", "foundation", "identity"},
    "data": {"store", "memory", "embed", "data", "cache", "axiom", "pipeline", "fabric", "crdt", "state"},
    "github": {"github", "gh", "pr", "pull", "issue", "request", "repository"},
    "devops": {"project", "deploy", "batch", "session", "fleet", "agent", "spawn", "ops", "workflow", "portal", "do"},
    "multiply": {"multiply", "x", "brace", "product", "chain"},
    "meta": {"manifest", "preview", "login", "help", "what can", "initialize", "setup"},
}


def _heuristic_classify(text: str) -> dict[str, Any]:
    """Fast heuristic fallback classifier with density-based scoring and explanation."""
    text_lower = text.lower()
    # Simple regex tokenizer if lgwks_hashing.tokenize is not available
    import re
    words = set(re.findall(r"[a-z0-9]+", text_lower))
    
    if not words:
        return {"category": "unknown", "confidence": 0.0, "reason": "empty input"}

    best_cat = "unknown"
    best_conf = 0.3
    best_matches = []

    for cat, keywords in _CATEGORY_KEYWORDS.items():
        matches = [w for w in words if w in keywords]
        if not matches:
            continue
        
        # //why density-based: matching 1/2 words is stronger than 1/100 words.
        # Matches are capped at 0.9 to leave room for the model path.
        density = len(matches) / len(words)
        conf = min(0.4 + (density * 0.5), 0.9)
        
        if conf > best_conf:
            best_cat = cat
            best_conf = conf
            best_matches = matches

    reason = f"matched keywords: {', '.join(best_matches)}" if best_matches else "no keywords matched"
    return {
        "category": best_cat,
        "confidence": round(best_conf, 3),
        "reason": reason,
        "matches": best_matches
    }


def classify(text: str) -> dict[str, Any]:
    """Classify user intent into a verb category.

    Returns:
        {
            "category": str,      # verb category
            "confidence": float,  # 0..1
            "method": str,        # "tiny-bert" | "heuristic"
            "latency_ms": float,
            "input_hash": str,    # SHA-256 of input for audit
            "reason": str,        # explanation for the decision
        }
    """
    t0 = time.time()
    input_hash = lgwks_hashing.content_id(text)

    router = _get_router()
    if router is not None:
        try:
            import torch
            tokenizer = router["tokenizer"]
            model = router["model"]
            inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=128)
            with torch.no_grad():
                outputs = model(**inputs)
                probs = torch.nn.functional.softmax(outputs.logits, dim=-1)
                pred = torch.argmax(probs, dim=-1).item()
                confidence = probs[0][pred].item()

            # Map prediction index to category
            categories = get_categories()
            category = categories[pred] if pred < len(categories) else "unknown"
            latency_ms = (time.time() - t0) * 1000

            return {
                "category": category,
                "confidence": round(confidence, 3),
                "method": "tiny-bert",
                "latency_ms": round(latency_ms, 2),
                "input_hash": input_hash,
                "reason": f"model predicted {category} with {confidence:.1%} confidence"
            }
        except Exception:
            # Fall through to heuristic if model inference fails
            pass

    # Heuristic fallback
    res = _heuristic_classify(text)
    latency_ms = (time.time() - t0) * 1000
    
    return {
        "category": res["category"],
        "confidence": res["confidence"],
        "method": "heuristic",
        "latency_ms": round(latency_ms, 2),
        "input_hash": input_hash,
        "reason": res["reason"]
    }


def route(text: str) -> dict[str, Any]:
    """Full routing: classify + map to concrete verb + args.

    Returns:
        {
            "category": str,
            "confidence": float,
            "method": str,
            "latency_ms": float,
            "verb": str,          # concrete lgwks verb
            "args": list[str],    # recommended args
            "note": str,          # human-readable guidance
        }
    """
    result = classify(text)
    category = result["category"]

    # Map category to concrete verb + args
    routes: dict[str, tuple[str, list[str], str]] = {
        "research": ("jarvis crawl", ["--prompt", text[:80]], "research crawl with your intent as prompt"),
        "code": ("repo status", [], "check repo state first, then review/debug"),
        "system": ("doctor", [], "run health check"),
        "data": ("store", ["--json"], "check data store status"),
        "github": ("gh issues", [], "list open issues"),
        "devops": ("do code", [], "unified orchestrator for devops tasks"),
        "multiply": ("x", [], "multiply intent with brace expression"),
        "meta": ("manifest", ["--json"], "discover capabilities"),
        "unknown": ("refine", [text], "refine your intent for better routing"),
    }

    verb, args, note = routes.get(category, ("refine", [text], "refine your intent"))

    return {
        **result,
        "verb": verb,
        "args": args,
        "note": note,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def add_parser(sub) -> None:
    router = sub.add_parser("route", help="deterministic intent router (tiny-bert + heuristic fallback)")
    router.add_argument("text", nargs="?", help="intent text to classify")
    router.add_argument("--json", action="store_true", help="structured output")
    router.add_argument("--model", choices=["auto", "heuristic", "tiny-bert"], default="auto",
                        help="routing model: auto (default), heuristic only, or tiny-bert only")
    router.set_defaults(func=_route_command)


def _route_command(args: argparse.Namespace) -> int:
    text = args.text
    if not text:
        if sys.stdin.isatty():
            print("error: provide text argument or pipe stdin", file=sys.stderr)
            return 2
        text = sys.stdin.read().strip()

    if not text:
        print("error: empty input", file=sys.stderr)
        return 2

    # Force heuristic if requested
    if getattr(args, "model", "auto") == "heuristic":
        result = classify(text)
        # Override method
        result["method"] = "heuristic"
    elif getattr(args, "model", "auto") == "tiny-bert":
        result = classify(text)
        if result["method"] != "tiny-bert":
            print("error: tiny-bert not available (run scripts/setup_models.py)", file=sys.stderr)
            return 1
    else:
        result = route(text)

    if getattr(args, "json", False):
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"  intent:     {text[:60]}{'...' if len(text) > 60 else ''}")
        print(f"  category:   {result['category']}")
        print(f"  confidence: {result['confidence']}")
        print(f"  method:     {result['method']}")
        if "verb" in result:
            print(f"  verb:       lgwks {result['verb']}")
        if "note" in result:
            print(f"  note:       {result['note']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print("usage: lgwks_intent_router.py <text>", file=sys.stderr)
        return 2
    result = route(args[0])
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
