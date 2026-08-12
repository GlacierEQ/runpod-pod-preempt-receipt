from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from pod_preempt_receipt import Decision, PodPreemptReceipt, PodPreemptReceiptRequest


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def demo_payload() -> dict:
    return {
        "mode": "preempt",
        "event": {"preempt_id": "preempt-1", "pod_id": "pod-7", "reason": "spot-reclaim", "observed_at": 1000.0, "last_heartbeat_at": 990.0},
        "workload": {"job_id": "train-9", "restart_profile": "gpu-80gb", "max_restart_attempts": 3},
        "checkpoints": [{"checkpoint_id": "ckpt-42", "created_at": 950.0, "state_digest": _sha("ckpt-42"), "uri": "file:///tmp/ckpt-42", "verified": True}],
        "restart_window_s": 300.0,
        "max_heartbeat_gap_s": 60.0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Emit or verify a checkpoint-bound pod preemption recovery receipt")
    parser.add_argument("--input", type=Path, help="JSON payload; defaults to a deterministic preemption demo")
    parser.add_argument("--subject", default="pod-preempt-demo")
    args = parser.parse_args()
    payload = json.loads(args.input.read_text()) if args.input else demo_payload()
    receipt = PodPreemptReceipt().evaluate(PodPreemptReceiptRequest(args.subject, payload, 1.0))
    print(json.dumps(receipt.as_dict(), indent=2, sort_keys=True))
    return 0 if receipt.decision is Decision.ALLOW else 2


if __name__ == "__main__":
    raise SystemExit(main())
