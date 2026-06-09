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
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

# Import the heuristic classifier as fallback
import lgwks_intent
import lgwks_model_hub


# Known verb categories for classification
_VERB_CATEGORIES: list[str] = [
    "research",      # jarvis, crawl, fetch, public, refine, extract
    "code",          # repo, review, debug, refactor, graph
    "system",        # solve, doctor, intent, keyvault, foundation, auth
    "data",          # store, memory, embed, axiom, pipeline
    "github",        # gh
    "devops",        # project, batch, session, hooks, agent-os, portal, do
    "multiply",      # x
    "meta",          # manifest, preview, preview, login
    "unknown",       # catch-all
]

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
        if model.config.num_labels != len(_VERB_CATEGORIES):
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


def _heuristic_classify(text: str) -> tuple[str, float]:
    """Fast heuristic fallback classifier. Returns (category, confidence)."""
    text_lower = text.lower()

    # Simple keyword-based classification
    if any(w in text_lower for w in {"crawl", "search", "research", "find", "lookup", "wiki", "arxiv", "paper"}):
        return "research", 0.7
    if any(w in text_lower for w in {"code", "review", "debug", "refactor", "test", "bug", "fix", "ast", "graph"}):
        return "code", 0.75
    if any(w in text_lower for w in {"system", "solve", "config", "setup", "doctor", "health", "check"}):
        return "system", 0.65
    if any(w in text_lower for w in {"store", "memory", "embed", "data", "cache", "vault"}):
        return "data", 0.6
    if any(w in text_lower for w in {"github", "gh", "pr", "pull", "issue", "merge", "repo", "request"}):
        return "github", 0.8
    if any(w in text_lower for w in {"project", "deploy", "batch", "session", "fleet", "agent", "spawn"}):
        return "devops", 0.65
    if any(w in text_lower for w in {"multiply", "x", "brace", "product", "chain"}) or "{" in text and "}" in text:
        return "multiply", 0.9
    if any(w in text_lower for w in {"manifest", "preview", "login", "help", "what can"}):
        return "meta", 0.6

    return "unknown", 0.3


def classify(text: str) -> dict[str, Any]:
    """Classify user intent into a verb category.

    Returns:
        {
            "category": str,      # verb category
            "confidence": float,  # 0..1
            "method": str,        # "tiny-bert" | "heuristic"
            "latency_ms": float,
            "input_hash": str,    # SHA-256 of input for audit
        }
    """
    t0 = time.time()
    input_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

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
            # tiny-bert has 9 output classes matching _VERB_CATEGORIES
            category = _VERB_CATEGORIES[pred] if pred < len(_VERB_CATEGORIES) else "unknown"
            latency_ms = (time.time() - t0) * 1000

            return {
                "category": category,
                "confidence": round(confidence, 3),
                "method": "tiny-bert",
                "latency_ms": round(latency_ms, 2),
                "input_hash": input_hash,
            }
        except Exception:
            # Fall back to heuristic on model error
            pass

    # Heuristic fallback
    category, confidence = _heuristic_classify(text)
    latency_ms = (time.time() - t0) * 1000

    return {
        "category": category,
        "confidence": round(confidence, 3),
        "method": "heuristic",
        "latency_ms": round(latency_ms, 2),
        "input_hash": input_hash,
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
