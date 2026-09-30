"""Restricted exchange client: context, claim, submit, receipt. No trading commands."""

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["context", "claim", "submit", "receipt", "schema"])
    parser.add_argument("value", nargs="?")
    parser.add_argument(
        "--exchange",
        default=str(Path(__file__).resolve().parents[1] / "runtime" / "agent_exchange"),
    )
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument("--manual-reason", help="Only for an explicit owner-requested review")
    parser.add_argument("--session-id")
    parser.add_argument("--expected-policy-version", type=int)
    args = parser.parse_args()
    if args.manual_reason is not None and (
        args.action != "claim" or not args.session_id or args.expected_policy_version is None
    ):
        raise ValueError("Manual claim requires session ID and expected policy version")
    root = Path(args.exchange).resolve()
    if args.action in ("claim", "schema"):
        run_id = args.value or uuid.uuid4().hex
        if args.action == "claim" and not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", run_id):
            raise ValueError("Invalid run ID")
        request = urllib.request.Request(
            args.api.rstrip("/") + "/paper/research/" + args.action,
            data=json.dumps(
                {
                    "run_id": run_id,
                    **(
                        {
                            "manual_reason": args.manual_reason,
                            "session_id": args.session_id,
                            "expected_policy_version": args.expected_policy_version,
                        }
                        if args.manual_reason is not None
                        else {}
                    ),
                }
            ).encode()
            if args.action == "claim"
            else None,
            headers={"Content-Type": "application/json", "X-MCBot-Command": "local-paper"},
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            print(response.read().decode())
    elif args.action == "context":
        manifest = json.loads((root / "latest.json").read_text(encoding="utf-8"))
        snapshot_id = manifest["snapshot_id"]
        if not re.fullmatch(r"[a-f0-9]{32}", snapshot_id):
            raise ValueError("Invalid snapshot ID")
        raw = (root / "exports" / snapshot_id / "context.json").read_bytes()
        if hashlib.sha256(raw).hexdigest() != manifest["sha256"]:
            raise ValueError("Context hash mismatch")
        print(raw.decode("utf-8"))
    elif args.action == "submit":
        if not args.value:
            raise ValueError("Supply a proposal JSON path")
        raw = Path(args.value).read_bytes()
        if len(raw) > 65536:
            raise ValueError("Proposal exceeds 64 KiB")
        value = json.loads(raw.decode("utf-8-sig"))
        proposal_id = value.get("proposal_id", "")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", proposal_id):
            raise ValueError("Invalid proposal ID")
        destination = root / "inbox" / f"{proposal_id}.json"
        temporary = root / "inbox" / f"{proposal_id}-{uuid.uuid4().hex}.tmp"
        temporary.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        os.replace(temporary, destination)
        print(
            json.dumps(
                {
                    "proposal_id": proposal_id,
                    "status": "submitted",
                    "next": "Read receipt; submission is not acceptance.",
                }
            )
        )
    else:
        if not args.value or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", args.value):
            raise ValueError("Supply a valid proposal ID")
        path = root / "receipts" / f"{args.value}.json"
        print(path.read_text(encoding="utf-8") if path.exists() else '{"status":"pending"}')


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, urllib.error.URLError) as error:
        print(json.dumps({"error": str(error)}), file=sys.stderr)
        sys.exit(1)
