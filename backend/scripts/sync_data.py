"""Headless objective-data sync. No web server, model key or frontend required."""
import argparse
import json
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
# Existing services use relative data paths; do not let the launch directory choose a different account.
os.chdir(BACKEND)
os.environ["STOCK_PILOT_DATA_ONLY"] = "1"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="Bypass collection TTLs")
    names = ["cold", "market", "references", "disclosures", "rotation", "breadth", "public", "backfill"]
    parser.add_argument("--stages", nargs="+", choices=names)
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--prepare-discussion", action="store_true", help="Explicitly refresh handoff after sync, preserving pending results")
    parser.add_argument("--worker", choices=names, help=argparse.SUPPRESS)
    args = parser.parse_args()
    from app.data_sync import service
    try:
        if args.worker:
            service.worker(args.worker)
            return 0
        if args.status:
            result = service.load_status()
        else:
            result = service.run(force=args.force, stages=args.stages)
            if args.prepare_discussion:
                handoff = service.prepare_discussion()
                result["discussion_manifest"] = handoff["manifest"]
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if args.status:
            return 0
        return 0 if result.get("status") in {"complete", "never_run"} else 2
    except BlockingIOError as exc:
        print(json.dumps({"status": "already_running", "reason": str(exc)}))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "failed", "reason": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
