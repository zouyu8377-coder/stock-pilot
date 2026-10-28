"""Explicitly authorized one-off review; does not persist budget settings."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--authorized-extra-review", action="store_true")
    args = parser.parse_args()
    if not args.authorized_extra_review:
        parser.error("This live check requires explicit authorization for one extra review (at most two model requests).")
    from app.agent_review import runtime, service
    if runtime.status().get("status") in {"running", "cancelling"}:
        raise RuntimeError("Another task is running; do not start a concurrent validation")
    # Manual requests are quota-exempt; keep normal automatic settings untouched.
    result = service.generate_daily_review(force_context=True)
    print(json.dumps({"run_id": result["run_id"], "status": result["status"],
                      "usage": result["usage"], "elapsed_ms": result["elapsed_ms"],
                      "validation_warnings": result["validation_warnings"]}, ensure_ascii=False))
