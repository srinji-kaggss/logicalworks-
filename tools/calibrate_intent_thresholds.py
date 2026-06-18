"""
calibrate_intent_thresholds.py — validate and calibrate authority thresholds
against the labeled intent corpus.

Usage:
    python3 tools/calibrate_intent_thresholds.py [--update]
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import lgwks_intent_classifier as ic

CORPUS_PATH = ROOT / "store" / "models" / "intent_calibration_corpus.json"
THRESH_PATH = ROOT / "store" / "models" / "intent_calibration.json"

def main():
    # Ensure manifest cache is populated for consistent testing
    sys.path.insert(0, str(ROOT))
    import lgwks_manifest
    manifest = lgwks_manifest.build_manifest()
    MANIFEST_CACHE = ROOT / "store" / "manifest-cache.json"
    if not MANIFEST_CACHE.parent.exists():
        MANIFEST_CACHE.parent.mkdir(parents=True)
    MANIFEST_CACHE.write_text(json.dumps(manifest, indent=2))
    print(f"Manifest cache populated with {len(manifest.get('verbs', []))} verbs.")

    if not CORPUS_PATH.exists():
        print(f"Corpus not found: {CORPUS_PATH}")
        sys.exit(1)

    corpus = json.loads(CORPUS_PATH.read_text())
    
    # Force NO_MODELS=1 for deterministic lexical path if real model not available
    # or to test the baseline.
    os.environ["LGWKS_NO_MODELS"] = "1"
    
    try:
        # Load from the cache we just wrote
        clf = ic.IntentClassifier.load(MANIFEST_CACHE)
    except Exception as e:
        print(f"Failed to load classifier: {e}")
        sys.exit(1)

    results = []
    print(f"{'Query':<40} | {'Expected':<10} | {'Actual':<10} | {'Label':<15} | {'Conf':<6} | {'Margin':<6} | {'Status'}")
    print("-" * 120)

    for entry in corpus["entries"]:
        query = entry["query"]
        expected = entry["expected"]
        expected_label = entry.get("label")
        
        res = clf.classify(query)
        
        actual = "refuse"
        if res.grants_full_authority:
            actual = "execute"
        elif res.plan_only:
            actual = "plan"
        
        # In lexical mode, grants_full_authority is ALWAYS False because of the method check.
        # So "execute" expected will always fail "actual" match if we are in lexical mode.
        # We should probably check if it WOULD grant authority if the method were semantic.
        
        would_execute = (bool(res.label) and res.confidence >= ic.FULL_AUTHORITY_THRESHOLD)
        
        status = "✅" if actual == expected else "❌"
        if expected == "execute" and not res.grants_full_authority and would_execute:
             status = "⚠️ (Lexical)"
        
        # Label check
        if expected_label and res.label != expected_label:
            status += " (Wrong Label)"
        
        print(f"{query[:40]:<40} | {expected:<10} | {actual:<10} | {res.label[:15]:<15} | {res.confidence:.4f} | {res.margin:.4f} | {status}")
        
        results.append({
            "query": query,
            "expected": expected,
            "actual": actual,
            "confidence": res.confidence,
            "margin": res.margin,
            "label": res.label
        })

    # Summary and calibration advice
    exec_conf = [r["confidence"] for r in results if r["expected"] == "execute"]
    plan_conf = [r["confidence"] for r in results if r["expected"] == "plan"]
    refuse_conf = [r["confidence"] for r in results if r["expected"] == "refuse"]
    
    exec_margin = [r["margin"] for r in results if r["expected"] == "execute"]
    refuse_margin = [r["margin"] for r in results if r["expected"] == "refuse"]

    print("\nSummary Metrics:")
    if exec_conf:
        print(f"  Execute Conf:  min={min(exec_conf):.4f}, avg={sum(exec_conf)/len(exec_conf):.4f}")
    if plan_conf:
        print(f"  Plan Conf:     min={min(plan_conf):.4f}, avg={sum(plan_conf)/len(plan_conf):.4f}")
    if refuse_conf:
        print(f"  Refuse Conf:   max={max(refuse_conf):.4f}, avg={sum(refuse_conf)/len(refuse_conf):.4f}")

    if exec_margin:
        print(f"  Execute Margin: min={min(exec_margin):.4f}, avg={sum(exec_margin)/len(exec_margin):.4f}")
    if refuse_margin:
        print(f"  Refuse Margin:  max={max(refuse_margin):.4f}, avg={sum(refuse_margin)/len(refuse_margin):.4f}")

if __name__ == "__main__":
    main()
