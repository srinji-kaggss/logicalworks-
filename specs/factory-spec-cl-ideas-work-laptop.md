# Factory Spec: cl-ideas → Work-Laptop Deployable Agentic AI

**Date:** 2026-06-03  
**Target:** CyberArk EPM v26.3.0.82 + Docker Desktop + M4 Pro 24GB + macOS Tahoe 26.3.1  
**Constraint:** Zero cloud inference. Zero admin elevation. Zero unsigned binaries.  
**Scope:** Make cl-ideas a "better firecrawl" (local bot-resilient extraction) + basic coder (AST refactor/tweak). Port reusable changes back to logicalworks-.

---

## 1. What Runs on a Locked-Down Corporate Mac

### A. Verified Available (no EPM block)

| Capability | How | Why It Works |
|---|---|---|
| **Docker Desktop** | User-installed, no admin on macOS | Containerized everything — models, browsers, compilers |
| **Python venv** | `./install.sh` from `e556583` | User-space, no sudo, no system packages |
| **CoreML / ANE** | Built into macOS | Apple-signed, native M4 Pro Neural Engine |
| **Playwright** | `pip install playwright` in venv | Chromium/WebKit downloaded to `~/.cache/ms-playwright` |
| **GitHub CLI (`gh`)** | `brew install gh` or download release | Signed binary, or run in Docker |
| **SQLite** | stdlib | Zero install |
| **Git** | Pre-installed on macOS | Signed by Apple |

### B. What EPM Blocks (confirmed patterns)

| Blocked | Why | Workaround |
|---|---|---|
| `sudo` / `brew` (sometimes) | Privilege escalation | Use venv + pip; Docker for system deps |
| Unsigned binaries | EPM application control | Docker containers; Apple-signed frameworks |
| Cloud API calls | Corporate proxy/DLP | Local inference only (Ollama Docker, CoreML) |
| HuggingFace Hub at runtime | Policy + network | Repo-resident weights (`e556583` model hub) |

### C. M4 Pro 24GB RAM — Capacity Math

From `lgwks_workercap.py` formula:

```
RAM:    24 GiB total
        - 6 GiB  (OS + apps)
        - 8 GiB  (always-on Deep ML model reserve)
        - 2 GiB  (safety)
        = 8 GiB usable for workers
        / 2 GiB per worker
        = 4 concurrent workers (ceiling)

CPU:    14 cores (M4 Pro)
        - 5  (reserve for model + system)
        = 9 usable
        / 1 per worker
        = 9 workers (but RAM caps at 4)
```

**Effective capacity:** 4 concurrent agent workers + 1 persistent model server.

---

## 2. The Model Protocol (What Runs Where)

### A. Three-Tier Local Inference (already in lgwks)

```
┌─────────────────────────────────────────────────────────────┐
│  TIER 1 (always)      TIER 2 (opt-in)      TIER 3 (future)   │
│  lgwks_entity_graph   lgwks_coreml.py      lgwks_foundation  │
│  regex extraction     CoreML .mlpackage    Apple FM / NL    │
│  0 deps               <2ms ANE             macOS 26+         │
│  μs latency           deterministic        on-device only   │
└─────────────────────────────────────────────────────────────┘
```

### B. New: Docker-Containerized LLM (for "basic coder")

Since cloud is blocked but 24GB RAM is available, run a **small local model** in Docker:

```yaml
# docker-compose.coder.yml
services:
  ollama:
    image: ollama/ollama:latest
    volumes:
      - ollama:/root/.ollama
    ports:
      - "11434:11434"
    # M4 Pro: pull qwen2.5-coder:7b or codellama:7b
    # 7B model ≈ 4-8GB RAM, fits in the 8GB ML reserve
    deploy:
      resources:
        limits:
          memory: 10G
```

**Models to evaluate:**

| Model | Size | Use Case | ANE/CoreML? |
|---|---|---|---|
| `qwen2.5-coder:7b` | ~4.5GB | Code refactor, explanation | No (llama.cpp) |
| `codellama:7b` | ~4GB | Code generation, infill | No |
| `phi4:14b` | ~9GB | Stronger reasoning | No (may not fit) |
| `tiny-bert` (committed) | 16MB | Intent classification | Yes (CoreML) |
| `distilbert` (committed) | 66MB | Entity extraction | Yes (CoreML) |

