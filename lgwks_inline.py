"""lgwks_inline — unified payload-inlining resolver.

Consolidates ad-hoc file/CID readers into a single resolver supporting @path,
@data://, binary auto-base64, and @cid: pointers into the axiom vault.

Part of the ant-ergonomics adoption set (Issue 157).
"""

from __future__ import annotations

import base64
import json
import mimetypes
import sys
from pathlib import Path
from typing import Any, Optional

# Constants
MAX_INLINE_BYTES = 2_000_000  # 2MB limit (aligned with lgwks_embed)
AXIOM_RUN_ROOTS = [
    Path(".lgwks") / "axiom" / "runs",
    Path(".lgwks") / "runs",
]

def resolve_payload(value: str, max_bytes: int = MAX_INLINE_BYTES) -> str:
    """
    Resolve a payload string which might be an @path, @data://, or @cid: pointer.
    
    Order of resolution:
    1.  \\@escape -> literal @
    2.  @data://... -> raw base64 passthrough
    3.  @cid:<cid> -> resolve from axiom vault
    4.  @path -> file content (text or auto-base64)
    5.  raw string -> literal value
    """
    if value.startswith("\\@"):
        return value[1:]

    if not value.startswith("@"):
        return value
    
    if value.startswith("@data://") or value.startswith("@data:"):
        # The value is the data URI itself
        return value[1:]
        
    if value.startswith("@cid:"):
        cid = value[5:]
        return _resolve_cid(cid)
        
    # It's an @path
    path_str = value[1:]
    path = Path(path_str).expanduser()
    
    # Try finding it relative to CWD if it doesn't exist
    if not path.exists():
        path = Path.cwd() / path_str
        
    if not path.exists():
        # If it doesn't exist as a file, maybe it was meant to be a literal @string?
        # ant-ergonomics usually fails if @path is used but file is missing.
        raise FileNotFoundError(f"Inline file not found: {path_str}")
    
    if path.stat().st_size > max_bytes:
        raise ValueError(f"Inline file too large: {path_str} ({path.stat().st_size} bytes > {max_bytes} cap)")
        
    # Sniff MIME type
    mime, _ = mimetypes.guess_type(path)
    # Heuristic for text: mime is text/* or no extension and looks like text
    is_text = mime is None or mime.startswith("text/")
    
    if is_text:
        try:
            # Try reading as UTF-8
            return path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            is_text = False
            
    # Binary handling: auto-base64 + MIME sniff
    raw = path.read_bytes()
    b64 = base64.b64encode(raw).decode("ascii")
    mime = mime or "application/octet-stream"
    return f"data:{mime};base64,{b64}"

def _resolve_cid(cid: str) -> str:
    """
    Resolve content from the axiom vault using a CID.
    Must go through the existing axiom/ verify path.
    """
    # Scan known run roots for emissions that contain this CID
    for root in AXIOM_RUN_ROOTS:
        if not root.exists():
            continue
        for run_dir in sorted(root.iterdir(), reverse=True): # Newest first
            if not run_dir.is_dir():
                continue
            # Look for emissions.jsonl files
            for p in run_dir.glob("*-emissions.jsonl"):
                try:
                    for line in p.read_text(encoding="utf-8").splitlines():
                        data = json.loads(line)
                        if data.get("cid") == cid:
                            # Found it.
                            capsule_data = data.get("capsule", {})
                            claim = capsule_data.get("claim")
                            if claim is not None:
                                return str(claim)
                            # Check other fields
                            for key in ("narration_claim", "narration_hole"):
                                if key in data:
                                    # If it's a dict, take the 'source' or 'why_unmatched'
                                    val = data[key]
                                    if isinstance(val, dict):
                                        return val.get("source") or val.get("why_unmatched") or str(val)
                                    return str(val)
                except Exception:
                    continue
    
    raise ValueError(f"CID not found in axiom vault: {cid}")

def get_precedence_payload(expr: Optional[str] = None, 
                          file_at: Optional[str] = None, 
                          stdin_text: Optional[str] = None) -> str:
    """
    Shared precedence helper: --expr > --file/@ > stdin.
    """
    if expr:
        # If expr starts with @, it is resolved
        return resolve_payload(expr)
    if file_at:
        # If file_at is provided, we treat it as an @path if it doesn't start with @
        val = file_at if file_at.startswith("@") else f"@{file_at}"
        return resolve_payload(val)
    if stdin_text is not None:
        return stdin_text
    return ""
