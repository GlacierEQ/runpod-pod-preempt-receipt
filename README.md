# Pod Preempt Receipt

Independent GlacierEQ portfolio implementation aligned to **RunPod** operating themes.

> **Not affiliated.** This repository is not affiliated with, endorsed by, employed by, or deployed at RunPod. No proprietary access, production deployment, customer impact, or company partnership is claimed.

## Purpose

Make preemptible GPU termination a recoverable, auditable state transition instead of a pod silently disappearing and an agent guessing where to resume.

## Implemented recovery protocol

`PodPreemptReceipt` supports two phases.

### Preempt

- validates the preemption event and heartbeat freshness;
- considers only checkpoints created before the preemption and marked verified;
- selects the newest verified checkpoint;
- computes lost-work time;
- refuses recovery when heartbeat gaps exceed policy or no verified checkpoint exists;
- mints a deterministic restart grant bound to preempt id, pod, job, checkpoint id/digest, restart profile, expiry, and maximum attempts.

### Restart

- verifies grant integrity;
- requires exact checkpoint lineage;
- rejects expired grants;
- rejects restart attempts beyond the declared limit;
- emits `RESTART_AUTHORIZED` only when every bound remains intact.

## Run

```bash
python -m pytest -q
python scripts/operate.py
```

Build and install:

```bash
python -m pip install build
python -m build
python -m pip install dist/*.whl
pod-preempt-receipt
```

## Proof surface

- `src/pod_preempt_receipt.py` — recovery and restart-grant engine
- `src/pod_preempt_cli.py` — installable execution surface
- `tests/test_pod_preempt_receipt.py` — checkpoint selection, heartbeat, lineage, expiry and retry behavior
- `tests/test_adversarial.py` — fail-closed adversarial coverage
- `.github/workflows/tests.yml` — tests + cold-start + wheel build/install + installed CLI
- `machine/` — existing Helix control-plane and promotion surfaces remain preserved

## Current boundary

The mechanism consumes normalized pod/checkpoint events. It does not control RunPod infrastructure or claim production recovery rates. The next depth step is a disposable worker adapter that persists checkpoints, receives a real termination signal, and proves restart from the emitted grant end-to-end.
