"""Command-line interface.

    abf record        (info: recording happens via the SDK/proxy, this just shows what's stored)
    abf fingerprint <endpoint> --label baseline --db abf.db
    abf compare <endpoint> --baseline baseline --current current --db abf.db
    abf detect --db abf.db --baseline baseline --current current
    abf explain <endpoint> --baseline baseline --current current --db abf.db
"""

from __future__ import annotations

import argparse
import sys

from .compare import compare_fingerprints
from .models import EndpointFingerprint
from .storage import SQLiteStorage


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="abf", description="API Behavioral Fingerprint CLI.")
    parser.add_argument("--db", default="abf.db")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("record", help="Show recorded endpoints (recording itself happens via SDK/proxy).")

    p_fp = sub.add_parser("fingerprint", help="Compute and store a fingerprint for an endpoint.")
    p_fp.add_argument("endpoint", help="e.g. 'GET /users/{id}'")
    p_fp.add_argument("--label", default="baseline")

    p_compare = sub.add_parser("compare", help="Compare two stored fingerprint labels for an endpoint.")
    p_compare.add_argument("endpoint")
    p_compare.add_argument("--baseline", default="baseline")
    p_compare.add_argument("--current", default="current")

    p_detect = sub.add_parser("detect", help="Run compare across every recorded endpoint.")
    p_detect.add_argument("--baseline", default="baseline")
    p_detect.add_argument("--current", default="current")

    p_explain = sub.add_parser("explain", help="Human-readable drift explanation for one endpoint.")
    p_explain.add_argument("endpoint")
    p_explain.add_argument("--baseline", default="baseline")
    p_explain.add_argument("--current", default="current")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    storage = SQLiteStorage(args.db)

    try:
        if args.command == "record":
            for ep in storage.endpoints():
                print(f"{ep}: {len(storage.observations_for(ep))} observations")

        elif args.command == "fingerprint":
            obs = storage.observations_for(args.endpoint)
            if not obs:
                print(f"No observations for endpoint: {args.endpoint}", file=sys.stderr)
                return 1
            fp = EndpointFingerprint.from_observations(args.endpoint, obs)
            storage.save_fingerprint(fp, args.label)
            print(f"Saved fingerprint '{args.label}' for {args.endpoint} ({fp.sample_count} samples)")

        elif args.command in ("compare", "explain"):
            baseline = storage.get_fingerprint(args.endpoint, args.baseline)
            current = storage.get_fingerprint(args.endpoint, args.current)
            if baseline is None or current is None:
                print("Missing baseline or current fingerprint; run `abf fingerprint` first.", file=sys.stderr)
                return 1
            drifts = compare_fingerprints(baseline, current)
            if not drifts:
                print(f"No drift detected for {args.endpoint}.")
            for d in drifts:
                print(d.explain())

        elif args.command == "detect":
            any_drift = False
            for endpoint in storage.endpoints():
                baseline = storage.get_fingerprint(endpoint, args.baseline)
                current = storage.get_fingerprint(endpoint, args.current)
                if baseline is None or current is None:
                    continue
                for d in compare_fingerprints(baseline, current):
                    any_drift = True
                    print(d.explain())
            if not any_drift:
                print("No drift detected across recorded endpoints.")

        return 0
    finally:
        storage.close()


if __name__ == "__main__":
    raise SystemExit(main())
