from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class InvitedProfile:
    profile_url: str
    profile_name: str
    invited_at: datetime


@dataclass(frozen=True)
class RunLog:
    id: int
    started_at: datetime
    finished_at: datetime | None
    status: str
    sent_count: int
    skipped_count: int
    error_message: str | None
