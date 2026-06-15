"""lgwks_config — validated YAML config surface (lgwks.config.v1).

Deterministic precedence: env var > project config > home config > coded defaults.
Enforces schema validation and provides provenance for all parameters.

Part of the ant-ergonomics adoption set (Issue 158).
"""

from __future__ import annotations

import os
import yaml
import json
import sys
from pathlib import Path
from typing import Any, Optional

SCHEMA_ID = "lgwks.config.v1"
HOME_CONFIG = Path.home() / ".lgwks" / "config.yaml"
PROJECT_CONFIG = Path(".lgwks") / "config.yaml"

# Hardcoded defaults (Layer 0)
DEFAULTS: dict[str, Any] = {
    "pipeline": {
        "recall_k": 2000,
        "fast_rank_k": 200,
        "heavy_rank_k": 50,
        "noise_threshold": 0.90,
        "diversity_penalty": 0.30,
        "same_source_cap": 50,
        "max_llm_ratio": 0.20,
        "batch_size": 256,
        "mm_embed_model": "google/gemini-embedding-2",
        "mm_max_img_bytes": 6 * 1024 * 1024,
        "coherence_threshold": 0.65,
        "gemma_model": "gemma3:1b"
    },
    "intent": {
        "confidence_threshold": 0.55,
        "full_authority_threshold": 0.85,
        "margin_min": 0.02
    },
    "model_hub": {
        "default_runtime": "auto"
    }
}

# Env mapping (Layer 2 - overrides everything)
ENV_MAP = {
    "LGWKS_RECALL_K": ("pipeline", "recall_k", int),
    "LGWKS_FAST_RANK_K": ("pipeline", "fast_rank_k", int),
    "LGWKS_HEAVY_RANK_K": ("pipeline", "heavy_rank_k", int),
    "LGWKS_NOISE_THRESHOLD": ("pipeline", "noise_threshold", float),
    "LGWKS_DIVERSITY_PENALTY": ("pipeline", "diversity_penalty", float),
    "LGWKS_SAME_SOURCE_CAP": ("pipeline", "same_source_cap", int),
    "LGWKS_MAX_LLM_RATIO": ("pipeline", "max_llm_ratio", float),
    "LGWKS_BATCH_SIZE": ("pipeline", "batch_size", int),
    "LGWKS_MM_EMBED_MODEL": ("pipeline", "mm_embed_model", str),
    "LGWKS_MM_MAX_IMG_BYTES": ("pipeline", "mm_max_img_bytes", int),
    "LGWKS_COHERENCE_THRESHOLD": ("pipeline", "coherence_threshold", float),
    "LGWKS_GEMMA_MODEL": ("pipeline", "gemma_model", str),
}

def load_config() -> dict[str, Any]:
    """Load and merge config from all layers."""
    # 1. Start with defaults
    import copy
    config = copy.deepcopy(DEFAULTS)
    provenance = {f"{s}.{k}": "default" for s, sub in DEFAULTS.items() for k in sub}

    # 2. Load YAML (Layer 1)
    for p in [HOME_CONFIG, PROJECT_CONFIG]:
        if p.exists():
            try:
                with p.open("r", encoding="utf-8") as f:
                    yaml_data = yaml.safe_load(f)
                    if yaml_data:
                        _deep_merge(config, yaml_data, provenance, str(p))
            except Exception as e:
                print(f"warning: failed to load config from {p}: {e}", file=sys.stderr)

    # 3. Apply Environment Variables (Layer 2)
    for env_var, (section, key, parser) in ENV_MAP.items():
        val = os.environ.get(env_var)
        if val is not None:
            try:
                config[section][key] = parser(val)
                provenance[f"{section}.{key}"] = f"env:{env_var}"
            except Exception as e:
                print(f"warning: invalid value for {env_var}: {e}", file=sys.stderr)

    # 4. Validate
    _validate(config)
    
    config["_provenance"] = provenance
    config["schema"] = SCHEMA_ID
    return config

def _deep_merge(base: dict, update: dict, provenance: dict, source: str, prefix: str = ""):
    for k, v in update.items():
        if k == "schema": continue
        path = f"{prefix}.{k}" if prefix else k
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _deep_merge(base[k], v, provenance, source, path)
        elif k in base or prefix: # Only merge known keys or if in a known section
            base[k] = v
            provenance[path] = source

def _validate(config: dict):
    """Validate against lgwks.config.v1 schema."""
    try:
        import jsonschema
        schema_path = Path(__file__).parent / "docs" / "schemas" / "lgwks.config.v1.json"
        if schema_path.exists():
            schema = json.loads(schema_path.read_text())
            jsonschema.validate(instance=config, schema=schema)
    except ImportError:
        # Fallback for minimal environments
        pass
    except Exception as e:
        print(f"error: config validation failed: {e}", file=sys.stderr)
        sys.exit(1)

# Global singleton
_CONFIG = None

def get_config() -> dict[str, Any]:
    """Get the active config singleton."""
    global _CONFIG
    if _CONFIG is None:
        _CONFIG = load_config()
    return _CONFIG
