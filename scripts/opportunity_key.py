#!/usr/bin/env python3
"""Print the engine's canonical candidate identity without reading or writing state."""
import argparse
import importlib.util
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="Official URL, requisition ID, or URL|cycle key")
    parser.add_argument("--cycle", help="Optional explicit application cycle")
    args = parser.parse_args()
    if not args.url.strip() or (args.cycle is not None and not args.cycle.strip()):
        parser.error("URL/key and supplied cycle must not be empty")
    if args.cycle is not None and "|" in args.url:
        parser.error("Supply the cycle in the key or with --cycle, not both")
    engine = Path(__file__).resolve().parents[1] / "engine/opportunity_engine.py"
    if not engine.is_file():
        parser.error("Canonical engine module is unavailable; no fallback key invented")
    spec = importlib.util.spec_from_file_location("opportunity_engine_keys", engine)
    module = importlib.util.module_from_spec(spec)
    sys.dont_write_bytecode = True
    spec.loader.exec_module(module)
    value = args.url + ("|" + args.cycle if args.cycle is not None else "")
    print(module.canonical(value))


if __name__ == "__main__":
    main()
