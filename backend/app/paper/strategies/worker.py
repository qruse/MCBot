"""Short-lived stdlib-only runner; process isolation is NOT an OS security sandbox."""

import contextlib
import io
import json
import sys


class Discard(io.TextIOBase):
    def write(self, text):
        return len(text)


def main():
    payload = json.loads(sys.stdin.read(4_000_000))
    namespace = {"__name__": "strategy_module"}
    try:
        with contextlib.redirect_stdout(Discard()), contextlib.redirect_stderr(Discard()):
            exec(compile(payload["source"], "<strategy>", "exec"), namespace)
            result = namespace["decide"](payload["context"])
        encoded = json.dumps(result, allow_nan=False)
        if len(encoded) > 32768:
            raise ValueError("oversized_output")
        sys.stdout.write(encoded)
    except BaseException:
        # Code exceptions may contain filesystem or credential data; never return their text.
        sys.stdout.write('{"worker_error":"strategy_execution_failed"}')
        sys.exit(1)


if __name__ == "__main__":
    main()
