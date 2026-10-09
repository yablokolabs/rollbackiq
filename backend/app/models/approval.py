"""Recovery proposals and human approvals.

An approval is scoped to one exact proposal through a canonical hash. If the
proposal changes after approval was granted — a different target, a different
environment, a newly required migration — the hash no longer matches and the
safety gate vetoes execution. This is what makes "approved" a statement about a
specific action rather than a general permission.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import Enum
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from .incident import utcnow


class ProposedAction(str, Enum):
    ROLLBACK = "rollback"
    HOLD = "hold"
    ESCALATE = "escalate"


class RecoveryProposal(BaseModel):
    incident_id: str
    action: ProposedAction
    target_release: Optional[str] = None
    environment: str = "demo"
    requires_migration: bool = False
    risks: List[str] = Field(default_factory=list)
    contraindications: List[str] = Field(default_factory=list)
    evidence_refs: List[str] = Field(default_factory=list)
    expected_recovery: str = ""
    created_at: datetime = Field(default_factory=utcnow)

    def canonical_payload(self) -> Dict[str, object]:
        """The decision-relevant fields, in a stable representation."""
        return {
            "incident_id": self.incident_id,
            "action": self.action.value,
            "target_release": self.target_release,
            "environment": self.environment,
            "requires_migration": self.requires_migration,
        }

    @property
    def proposal_hash(self) -> str:
        payload = json.dumps(self.canonical_payload(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


class ApprovalDecision(str, Enum):
    APPROVED = "APPROVED"
    DENIED = "DENIED"


#: Actor names that cannot act as the human approver.
NON_HUMAN_ACTORS = frozenset({"", "system", "agent", "duo", "rollbackiq", "automation"})


class Approval(BaseModel):
    id: str
    incident_id: str
    proposal_hash: str
    actor: str
    decision: ApprovalDecision
    environment: str = "demo"
    created_at: datetime = Field(default_factory=utcnow)
    expires_at: Optional[datetime] = None
    scope_note: str = ""

    def is_expired(self, now: datetime) -> bool:
        return self.expires_at is not None and now >= self.expires_at