**Decision:** Use Ollama Docker for the "basic coder" (refactor/explain), CoreML ANE for intent classification and entity extraction.

---

## 3. "Better Firecrawl" — Spec

### A. What Firecrawl Does (that we need to beat)

1. **Crawl** — JS-rendered page extraction (Playwright)
2. **Scrape** — Convert HTML → structured data (LLM-powered)
3. **Extract** — Schema-governed data extraction (LLM + JSON schema)
4. **Map** — Site structure discovery
5. **Search** — Query over crawled content (vector search)

### B. Our Local-Only Equivalent

| Firecrawl Feature | cl-ideas/lgwks Equivalent | Local? |
|---|---|---|
| `/scrape` (JS render) | `lgwks crawl --webkit` + `fundserv/crawl.py` | ✅ Playwright local |
| `/crawl` (site BFS) | `fundserv/crawl.py` BFS + scope lock | ✅ Deterministic |
| `/extract` (LLM→JSON) | `fundserv/parser.py` + `coreml_classify.py` T2 | ✅ CoreML, no LLM |
| `/map` (site structure) | `fundserv/schema_discover.py` DOM fingerprint | ✅ SHA-256 structural hash |
| `/search` (vector RAG) | `lgwks embed` (local vault) | ✅ Deterministic embeddings |
| Bot detection evasion | `lgwks_browser.py` stealth args | ✅ Honest browser fingerprint |

### C. The Gap — What Makes It "Better"

**Current cl-issues crawl gap:** No content extraction from JS-heavy SPAs. The Angular router on `portal.fundserv.com` rendered an empty shell because auth was missing. When auth works, we get HTML but extraction is regex-only.

**The "better" additions:**

#### C1. Site Profile System (already built, port to lgwks)

`fundserv/site_profile.py` + `config/sites/*.json` decouples crawl/parser from hardcoded assumptions. This should be a first-class lgwks feature.

```json
// config/sites/example.com.json
{
  "host": "example.com",
  "dom": {
    "chrome_tags": ["nav", "header", "footer", "script"],
    "chrome_class_patterns": ["topnav", "dropdown", "cookie-banner"],
    "heading_tags": ["h1", "h2", "h3", "h4"],
    "version_markers": {
      "current_selector": "h4.current",
      "future_selector": "h4.future",
      "current_label": "current",
      "future_label": "future"
    }
  },
  "crawl": {
    "scope_prefix": "/secure/",
    "max_depth": 5,
    "delay_s": 1.5,
    "respect_robots": true
  },
  "schema_discover": {
    "content_signals": {
      "min_content_tags": 10,
      "min_heading_depth": 2
    },
    "confidence_threshold": 0.6
  }
}
```

**Port decision:** ✅ **Port to logicalworks-** as `lgwks_site_profile.py` + `config/sites/` directory. This is generic infrastructure.

#### C2. MLX-Based Content Understanding (new)

Apple's **MLX** framework (pip-installable, M4-optimized) can run small transformer models for:
- Summarization of crawled pages
- Question-answering over local content
- Code understanding (for the "basic coder")

```python
# lgwks_mlx.py — new module (cl-ideas first, port later)
"""MLX-based local inference for content understanding.

Runs on M4 Pro GPU/ANE. No cloud. No CoreML (MLX is separate, more flexible).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_MLX_MODELS_DIR = Path(__file__).resolve().parent / "models" / "mlx"

def _load_mlx_model(model_name: str = "qwen2.5-0.5b") -> Any | None:
    """Load an MLX-format model. Returns None if MLX not installed or model missing."""
    try:
        import mlx.core as mx  # type: ignore[import]
        from mlx_lm import load, generate  # type: ignore[import]
    except ImportError:
        logger.debug("mlx or mlx_lm not installed — pip install mlx mlx-lm")
        return None
    
    model_path = _MLX_MODELS_DIR / model_name
    if not model_path.exists():
        logger.debug("MLX model %s not found at %s", model_name, model_path)
        return None
    
    try:
        model, tokenizer = load(str(model_path))
        return {"model": model, "tokenizer": tokenizer, "backend": "mlx"}
    except Exception as exc:
        logger.warning("Failed to load MLX model: %s", exc)
        return None

def summarize(text: str, max_tokens: int = 256) -> dict[str, Any]:
    """Summarize text using local MLX model. Returns {ok, summary, model}."""
    m = _load_mlx_model()
    if m is None:
        return {"ok": False, "summary": "", "model": "", "reason": "mlx unavailable"}
    
    from mlx_lm import generate  # type: ignore[import]
    prompt = f"Summarize the following text in 2-3 sentences:\n\n{text[:4000]}\n\nSummary:"
    
    try:
        summary = generate(
            m["model"],
            m["tokenizer"],
            prompt=prompt,
            max_tokens=max_tokens,
            verbose=False,
        )
        return {"ok": True, "summary": summary, "model": "qwen2.5-0.5b", "reason": "mlx"}
    except Exception as exc:
        return {"ok": False, "summary": "", "model": "", "reason": f"inference error: {exc}"}
```

