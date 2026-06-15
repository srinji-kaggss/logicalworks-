"""lgwks_transform — minimal JSONPath/GJSON-like extractor (Issue 159)."""

import json
from typing import Any

def apply_transform(data: Any, expr: str) -> Any:
    """
    Apply a simple path expression to extract data.
    Supports dot-notation 'a.b.c' and array mapping 'a.#.c'.
    """
    if not expr:
        return data
        
    parts = expr.split('.')
    current = data
    
    for i, part in enumerate(parts):
        if part == '#':
            # Map the rest of the expression over the array
            if not isinstance(current, list):
                return None
            rest = '.'.join(parts[i+1:])
            if not rest:
                return current
            return [apply_transform(item, rest) for item in current]
            
        elif isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list):
            try:
                idx = int(part)
                current = current[idx] if 0 <= idx < len(current) else None
            except ValueError:
                return None
        else:
            return None
            
    return current
