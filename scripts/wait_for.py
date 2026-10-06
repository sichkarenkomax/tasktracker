"""Wait until a URL answers successfully.

`docker compose up -d` returns as soon as the containers are *created*, not
when the stack can serve traffic, so an immediate `curl http://localhost/health`
fails with a connection refused or a 502 from Caddy even though the deployment
is perfectly fine. This script polls until the endpoint is ready and gives up
with a readable message instead of a stack trace.

    python scripts/wait_for.py http://localhost/health/ready

Point it at a health or API endpoint, not at a UI route: Caddy answers unknown
paths with the SPA's index.html, so any application path returns HTTP 200 even
when the backend is not ready.

Standard library only - it has to work before any virtualenv exists.
"""

from __future__ import annotations

import argparse
import sys
import time
import urllib.error
import urllib.request

DEFAULT_TIMEOUT = 180.0
DEFAULT_INTERVAL = 1.0


class WaitTimeoutError(Exception):
    """The endpoint did not become ready in time."""


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Poll a URL until it responds with a success status.",
    )
    parser.add_argument(
        "url",
        help="endpoint to poll, e.g. http://localhost/health/ready",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help=f"seconds to wait before giving up (default: {DEFAULT_TIMEOUT:g})",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=DEFAULT_INTERVAL,
        help=f"seconds between attempts (default: {DEFAULT_INTERVAL:g})",
    )
    return parser.parse_args(argv)


def probe(url: str) -> tuple[bool, str]:
    """One attempt. Returns (ready, detail for the log)."""
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status < 400, f"HTTP {response.status}"
    except urllib.error.HTTPError as exc:
        # A 503 from a health endpoint is a perfectly normal intermediate state:
        # the process is up but its dependency is not ready yet.
        return False, f"HTTP {exc.code}"
    except urllib.error.URLError:
        # The underlying reason is deliberately dropped: on Windows it arrives
        # in the console's legacy code page and prints as mojibake, and the
        # remedy is the container logs either way.
        return False, "unreachable"
    except TimeoutError:
        return False, "timed out"


def wait(url: str, *, timeout: float, interval: float) -> None:
    deadline = time.monotonic() + timeout
    attempts = 0
    detail = "no attempt"
    while True:
        attempts += 1
        ready, detail = probe(url)
        if ready:
            print(f"ready: {url} after {attempts} attempt(s), {detail}")
            return
        if time.monotonic() >= deadline:
            raise WaitTimeoutError(
                f"{url} did not become ready in {timeout:g}s ({attempts} attempts, last: {detail})"
            )
        time.sleep(interval)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        wait(args.url, timeout=args.timeout, interval=args.interval)
    except WaitTimeoutError as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        print(
            "Check what the stack is doing: docker compose logs -f",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
