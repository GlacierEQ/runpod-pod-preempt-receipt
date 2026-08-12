# DEV_UP_INSTRUCTIONS — implementation record

**Repository:** `GlacierEQ/runpod-pod-preempt-receipt`  
**Independent company lens:** RunPod  
**Innovation:** Pod Preempt Receipt

## Mission

Turn preemptible GPU loss into an explicit checkpoint-bound recovery transition with verifiable restart authority.

## Implemented

The generic scaffold has been replaced by a two-phase preemption/restart protocol.

`src/pod_preempt_receipt.py` now:

- validates preemption and heartbeat evidence;
- selects the newest verified checkpoint created before termination;
- ignores unverified checkpoints;
- reports lost work and unrecoverable conditions explicitly;
- mints deterministic restart grants bound to checkpoint lineage, job/pod identity, expiry and attempt limits;
- verifies grant integrity and exact checkpoint digest at restart;
- refuses expired grants and excessive restart attempts;
- emits deterministic recovery and authorization receipts.

`src/pod_preempt_cli.py` and `scripts/operate.py` execute the protocol directly. The project is packaged with the `pod-preempt-receipt` console command.

## Verification contract

Behavioral tests cover newest verified checkpoint selection, ignoring unverified checkpoints, unrecoverable preemption, stale heartbeat, valid restart, lineage mismatch, grant expiry and restart-attempt limits. Existing adversarial coverage remains active.

CI must pass tests, cold-start, wheel build/install and installed CLI execution before Helix promotion evidence can be minted.

## Truth boundary

No RunPod affiliation, proprietary access, production deployment, customer impact, or company partnership is claimed. A real disposable worker/checkpoint adapter remains the next end-to-end depth step.