**Model selection for 24GB M4 Pro:**
- `qwen2.5-0.5b` — ~300MB, summarization OK, code understanding weak
- `qwen2.5-1.5b` — ~1GB, good balance
- `qwen2.5-coder:1.5b` — ~1GB, code-focused
- `qwen2.5-7b` — ~4.5GB, strong but pushes RAM limits with other workers

**Recommendation:** Start with `qwen2.5-1.5b-instruct` for general content, `qwen2.5-coder:1.5b` for code tasks. Both fit comfortably in the 8GB ML reserve.

**Port decision:** 🔄 **Prototype in cl-ideas**, port to logicalworks- once model selection stabilizes.

#### C3. Enhanced Diff Engine (new)

Current `fundserv/pipeline.py` diffs chunks by hash. We need semantic diff — understanding what *changed* in a regulatory standard, not just that a hash differs.

```python
# lgwks_diff_semantic.py — new module
"""Semantic diff for structured documents.

Compares two versions of a parsed document and emits:
  - added/removed sections
  - modified tables (cell-level)
  - rule changes (eligibility matrix updates)
  - cross-reference integrity checks
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

@dataclass
class SemanticDiff:
    status: str  # "added" | "removed" | "modified" | "unchanged"
    section: str
    field: str | None
    before: str | None
    after: str | None
    confidence: float  # 0.0-1.0, from structural match


def diff_chunks(prev: list[dict], curr: list[dict]) -> list[SemanticDiff]:
    """Diff two chunk lists semantically."""
    # Index by document_id + section + chunk_hash
    prev_idx = {(c["document_id"], c.get("section", ""), c["hash"]): c for c in prev}
    curr_idx = {(c["document_id"], c.get("section", ""), c["hash"]): c for c in curr}
    
    diffs: list[SemanticDiff] = []
    
    # Find removed
    for key, chunk in prev_idx.items():
        if key not in curr_idx:
            diffs.append(SemanticDiff(
                status="removed",
                section=chunk.get("section", ""),
                field=None,
                before=chunk.get("text", "")[:200],
                after=None,
                confidence=1.0,
            ))
    
    # Find added
    for key, chunk in curr_idx.items():
        if key not in prev_idx:
            diffs.append(SemanticDiff(
                status="added",
                section=chunk.get("section", ""),
                field=None,
                before=None,
                after=chunk.get("text", "")[:200],
                confidence=1.0,
            ))
    
    # Find modified (same section, different hash)
    # ... table cell comparison, rule extraction, etc.
    
    return diffs
```

**Port decision:** ✅ **Port to logicalworks-** as `lgwks_diff.py`. Generic document diffing is a core capability.

---

## 4. "Basic Coder" — Spec

### A. Scope: Refactor/Tweak Only (No Generation)

The user explicitly said: "we have done most of the work and it just needs to refactor/tweak."

This means:
- ✅ Rename symbols
- ✅ Extract methods
- ✅ Move code between files
- ✅ Type annotation insertion
- ✅ Import sorting/optimization
- ✅ Dead code removal
- ❌ Write new functions from scratch
- ❌ Architectural redesign
- ❌ Test generation (out of scope)

### B. Implementation: AST-Based + Pattern Matching

**No LLM needed for refactoring.** Use Python's `ast` module + `libcst` (if available) for deterministic transforms.

