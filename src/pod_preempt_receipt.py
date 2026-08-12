"""Pod Preempt Receipt.

Turns preemptible GPU termination into an explicit recovery state transition:
select the newest verified checkpoint, quantify lost work, mint a bounded restart
grant, and refuse restart when checkpoint lineage or grant bounds do not match.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


class Decision(str, Enum):
    ALLOW = "ALLOW"
    REFUSE = "REFUSE"


@dataclass(frozen=True)
class PodPreemptReceiptRequest:
    subject_id: str
    payload: dict[str, Any] = field(default_factory=dict)
    budget: float = 1.0
    grant_id: str | None = None
    not_after: float | None = None


@dataclass(frozen=True)
class PodPreemptReceiptReceipt:
    decision: Decision
    reasons: tuple[str, ...]
    digest: str
    metrics: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"decision": self.decision.value, "reasons": list(self.reasons), "digest": self.digest, "metrics": self.metrics}


class PreemptError(ValueError):
    pass


class PodPreemptReceipt:
    MIN_BUDGET = 0.0

    @staticmethod
    def _num(value: Any, label: str, *, minimum: float | None = None) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise PreemptError(f"{label}_invalid")
        value = float(value)
        if not math.isfinite(value):
            raise PreemptError(f"{label}_not_finite")
        if minimum is not None and value < minimum:
            raise PreemptError(f"{label}_below_minimum")
        return value

    @staticmethod
    def _id(value: Any, label: str) -> str:
        value = str(value or "").strip()
        if not value:
            raise PreemptError(f"{label}_missing")
        return value

    @classmethod
    def _checkpoint(cls, raw: Any, index: int) -> dict[str, Any]:
        if not isinstance(raw, dict):
            raise PreemptError(f"checkpoint_{index}_not_object")
        digest = str(raw.get("state_digest", "")).strip()
        if not SHA256_RE.fullmatch(digest):
            raise PreemptError(f"checkpoint_{index}_state_digest_invalid")
        return {
            "checkpoint_id": cls._id(raw.get("checkpoint_id"), f"checkpoint_{index}_id"),
            "created_at": cls._num(raw.get("created_at"), f"checkpoint_{index}_created_at", minimum=0),
            "state_digest": digest,
            "uri": cls._id(raw.get("uri"), f"checkpoint_{index}_uri"),
            "verified": raw.get("verified") is True,
        }

    @classmethod
    def _preempt(cls, payload: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
        event = payload.get("event")
        workload = payload.get("workload")
        if not isinstance(event, dict):
            raise PreemptError("event_missing")
        if not isinstance(workload, dict):
            raise PreemptError("workload_missing")
        preempt_id = cls._id(event.get("preempt_id"), "preempt_id")
        pod_id = cls._id(event.get("pod_id"), "pod_id")
        reason = cls._id(event.get("reason"), "preempt_reason")
        observed_at = cls._num(event.get("observed_at"), "observed_at", minimum=0)
        heartbeat_at = cls._num(event.get("last_heartbeat_at"), "last_heartbeat_at", minimum=0)
        if heartbeat_at > observed_at:
            raise PreemptError("heartbeat_after_preempt_observation")
        restart_window_s = cls._num(payload.get("restart_window_s", 900.0), "restart_window_s", minimum=1)
        max_heartbeat_gap_s = cls._num(payload.get("max_heartbeat_gap_s", 120.0), "max_heartbeat_gap_s", minimum=1)
        raw_checkpoints = payload.get("checkpoints")
        if not isinstance(raw_checkpoints, list):
            raise PreemptError("checkpoints_not_list")
        checkpoints = [cls._checkpoint(row, i) for i, row in enumerate(raw_checkpoints)]
        usable = [c for c in checkpoints if c["verified"] and c["created_at"] <= observed_at]
        usable.sort(key=lambda c: (-c["created_at"], c["checkpoint_id"]))
        checkpoint = usable[0] if usable else None
        heartbeat_gap = observed_at - heartbeat_at
        reasons: list[str] = []
        if heartbeat_gap > max_heartbeat_gap_s:
            reasons.append("heartbeat_gap_exceeded")
        if checkpoint is None:
            reasons.append("verified_checkpoint_missing")
        job_id = cls._id(workload.get("job_id"), "job_id")
        restart_profile = cls._id(workload.get("restart_profile"), "restart_profile")
        max_attempts = int(cls._num(workload.get("max_restart_attempts", 3), "max_restart_attempts", minimum=1))
        restart_grant = None
        lost_work_s = None
        if checkpoint:
            lost_work_s = max(0.0, observed_at - checkpoint["created_at"])
            grant_body = {
                "preempt_id": preempt_id,
                "pod_id": pod_id,
                "job_id": job_id,
                "checkpoint_id": checkpoint["checkpoint_id"],
                "checkpoint_digest": checkpoint["state_digest"],
                "restart_profile": restart_profile,
                "issued_at": observed_at,
                "expires_at": observed_at + restart_window_s,
                "max_restart_attempts": max_attempts,
            }
            restart_grant = {**grant_body, "grant_id": _digest(grant_body)}
        result = {
            "state": "RECOVERABLE" if checkpoint and not reasons else "UNRECOVERABLE",
            "preempt_id": preempt_id,
            "pod_id": pod_id,
            "reason": reason,
            "heartbeat_gap_s": round(heartbeat_gap, 9),
            "checkpoint": checkpoint,
            "lost_work_s": round(lost_work_s, 9) if lost_work_s is not None else None,
            "restart_grant": restart_grant,
        }
        return result, reasons

    @classmethod
    def _restart(cls, payload: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
        grant = payload.get("restart_grant")
        if not isinstance(grant, dict):
            raise PreemptError("restart_grant_missing")
        required = ("grant_id", "preempt_id", "pod_id", "job_id", "checkpoint_id", "checkpoint_digest", "restart_profile", "issued_at", "expires_at", "max_restart_attempts")
        if any(key not in grant for key in required):
            raise PreemptError("restart_grant_incomplete")
        expected_body = {key: grant[key] for key in required if key != "grant_id"}
        if str(grant["grant_id"]) != _digest(expected_body):
            raise PreemptError("restart_grant_digest_invalid")
        if not SHA256_RE.fullmatch(str(grant["checkpoint_digest"])):
            raise PreemptError("checkpoint_digest_invalid")
        presented_digest = str(payload.get("checkpoint_digest", "")).strip()
        if presented_digest != grant["checkpoint_digest"]:
            raise PreemptError("checkpoint_lineage_mismatch")
        now = cls._num(payload.get("now"), "now", minimum=0)
        attempt = int(cls._num(payload.get("attempt"), "attempt", minimum=1))
        reasons: list[str] = []
        if now > float(grant["expires_at"]):
            reasons.append("restart_grant_expired")
        if attempt > int(grant["max_restart_attempts"]):
            reasons.append("restart_attempt_limit_exceeded")
        result = {
            "state": "RESTART_AUTHORIZED" if not reasons else "RESTART_REFUSED",
            "grant_id": grant["grant_id"],
            "checkpoint_id": grant["checkpoint_id"],
            "checkpoint_digest": grant["checkpoint_digest"],
            "restart_profile": grant["restart_profile"],
            "attempt": attempt,
            "authorization_digest": _digest({"grant_id": grant["grant_id"], "checkpoint_digest": grant["checkpoint_digest"], "attempt": attempt}),
        }
        return result, reasons

    def evaluate(self, req: PodPreemptReceiptRequest) -> PodPreemptReceiptReceipt:
        reasons: list[str] = []
        if not str(req.subject_id or "").strip():
            reasons.append("subject_id_missing")
        if isinstance(req.budget, bool) or not isinstance(req.budget, (int, float)) or not math.isfinite(float(req.budget)) or float(req.budget) <= self.MIN_BUDGET:
            reasons.append("budget_non_positive_or_invalid")
        payload = req.payload if isinstance(req.payload, dict) else {}
        if not isinstance(req.payload, dict):
            reasons.append("payload_not_object")
        result = None
        try:
            mode = str(payload.get("mode", "preempt")).lower()
            if mode == "preempt":
                result, mode_reasons = self._preempt(payload)
            elif mode == "restart":
                result, mode_reasons = self._restart(payload)
            else:
                raise PreemptError("mode_invalid")
            reasons.extend(mode_reasons)
        except PreemptError as exc:
            reasons.append(str(exc))
        decision = Decision.REFUSE if reasons else Decision.ALLOW
        metrics = {"result": result}
        body = {"subject_id": req.subject_id, "decision": decision.value, "reasons": reasons, "metrics": metrics}
        return PodPreemptReceiptReceipt(decision, tuple(reasons or ["preemption_recovery_receipt_valid"]), _digest(body), metrics)


Mechanism = PodPreemptReceipt
