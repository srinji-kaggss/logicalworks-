"""lgwks_clock — the single source of truth for timestamps.

now_iso() is the one wall-clock stamp used across the system. It replaces ~11
copy-pasted helpers (`_now`, `_ts`) that had drifted into two incompatible wire
formats for the same instant:

  - daemon / daemon_event / daemon_store / hooks / session :  ...+00:00   (5 files)
  - synthesizer / bot_optimizer / bot_code_hacker / bot_stress: ...+00:00 (4 files, via timespec)
  - do / workflows                                          :  ...Z       (2 files, strftime)

The first two groups already emit the same string; the `Z` form was the outlier.
One helper makes every timestamp in the system byte-comparable (string sort ==
chronological sort), which the daemon's event ordering relies on.

Format: RFC 3339 / ISO 8601, UTC, second precision, e.g. '2026-06-14T12:00:00+00:00'.
"""

from __future__ import annotations

from datetime import datetime, timezone

__all__ = ["now_iso"]


def now_iso() -> str:
    """Current UTC time as 'YYYY-MM-DDTHH:MM:SS+00:00' (second precision)."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