```python
# lgwks_refactor.py — new module (logicalworks- first)
"""Deterministic code refactoring via AST + pattern matching.

No LLM. No cloud. Pure structural transforms.
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class RefactorEngine:
    """AST-based refactoring engine."""
    
    def __init__(self, source: str, filename: str = "<unknown>"):
        self.source = source
        self.filename = filename
        self.tree = ast.parse(source, filename=filename)
        self.changes: list[dict] = []
    
    # ── transforms ─────────────────────────────────────────────────────
    
    def rename_symbol(self, old_name: str, new_name: str) -> "RefactorEngine":
        """Rename a function, class, or variable across the file."""
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Name) and node.id == old_name:
                node.id = new_name
                self.changes.append({
                    "type": "rename",
                    "old": old_name,
                    "new": new_name,
                    "line": getattr(node, "lineno", 0),
                })
            elif isinstance(node, ast.FunctionDef) and node.name == old_name:
                node.name = new_name
                self.changes.append({"type": "rename", "old": old_name, "new": new_name, "line": node.lineno})
            elif isinstance(node, ast.ClassDef) and node.name == old_name:
                node.name = new_name
                self.changes.append({"type": "rename", "old": old_name, "new": new_name, "line": node.lineno})
        return self
    
    def extract_method(self, class_name: str, method_name: str, 
                       new_method_name: str, lines: tuple[int, int]) -> "RefactorEngine":
        """Extract a block of code into a new method."""
        # Find the class, find the method, extract lines into new method
        # ... implementation
        return self
    
    def add_type_annotations(self, type_map: dict[str, str]) -> "RefactorEngine":
        """Insert type annotations from a name→type mapping."""
        for node in ast.walk(self.tree):
            if isinstance(node, ast.FunctionDef):
                for arg in node.args.args:
                    if arg.arg in type_map and arg.annotation is None:
                        arg.annotation = ast.Name(id=type_map[arg.arg], ctx=ast.Load())
                        self.changes.append({
                            "type": "add_annotation",
                            "name": arg.arg,
                            "annotation": type_map[arg.arg],
                            "line": node.lineno,
                        })
        return self
    
    def remove_unused_imports(self) -> "RefactorEngine":
        """Remove import statements that are never referenced."""
        # Build usage map, find unused imports, mark for removal
        # ... implementation
        return self
    
    # ── output ───────────────────────────────────────────────────────────
    
    def apply(self) -> str:
        """Apply all changes and return modified source."""
        # Use ast.unparse (Python 3.9+) or codegen for older versions
        try:
            return ast.unparse(self.tree)
        except AttributeError:
            # Fallback for Python < 3.9
            import codegen  # type: ignore[import]
            return codegen.to_source(self.tree)
    
    def preview(self) -> list[dict]:
        """Return list of planned changes without applying."""
        return self.changes


def refactor_file(path: Path, operations: list[dict]) -> dict[str, Any]:
    """Apply a list of refactor operations to a file.
    
    operations: [{"op": "rename", "old": "foo", "new": "bar"}, ...]
    Returns: {ok, path, changes_count, diff_preview}
    """
    source = path.read_text()
    engine = RefactorEngine(source, filename=str(path))
    
    for op in operations:
        if op["op"] == "rename":
            engine.rename_symbol(op["old"], op["new"])
        elif op["op"] == "add_types":
            engine.add_type_annotations(op["type_map"])
        elif op["op"] == "remove_unused_imports":
            engine.remove_unused_imports()
    
    preview = engine.preview()
    if not preview:
        return {"ok": True, "path": str(path), "changes_count": 0, "diff_preview": "No changes needed"}
    
    new_source = engine.apply()
    # Write only if different
    if new_source != source:
        path.write_text(new_source)
    
    return {
        "ok": True,
        "path": str(path),
        "changes_count": len(preview),
        "diff_preview": f"{len(preview)} changes: " + ", ".join(c["type"] for c in preview[:5]),
    }
```

### C. Integration with lgwks

New verb: `lgwks refactor`

```bash
# Preview changes
lgwks refactor --preview --file src/foo.py rename --old bad_name --new good_name

# Apply changes
lgwks refactor --file src/foo.py rename --old bad_name --new good_name

# Batch refactor from JSON plan
lgwks refactor --plan refactor_plan.json
```

