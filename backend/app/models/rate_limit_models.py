from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    limit: int
    current: int
    remaining: int
    reset_at: datetime


@dataclass(frozen=True)
class ConcurrencyResult:
    allowed: bool
    limit: int
    active: int
    already_acquired: bool = False


@dataclass(frozen=True)
class AdminResetResult:
    request_keys_removed: int
    concurrency_entries_removed: int
