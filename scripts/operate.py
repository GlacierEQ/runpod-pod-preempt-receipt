#!/usr/bin/env python3
"""Cold-start a real checkpoint-bound preemption recovery receipt."""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from pod_preempt_cli import main
if __name__ == "__main__":
    raise SystemExit(main())