**Port decision:** ✅ **Build in logicalworks-** as `lgwks_refactor.py`. This is generic infrastructure.

---

## 5. Docker-Based Local LLM (For When AST Isn't Enough)

### A. Ollama in Docker

```yaml
# docker-compose.yml (cl-ideas root)
version: "3.8"
services:
  ollama:
    image: ollama/ollama:latest
    container_name: lgwks-ollama
    volumes:
      - ollama:/root/.ollama
    ports:
      - "127.0.0.1:11434:11434"  # localhost only, no external exposure
    environment:
      - OLLAMA_HOST=0.0.0.0
    # M4 Pro: use CPU (no GPU passthrough in Docker Desktop for Mac yet)
    # Still fast enough for 1.5B-7B models
    deploy:
      resources:
        limits:
          memory: 10G
        reservations:
          memory: 4G

volumes:
  ollama:
```

### B. Startup Script

```bash
#!/bin/bash
# start-local-llm.sh — idempotent Ollama launcher

set -euo pipefail

CONTAINER_NAME="lgwks-ollama"
MODEL_NAME="${LGWKS_LOCAL_MODEL:-qwen2.5-coder:1.5b}"

echo "[lgwks] Checking Docker..."
if ! docker info >/dev/null 2>&1; then
    echo "[lgwks] Docker not running. Start Docker Desktop first."
    exit 1
fi

echo "[lgwks] Starting Ollama container..."
if docker ps -q -f name="$CONTAINER_NAME" | grep -q .; then
    echo "[lgwks] Ollama already running."
else
    docker compose -f docker-compose.yml up -d ollama
    echo "[lgwks] Waiting for Ollama to be ready..."
    until curl -s http://localhost:11434/api/tags >/dev/null 2>&1; do
        sleep 1
    done
fi

echo "[lgwks] Pulling model $MODEL_NAME (if not present)..."
curl -s -X POST http://localhost:11434/api/pull -d "{\"name\":\"$MODEL_NAME\"}" >/dev/null

echo "[lgwks] Local LLM ready at http://localhost:11434"
echo "[lgwks] Model: $MODEL_NAME"
```

### C. Integration with lgwks

```python
# lgwks_local_llm.py — thin wrapper around local Ollama
"""Local LLM inference via Ollama (Docker). No cloud. Fallback to None if unavailable."""

from __future__ import annotations

import json
import logging
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

_OLLAMA_URL = "http://localhost:11434/api/generate"

def available() -> bool:
    """Is a local Ollama instance responding?"""
    try:
        req = urllib.request.Request("http://localhost:11434/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=2) as resp:
            return resp.status == 200
    except Exception:
        return False

def generate(prompt: str, model: str = "qwen2.5-coder:1.5b", 
             max_tokens: int = 1024, temperature: float = 0.2) -> dict[str, Any]:
    """Generate text via local Ollama. Returns {ok, text, model, tokens}."""
    if not available():
        return {"ok": False, "text": "", "model": "", "tokens": 0, "reason": "ollama not available — run ./start-local-llm.sh"}
    
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "num_predict": max_tokens,
            "temperature": temperature,
        },
    }).encode()
    
    try:
        req = urllib.request.Request(_OLLAMA_URL, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
            return {
                "ok": True,
                "text": data.get("response", ""),
                "model": model,
                "tokens": data.get("eval_count", 0),
                "reason": "ollama-local",
            }
    except Exception as exc:
        return {"ok": False, "text": "", "model": "", "tokens": 0, "reason": f"ollama error: {exc}"}
```

**Port decision:** 🔄 **Prototype in cl-ideas**, port to logicalworks- once stabilized. This is a new capability (local LLM bridge).

---

## 6. The Factory Port Matrix

