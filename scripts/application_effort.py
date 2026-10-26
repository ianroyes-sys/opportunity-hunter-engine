#!/usr/bin/env python3
"""Durable application cooldowns. Never edits tracker, submissions, or candidate files.

Keys must identify the candidate URL/ID AND application cycle, not an organization.
Release only on the user's explicit request or a verified changed fact under engine policy.
An active defer is idempotent: repeated passes cannot move its retry time forward.
"""

import argparse
import contextlib
from datetime import datetime, timedelta, timezone
import fcntl
import json
import os
from pathlib import Path
import tempfile


REASONS = {"manual-heavy", "user-action", "no-progress", "time-budget"}
DEFAULT_ROOT = Path(__file__).resolve().parents[1]


def stamp(now):
    return now.astimezone(timezone.utc).isoformat()


def parse_stamp(value):
    if not isinstance(value, str):
        raise ValueError("Invalid timestamp")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("Timestamp needs timezone")
    return parsed


def valid_text(value, limit, label):
    if (not isinstance(value, str) or not value.strip() or len(value) > limit
            or any(ord(char) < 32 for char in value)):
        raise ValueError(f"Invalid {label}")
    return value


def validate_record(key, record, maximum_revision):
    valid_text(key, 2048, "candidate key")
    if not isinstance(record, dict) or record.get("key") != key:
        raise ValueError("Invalid deferral record")
    if record.get("reason") not in REASONS:
        raise ValueError("Invalid deferral reason")
    valid_text(record.get("detail"), 1000, "detail")
    started = parse_stamp(record.get("deferredAt"))
    if parse_stamp(record.get("retryAt")) <= started:
        raise ValueError("Invalid retry time")
    if record.get("releasedAt") is not None:
        parse_stamp(record["releasedAt"])
    if type(record.get("revision")) is not int or not 1 <= record["revision"] <= maximum_revision:
        raise ValueError("Invalid record revision")


def validate(state):
    if (not isinstance(state, dict) or type(state.get("version")) is not int or state.get("version") != 1
            or type(state.get("revision")) is not int or state["revision"] < 0
            or not isinstance(state.get("records"), dict)
            or not isinstance(state.get("history"), list)):
        raise ValueError("Corrupt deferral state; refusing to reset it")
    for key, record in state["records"].items():
        validate_record(key, record, state["revision"])
    if len(state["history"]) != state["revision"]:
        raise ValueError("Invalid history length")
    latest = {}
    for number, event in enumerate(state["history"], 1):
        if not isinstance(event, dict) or event.get("revision") != number or event.get("action") not in {"defer", "release"}:
            raise ValueError("Invalid history event")
        valid_text(event.get("key"), 2048, "history key")
        parse_stamp(event.get("at"))
        validate_record(event["key"], event.get("record"), number)
        if event["record"]["revision"] != number:
            raise ValueError("Invalid history snapshot revision")
        latest[event["key"]] = event["record"]
    if latest != state["records"]:
        raise ValueError("History does not match current records")
    return state


def state_path(root):
    return Path(root) / "pipeline" / "APPLICATION-DEFERRALS.json"


def read_state(root):
    path = state_path(root)
    if not path.exists():
        return {"version": 1, "revision": 0, "records": {}, "history": []}
    return validate(json.loads(path.read_text()))


def active(record, now):
    return record is not None and record.get("releasedAt") is None and parse_stamp(record["retryAt"]) > now


def check(root, key, now=None):
    valid_text(key, 2048, "candidate key")
    now = now or datetime.now(timezone.utc)
    record = read_state(root)["records"].get(key)
    return {"key": key, "deferred": active(record, now), "retryAt": record["retryAt"] if record else None,
            "record": record}


def list_active(root, now=None):
    now = now or datetime.now(timezone.utc)
    state = read_state(root)
    return {"revision": state["revision"], "records": sorted(
        (record for record in state["records"].values() if active(record, now)),
        key=lambda record: (record["retryAt"], record["key"]))}


def mutate(root, key, action, reason=None, detail=None, minutes=1440, now=None):
    valid_text(key, 2048, "candidate key")
    if action not in {"defer", "release"}:
        raise ValueError("Invalid action")
    if action == "defer":
        if reason not in REASONS:
            raise ValueError("Invalid reason")
        valid_text(detail, 1000, "detail")
        if type(minutes) is not int or not 1 <= minutes <= 525600:
            raise ValueError("Minutes must be between 1 and 525600")
    now = now or datetime.now(timezone.utc)
    path = state_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(".lock")
    with lock_path.open("a+") as lock:
        os.chmod(lock_path, 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = read_state(root)
        previous = state["records"].get(key)
        if ((action == "defer" and active(previous, now)) or
                (action == "release" and (previous is None or previous.get("releasedAt") is not None))):
            return {"changed": False, "revision": state["revision"], "record": previous}
        state["revision"] += 1
        if action == "defer":
            record = {"key": key, "reason": reason, "detail": detail, "deferredAt": stamp(now),
                      "retryAt": stamp(now + timedelta(minutes=minutes)), "releasedAt": None,
                      "revision": state["revision"]}
        else:
            record = {**previous, "releasedAt": stamp(now), "revision": state["revision"]}
        state["records"][key] = record
        state["history"].append({"action": action, "key": key, "at": stamp(now),
                                 "revision": state["revision"], "record": dict(record)})
        validate(state)
        descriptor, temporary = tempfile.mkstemp(prefix=".application-deferrals-", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(descriptor, "w") as output:
                json.dump(state, output, indent=2)
                output.write("\n")
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, path)
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(temporary)
        return {"changed": True, "revision": state["revision"], "record": record}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list")
    for command in ("check", "defer", "release"):
        sub = commands.add_parser(command)
        sub.add_argument("--key", required=True, help="Canonical candidate URL/ID plus application cycle")
        if command == "defer":
            sub.add_argument("--reason", required=True, choices=sorted(REASONS))
            sub.add_argument("--detail", required=True)
            sub.add_argument("--minutes", type=int, default=1440)
    args = parser.parse_args()
    try:
        if args.command == "list":
            result = list_active(args.root)
        elif args.command == "check":
            result = check(args.root, args.key)
        else:
            result = mutate(args.root, args.key, args.command, getattr(args, "reason", None),
                            getattr(args, "detail", None), getattr(args, "minutes", 1440))
        print(json.dumps(result))
        return 0
    except (ValueError, OSError, TypeError, OverflowError) as error:
        print(json.dumps({"error": str(error), "deferred": True,
                          "failClosed": True, "action": "Do not attempt candidates until state is repaired"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
