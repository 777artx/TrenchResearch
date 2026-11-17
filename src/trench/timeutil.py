from __future__ import annotations

from datetime import UTC, datetime


def utcnow() -> datetime:
    """Timezone-aware UTC now. All stored timestamps are UTC."""
    return datetime.now(UTC)