| Change | cl-ideas (private) | logicalworks- (public) | Notes |
|---|---|---|---|
| **Site Profile System** | ✅ Exists | 🔄 **Port** | Generic infrastructure |
| **MLX Content Summary** | 🔄 Prototype | 🔄 Port after validation | New capability |
| **Semantic Diff Engine** | 🔄 Build | 🔄 **Port** | Generic document diff |
| **AST Refactor Engine** | ❌ Not needed | ✅ **Build** | Generic infrastructure |
| **Ollama Docker Bridge** | 🔄 Prototype | 🔄 Port after validation | New capability |
| **SPA-aware Auth** | ✅ Exists | ✅ Already there | `lgwks_browser.py` |
| **CoreML Classification** | ✅ Exists | ✅ Already there | `lgwks_coreml.py` |
| **Entity Graph** | ✅ Exists | ✅ Already there | `lgwks_entity_graph.py` |
| **Repo-resident Models** | ✅ Exists | ✅ Already there | `e556583` |
| **Intent Classifier** | ❌ Not needed | ✅ Already there | `lgwks_intent_classifier.py` |

---

## 7. Implementation Order

### Phase 1: cl-ideas "Better Firecrawl" (This Week)

1. **Wire `coreml_classify.py` into `schema_discover.py`**
   - When DOM fingerprint confidence < 0.6, fall back to CoreML T2
   - One-line change: `if confidence < threshold: result = coreml_classify.classify_page(text)`

2. **Add MLX summarization to crawl pipeline**
   - New module: `fundserv/mlx_content.py`
   - After parse, summarize each chunk for human review
   - Only runs if `mlx` pip package installed

3. **Semantic diff for regulatory changes**
   - New module: `fundserv/semantic_diff.py`
   - Compare V36 → V37 chunks, emit rule-level diffs
   - Highlight eligibility matrix changes

### Phase 2: logicalworks- Port (Next Week)

1. **Port site profile system**
   - `lgwks_site_profile.py` + `config/sites/` directory
   - Load profile by host, merge with defaults

2. **Port semantic diff engine**
   - `lgwks_diff.py` — generic document diffing
   - Integrate with `lgwks_entity_graph.py` for chunk comparison

3. **Build AST refactor engine**
   - `lgwks_refactor.py` — deterministic code transforms
   - New verb: `lgwks refactor`

### Phase 3: Work-Laptop Packaging (Following Week)

1. **Docker Compose for Ollama**
   - `docker-compose.yml` at repo root
   - `start-local-llm.sh` helper script
   - Document in `README.md`

2. **Enhanced `install.sh`**
   - Detect M4 Pro, suggest MLX models
   - Check Docker availability, print Ollama setup instructions
   - Option: `--with-mlx` flag to pip install `mlx` + `mlx-lm`

3. **One-command setup**
   ```bash
   git clone <repo>
   cd logicalworks-
   ./install.sh              # venv, deps, models
   ./start-local-llm.sh      # Docker Ollama (optional)
   lgwks doctor              # verify everything
   ```

---

## 8. Verification Commands

```bash
# Verify lgwks core works offline
lgwks doctor

# Verify site profile system
lgwks crawl --profile config/sites/estandards.fundserv.com.json <url>

# Verify CoreML classification
lgwks model_hub load tiny-bert
lgwks entity-graph classify --text "Fundserv V36 standard"

# Verify local LLM (if Ollama running)
curl http://localhost:11434/api/tags

# Verify MLX (if installed)
python -c "import mlx.core; print('MLX OK')"

# Verify refactor engine (preview only)
lgwks refactor --preview --file test.py rename --old foo --new bar
```

---

## 9. Risk Assessment

| Risk | Likelihood | Mitigation |
|---|---|---|
| EPM blocks Docker socket | Low | Docker Desktop uses macOS hypervisor, not raw socket |
| EPM blocks `gh` CLI | Medium | Use Docker-based `gh` or download signed release |
| MLX pip install fails | Medium | Fallback to CoreML-only; MLX is optional |
| Ollama 7B model OOMs | Low | Capacity math shows 4.5GB fits in 8GB reserve |
| AST refactor corrupts code | Low | `--preview` mode mandatory; only apply after review |
| Site profile schema drift | Medium | Version profiles in JSON schema; validate on load |

---

**RISK:** The highest risk is **EPM blocking the Ollama Docker image** or the `gh` CLI binary. The mitigation is graceful degradation: if Ollama is unavailable, the "basic coder" falls back to AST-only (no LLM). If `gh` is unavailable, lgwks uses `git` directly for repo operations. The core crawl/extract/pipeline works without either.
