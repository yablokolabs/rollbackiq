"""Release records.

A rollback target must be a release this system previously observed as healthy.
``known_good`` is set only by the baseline capture path, never by a caller
asserting it.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from .incident import utcnow


class Release(BaseModel):
    id: str
    commit_sha: str = "unknown"
    pipeline_id: str = "unknown"
    environment: str = "demo"
    deployed_at: Optional[datetime] = None
    image_digest: Optional[str] = None
    known_good: bool = False
    # Migration state. ``None`` means "not established", which the safety gate
    # treats as unsafe rather than as compatible.
    requires_migration: bool = False
    migration_compatible: Optional[bool] = None
    created_at: datetime = Field(default_factory=utcnow)

    def is_rollback_target_for(self, current_release_id: str) -> bool:
        return self.known_good and self.id != current_release_id
