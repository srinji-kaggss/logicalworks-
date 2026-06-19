"""lgwks_search_engine — the 'Web Browser for AIs'. 

Consolidates search, ingestion, and visual grounding into a single protocol.
Bypasses 'DOM bs' by prioritizing symbolic APIs and vision-based extraction.

Protocol Ladder:
  1. Symbolic Path:   Direct API / ctx7 / llms.txt (Zero DOM)
  2. Visual Path:     Qwen3-VL screenshot grounding (Layer 5/15)
  3. Substrate Path:  Clean markdown extraction (Layer 12)
"""

from __future__ import annotations

import json
import time
import urllib.parse
from pathlib import Path
from typing import Any

import lgwks_browser
import lgwks_run
import lgwks_model_mesh as mesh
from lgwks_substrate_io import _sha

# Role alignment with MESH_LAW
ROLE_SEARCH = "extract"  # Using Layer 12 (Extractor) for structured fact retrieval
ROLE_VISION = "embed"    # Using Layer 5 (The Eye) for visual grounding

def resolve_fact(query: str, domain_hint: str | None = None) -> dict[str, Any]:
    """Resolves a query into verified facts adhering to the Strict Escalation Ladder.
    
    //why: Every action must flow Symbolic -> ML -> LLM. Handoffs are ONLY 
    used when the limit of the previous gate is hit, never before.
    """
    # GATE 1: Symbolic / Deterministic (ctx7 API)
    if domain_hint and _is_library_query(query, domain_hint):
        facts = _resolve_via_ctx7(query, domain_hint)
        if facts:
            return {"ok": True, "via": "symbolic:ctx7", "facts": facts}

    # GATE 2: Sensor / ML (Sweep + lgwks_extract)
    from lgwks_search import sweep
    evidence = sweep(query)
    if not evidence.get("has_evidence"):
        return {"ok": False, "reason": "no evidence found in any search arm"}

    top_url = evidence["results"][0]["url"]
    
    import lgwks_extract
    # Extract uses the same ladder internally (crwl -> curl -> vision)
    doc = lgwks_extract.extract(top_url, max_chars=2500)
    if doc.get("ok") and doc.get("text"):
        fact = {
            "fact_id": f"fact-{_sha(top_url + query)[:16]}",
            "document_id": f"doc-{_sha(top_url)[:16]}",
            "query": query,
            "confidence": 1.0,  # Deterministic text extraction
            "via": "sensor:extract",
            "content": doc["text"]
        }
        return {"ok": True, "via": "sensor", "url": top_url, "fact": fact}

    # GATE 3: Generative (Vision Grounding)
    # ONLY executed if all text-based extraction mechanisms fail completely
    grounding = _ground_visually(top_url, query)
    
    return grounding

def _is_library_query(query: str, domain: str) -> bool:
    # Heuristic: does it look like a technical/doc query?
    return any(kw in query.lower() for kw in ("api", "hook", "class", "function", "method"))

def _resolve_via_ctx7(query: str, library: str) -> list[dict[str, Any]] | None:
    """Uses context7-cli to get structured documentation directly."""
    try:
        import subprocess
        # Normalize library name for ctx7
        lib_id = library if library.startswith("/") else f"/{library}"
        cmd = ["ctx7", "docs", lib_id, query]
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if p.returncode == 0 and p.stdout.strip():
            return [{"source": "ctx7", "text": p.stdout.strip()}]
    except Exception:
        pass
    return None

def _ground_visually(url: str, query: str) -> dict[str, Any]:
    """Renders page, takes screenshot, and uses Qwen3-VL (Layer 5) to extract facts.
    
    //why: 'seeing' the page is more robust than walking a broken DOM.
    """
    # 1. Render + Screenshot (Layer 5)
    r = lgwks_browser.render(url, with_screenshot=True, wait_ms=3000)
    if not r.get("ok") or not r.get("screenshot_b64"):
        return {"ok": False, "reason": "visual rendering failed"}

    # 2. Vision Extraction (Layer 12: LFM2-Extract)
    # Ask the Eye to find the specific fact in the screenshot.
    import base64
    img_data = base64.b64decode(r["screenshot_b64"])
    
    # lgwks_run.embed_dual handles the multimodal grounding
    res = lgwks_run.embed_dual(query, embed_on=True, modality="image", media=img_data)
    
    # 3. Formulate Fact Record (The Standalone Trajectory)
    doc_id = f"doc-{_sha(url)[:16]}"
    fact = {
        "fact_id": f"fact-{_sha(doc_id + query)[:16]}",
        "document_id": doc_id,
        "query": query,
        "confidence": res.get("confidence", 0.9),
        "via": "vision-grounding:qwen3-vl",
        "content": r.get("text", "")[:2000] # Still keep a text snippet for the cortex
    }
    
    return {"ok": True, "via": "vision", "url": url, "fact": fact}

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("usage: python3 lgwks_search_engine.py <query> [domain]")
        raise SystemExit(2)
    q = sys.argv[1]
    d = sys.argv[2] if len(sys.argv) > 2 else None
    print(json.dumps(resolve_fact(q, d), indent=2))
