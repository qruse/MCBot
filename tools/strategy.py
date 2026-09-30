"""Local strategy development: scaffold, validate, register, replay, feedback, rollback."""

import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=["scaffold", "validate", "register", "replay", "list", "feedback", "rollback"],
    )
    parser.add_argument("value", nargs="?")
    parser.add_argument("--version", type=int, default=1)
    parser.add_argument("--from-ref", default="theme-top3-v1@1")
    parser.add_argument(
        "--workspace",
        default=str(Path(__file__).resolve().parents[1] / "runtime" / "strategy_workspace"),
    )
    parser.add_argument("--evaluation-id")
    parser.add_argument("--session-id")
    parser.add_argument("--expected-policy-version", type=int)
    parser.add_argument("--reason")
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    args = parser.parse_args()

    def request(path, body=None):
        url = args.api.rstrip("/") + "/paper/" + path
        command = urllib.request.Request(
            url,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Content-Type": "application/json", "X-MCBot-Command": "local-paper"},
        )
        with urllib.request.urlopen(command, timeout=240) as response:
            return json.load(response)

    if args.action == "scaffold":
        if (
            not args.value
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", args.value)
            or args.version < 1
        ):
            raise ValueError("Supply a valid strategy ID and positive version")
        parent = request("strategies/source?" + urllib.parse.urlencode({"ref": args.from_ref}))
        directory = Path(args.workspace).resolve() / args.value / str(args.version)
        directory.mkdir(parents=True, exist_ok=False)
        manifest = {
            "strategy_id": args.value,
            "version": args.version,
            "parent_ref": args.from_ref,
            "name": args.value,
            "hypothesis": "TODO: evidence-backed change hypothesis",
            "failure_criterion": "TODO: measurable failure and rollback criterion",
        }
        (directory / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        (directory / "strategy.py").write_text(parent["source"], encoding="utf-8")
        result = {
            "directory": str(directory),
            "next": "Edit strategy.py and manifest.json, then validate.",
        }
    elif args.action in ("validate", "register"):
        if not args.value:
            raise ValueError("Supply the strategy workspace directory")
        directory = Path(args.value)
        draft = json.loads((directory / "manifest.json").read_text(encoding="utf-8-sig"))
        draft["source"] = (directory / "strategy.py").read_text(encoding="utf-8-sig")
        if args.action == "validate":
            result = request("strategies/validate", draft)
            (directory / "validation.json").write_text(
                json.dumps(result, indent=2), encoding="utf-8"
            )
        else:
            evaluation = (
                args.evaluation_id or json.loads((directory / "validation.json").read_text())["id"]
            )
            result = request("strategies/register", {"draft": draft, "evaluation_id": evaluation})
    elif args.action == "replay":
        if not args.value or not args.session_id:
            raise ValueError("Supply a strategy reference and --session-id")
        result = request(
            "strategies/replay", {"strategy_ref": args.value, "session_id": args.session_id}
        )
    elif args.action == "rollback":
        if (
            not args.value
            or not args.reason
            or not args.session_id
            or args.expected_policy_version is None
        ):
            raise ValueError(
                "Supply target reference, --reason, --session-id and --expected-policy-version"
            )
        result = request(
            "strategies/rollback",
            {
                "command_id": uuid.uuid4().hex,
                "session_id": args.session_id,
                "expected_policy_version": args.expected_policy_version,
                "target_ref": args.value,
                "reason": args.reason,
            },
        )
    else:
        result = request("strategies")
        if args.action == "feedback":
            result = {"feedback": result["feedback"], "evaluations": result["evaluations"]}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except urllib.error.HTTPError as error:
        print(error.read().decode(), file=sys.stderr)
        sys.exit(1)
    except (OSError, ValueError, urllib.error.URLError) as error:
        print(json.dumps({"error": str(error)}), file=sys.stderr)
        sys.exit(1)
