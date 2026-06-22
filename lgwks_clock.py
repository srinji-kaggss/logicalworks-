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

import time
from datetime import datetime, timezone

__all__ = ["now_iso", "now_aware", "stamp_compact", "date_compact", "now_human"]


def now_iso() -> str:
    """Current UTC time as 'YYYY-MM-DDTHH:MM:SS+00:00' (second precision)."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def now_aware() -> datetime:
    """Current UTC instant as an aware datetime — for arithmetic (age, deltas),
    not display. The one place raw `datetime.now(timezone.utc)` lives (#223)."""
    return datetime.now(timezone.utc)


def stamp_compact() -> str:
    """Compact UTC stamp 'YYYYMMDD-HHMMSS' for run-ids / filenames (lexically
    sortable == chronological). One source of truth — replaces scattered
    `time.strftime('%Y%m%d-%H%M%S', …)`, some of which were LOCAL time (#223)."""
    return time.strftime("%Y%m%d-%H%M%S", time.gmtime())


def date_compact() -> str:
    """Compact UTC date 'YYYYMMDD' (e.g. a daily cache-key salt). Replaces local
    `time.strftime('%Y%m%d')`, which rolled over at local — not UTC — midnight (#223)."""
    return time.strftime("%Y%m%d", time.gmtime())


def now_human() -> str:
    """Human-readable UTC stamp 'YYYY-MM-DD HH:MM:SS UTC' for reports/display (#223)."""
    return time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
