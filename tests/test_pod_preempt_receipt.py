from __future__ import annotations

import hashlib

from pod_preempt_receipt import Decision, PodPreemptReceipt, PodPreemptReceiptRequest


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def checkpoint(cid: str, created: float, *, verified=True, digest=None):
    return {"checkpoint_id": cid, "created_at": created, "state_digest": digest or sha(cid), "uri": f"s3://checkpoints/{cid}", "verified": verified}


def preempt_payload(checkpoints, **event_overrides):
    event = {"preempt_id": "p-1", "pod_id": "pod-7", "reason": "spot-reclaim", "observed_at": 1000.0, "last_heartbeat_at": 990.0}
    event.update(event_overrides)
    return {"mode": "preempt", "event": event, "workload": {"job_id": "train-9", "restart_profile": "gpu-80gb", "max_restart_attempts": 3}, "checkpoints": checkpoints, "restart_window_s": 300.0, "max_heartbeat_gap_s": 60.0}


def evaluate(payload):
    return PodPreemptReceipt().evaluate(PodPreemptReceiptRequest("worker-a", payload, 1.0))


def test_preempt_selects_newest_verified_checkpoint_and_mints_restart_grant() -> None:
    receipt = evaluate(preempt_payload([checkpoint("c1", 800), checkpoint("c2", 950)]))
    assert receipt.decision is Decision.ALLOW
    result = receipt.metrics["result"]
    assert result["state"] == "RECOVERABLE"
    assert result["checkpoint"]["checkpoint_id"] == "c2"
    assert result["lost_work_s"] == 50.0
    assert len(result["restart_grant"]["grant_id"]) == 64


def test_unverified_newer_checkpoint_is_ignored() -> None:
    receipt = evaluate(preempt_payload([checkpoint("good", 900), checkpoint("new-unverified", 980, verified=False)]))
    assert receipt.decision is Decision.ALLOW
    assert receipt.metrics["result"]["checkpoint"]["checkpoint_id"] == "good"


def test_preempt_without_verified_checkpoint_is_explicitly_unrecoverable() -> None:
    receipt = evaluate(preempt_payload([checkpoint("bad", 900, verified=False)]))
    assert receipt.decision is Decision.REFUSE
    assert "verified_checkpoint_missing" in receipt.reasons
    assert receipt.metrics["result"]["state"] == "UNRECOVERABLE"


def test_excessive_heartbeat_gap_refuses_silent_disappearance() -> None:
    receipt = evaluate(preempt_payload([checkpoint("c1", 900)], last_heartbeat_at=800.0))
    assert receipt.decision is Decision.REFUSE
    assert "heartbeat_gap_exceeded" in receipt.reasons


def test_restart_authorized_for_exact_checkpoint_lineage() -> None:
    preempt = evaluate(preempt_payload([checkpoint("c1", 950)]))
    grant = preempt.metrics["result"]["restart_grant"]
    restart = evaluate({"mode": "restart", "restart_grant": grant, "checkpoint_digest": grant["checkpoint_digest"], "now": 1100.0, "attempt": 1})
    assert restart.decision is Decision.ALLOW
    assert restart.metrics["result"]["state"] == "RESTART_AUTHORIZED"


def test_restart_rejects_wrong_checkpoint_lineage() -> None:
    preempt = evaluate(preempt_payload([checkpoint("c1", 950)]))
    grant = preempt.metrics["result"]["restart_grant"]
    restart = evaluate({"mode": "restart", "restart_grant": grant, "checkpoint_digest": sha("different"), "now": 1100.0, "attempt": 1})
    assert restart.decision is Decision.REFUSE
    assert "checkpoint_lineage_mismatch" in restart.reasons


def test_restart_grant_expiry_is_enforced() -> None:
    preempt = evaluate(preempt_payload([checkpoint("c1", 950)]))
    grant = preempt.metrics["result"]["restart_grant"]
    restart = evaluate({"mode": "restart", "restart_grant": grant, "checkpoint_digest": grant["checkpoint_digest"], "now": 1400.0, "attempt": 1})
    assert restart.decision is Decision.REFUSE
    assert "restart_grant_expired" in restart.reasons


def test_restart_attempt_limit_is_enforced() -> None:
    preempt = evaluate(preempt_payload([checkpoint("c1", 950)]))
    grant = preempt.metrics["result"]["restart_grant"]
    restart = evaluate({"mode": "restart", "restart_grant": grant, "checkpoint_digest": grant["checkpoint_digest"], "now": 1100.0, "attempt": 4})
    assert restart.decision is Decision.REFUSE
    assert "restart_attempt_limit_exceeded" in restart.reasons
