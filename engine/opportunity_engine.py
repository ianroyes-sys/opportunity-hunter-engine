#!/usr/bin/env python3
"""Opportunity Engine v2: deterministic intake, selection and evidence-backed outcomes.

No network, browser, model or external writes. Historical Markdown is an import, not
the scheduler. Structured outcomes are serialized under a filesystem lock. Missing
or corrupt policy is never silently replaced. Old submissions are never replayed.
"""
from __future__ import annotations

import argparse
import contextlib
import csv
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

VERSION = 2
STATES = {"verified", "needs-browser", "deferred", "skipped", "submitted", "unverified", "closed"}
TERMINAL = {"submitted", "closed", "skipped"}


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def clean(s):
    return re.sub(r"\s+", " ", re.sub(r"[*`]", "", str(s))).strip()


def norm(s):
    return re.sub(r"[^a-z0-9]+", "-", clean(s).lower()).strip("-")


def url_key(value):
    value = clean(value).rstrip(".,;")
    u = urlsplit(value)
    if u.scheme not in ("http", "https") or not u.netloc:
        return value
    query = [(k, v) for k, v in parse_qsl(u.query, keep_blank_values=True)
             if not k.lower().startswith("utm_") and k.lower() not in {"fbclid", "gclid", "ref", "source", "embed"}]
    return urlunsplit(("https", u.netloc.lower().removeprefix("www."), u.path.rstrip("/") or "/", urlencode(sorted(query)), ""))


def canonical(value):
    parts = clean(value).split("|")
    return "|".join([url_key(parts[0]), *[p.strip().lower() for p in parts[1:]]])


def urls(raw):
    return [u.rstrip(".,;:") for u in re.findall(r"https?://[^\s<>\]\[)`|]+", raw)]


def read_json(path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except (ValueError, OSError) as exc:
        raise ValueError(f"Cannot read {path.name}; preserving it: {exc}") from exc


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as out:
            json.dump(value, out, indent=2, ensure_ascii=False)
            out.write("\n")
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


@contextlib.contextmanager
def locked(root):
    folder = root / "pipeline"
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / ".engine.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def fields(raw):
    out = {}
    for line in raw.splitlines():
        m = re.match(r"^(?:-\s+)?(?:\*\*)?([^:*]+):(?:\*\*)?\s*(.*)$", line)
        if m:
            out.setdefault(m[1].strip().lower(), clean(m[2]))
    return out


def status(raw):
    """Parse actual status, not incidental 'not submitted' in prose."""
    s = clean(raw).lower()
    if re.match(r"(?:unverified|verify.application)\b|submit.*(?:uncertain|unconfirmed)", s):
        return "unverified"
    if re.match(r"(?:submitted|applied|accepted|won|interview)\b", s):
        return "submitted"
    if re.match(r"(?:expired|rejected|withdrawn|closed|ineligible)\b", s):
        return "closed"
    if re.match(r"(?:skipped|user.skipped)\b", s):
        return "skipped"
    if re.search(r"\bwatchlist\b|future.dated|no live requisition|not (?:yet )?open|waiting for.*posting", s):
        return "deferred"
    if re.search(r"\b(blocked|held|deferred|awaiting|needs.ian|recommender.gated|transcript.gated)\b", s):
        return "deferred"
    if re.match(r"(?:vetted|verified|materials.ready|preparing|review.ready)\b", s):
        return "verified"
    if re.match(r"(?:found|new|needs.browser|form.in.progress)\b", s):
        return "needs-browser"
    return "unknown"


def cells(line):
    return [x.strip() for x in re.split(r"(?<!\\)\|", line.strip().strip("|"))]


def tracker_records(root):
    path = root / "pipeline/tracker.md"
    result = {}
    if not path.exists():
        return result
    for line in path.read_text().splitlines():
        if not line.startswith("|"):
            continue
        row = cells(line)
        links = re.findall(r"(?:opportunities/)([^)\s]+\.md)", line)
        if len(row) >= 7:
            for name in links:
                # Topmost current row outranks duplicates in historical audits.
                result.setdefault(name, {"name": clean(row[0]), "category": clean(row[1]),
                                         "deadline": clean(row[2]), "status": clean(row[5])})
    return result


def import_records(root):
    records = []
    tracker = tracker_records(root)
    ledger_path = root / "pipeline/SUBMISSIONS.md"
    ledger = ledger_path.read_text() if ledger_path.exists() else ""
    ledger_urls = {url_key(u) for u in urls(ledger) if len(urlsplit(u).path) > 1}
    ledger_titles = {norm(cells(l)[1]) for l in ledger.splitlines() if l.startswith("|") and len(cells(l)) >= 6}
    blocked_path = root / "pipeline/BLOCKED.md"
    blocked = blocked_path.read_text() if blocked_path.exists() else ""
    wall_names = [norm(m[1]) for m in re.finditer(r"^###\s+(.+)$", blocked, re.M)]
    for path in sorted((root / "pipeline/opportunities").glob("*.md")):
        raw = path.read_text(errors="replace")
        f = fields(raw)
        row = tracker.get(path.name, {})
        title = re.search(r"^#\s+(.+)$", raw, re.M)
        name = clean(title[1] if title else row.get("name", path.stem))
        source = next(iter(urls(f.get("source", "") or f.get("official source", "") or f.get("official url", "") or f.get("portal url", "") or f.get("url", "") or raw)), "")
        key = canonical(f.get("candidate key", "")) or (url_key(source) + "|" + path.stem if source else "record|" + path.stem)
        rstatus, tstatus = status(f.get("status", "")), status(row.get("status", ""))
        state = rstatus if rstatus != "unknown" else tstatus
        if "submitted" in (rstatus, tstatus):
            state = "submitted"
        elif "unverified" in (rstatus, tstatus):
            state = "unverified"
        elif "skipped" in (rstatus, tstatus):
            state = "skipped"
        elif "closed" in (rstatus, tstatus):
            state = "closed"
        elif "deferred" in (rstatus, tstatus):
            state = "deferred"
        # Ledger URLs are checked conservatively: role-specific paths only.
        duplicate = (source and len(urlsplit(source).path) > 12 and url_key(source) in ledger_urls) or norm(name) in ledger_titles
        if duplicate and state not in {"submitted", "closed"}:
            state = "unverified"
        title_key = norm(name)
        has_wall = any(title_key == w or (len(title_key) > 18 and title_key in w) or
                       (len(norm(path.stem)) > 18 and norm(path.stem) in w) for w in wall_names)
        if has_wall and state in {"verified", "needs-browser", "unknown"}:
            state = "deferred"
        deadline = f.get("deadline", row.get("deadline", "unknown"))
        if state in {"verified", "needs-browser"} and re.search(r"no (?:eligible|live|full.time).*?(?:posted|requisition|confirmed)|no.*requisition.*posted|not open|waiting for.*posting", deadline, re.I):
            state = "deferred"
        reason = ("Possible prior submission in ledger; verify portal before any action" if duplicate and state == "unverified"
                  else clean(f.get("status", row.get("status", "No machine-readable status"))))
        if has_wall and state == "deferred":
            reason = "Existing named wall; saved facts or current requirements must change before retry"
        if not source and state in {"verified", "needs-browser"}:
            state, reason = "unknown", "No official application URL on record"
        records.append({"key": key, "name": name, "state": state, "reason": reason[:350],
                        "sourceUrl": source, "recordPath": str(path.relative_to(root)),
                        "category": f.get("category", row.get("category", "unknown")),
                        "deadline": deadline,
                        "effort": "unknown", "origin": "legacy", "aliases": [path.stem, url_key(source)]})
    return records


def import_career(root, existing):
    """Cross-ledger outcomes protect against duplicate applications across workflows."""
    result = []
    for filename in ("APPLICATION_HISTORY.csv", "JOB_TRACKER.csv"):
        path = root / "career-ledger" / filename
        if not path.exists():
            continue
        with path.open(newline="") as stream:
            for row in csv.DictReader(stream):
                source = row.get("job_url", "")
                state = status(row.get("status", ""))
                if not source or state not in {"submitted", "unverified", "closed", "deferred"}:
                    continue
                same = next((c for c in existing + result if url_key(c["sourceUrl"]) == url_key(source)), None)
                if same:
                    if state == "submitted":
                        same.update(state="submitted", reason="Historical career application ledger; do not resubmit")
                    elif state == "unverified" and same["state"] != "submitted":
                        same.update(state="unverified", reason="Career workflow flags uncertain submission; reconcile portal")
                    continue
                result.append({"key": url_key(source) + "|career-ledger", "name": clean(row.get("company", "") + " — " + row.get("role", "")),
                               "sourceUrl": source, "state": state, "reason": "Historical career workflow: " + row.get("status", ""),
                               "recordPath": str(path.relative_to(root)), "category": "full-time / new-grad", "deadline": "unknown", "effort": "unknown", "origin": "career-ledger", "aliases": [url_key(source)]})
    return result


def import_inbox(root, existing):
    path = root / "pipeline/HUNT-INBOX.md"
    if not path.exists():
        return [], 0
    # Parse table records only. Megabytes of repeated search narration never enter prompts.
    seen_urls = {url_key(c["sourceUrl"]) for c in existing if c.get("sourceUrl")}
    seen_names = {norm(c["name"]) for c in existing}
    items, total = [], 0
    for line in path.read_text(errors="replace").splitlines():
        if not line.startswith("|"):
            continue
        row = cells(line)
        if len(row) < 8 or clean(row[0]).lower() not in {"new", "needs-browser"}:
            continue
        total += 1
        source = next(iter(urls(row[4])), "")
        if not source or url_key(source) in seen_urls or norm(row[1]) in seen_names:
            continue
        name = clean(row[1])
        key = url_key(source) + "|legacy-intake"
        items.append({"key": key, "name": name, "state": "needs-browser", "sourceUrl": source,
                      "reason": "Legacy intake requires current-source/eligibility verification: " + clean(row[6] + " " + row[7])[:250],
                      "recordPath": "pipeline/HUNT-INBOX.md", "category": clean(row[2]), "deadline": clean(row[3]),
                      "effort": "unknown", "origin": "legacy-inbox", "aliases": [url_key(source)]})
        seen_urls.add(url_key(source))
        seen_names.add(norm(name))
    return items, total


def timestamp(value):
    try:
        if isinstance(value, (int, float)):
            return float(value)
        return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError):
        return 0


def matches(c, key):
    key = canonical(key)
    return key == c["key"] or key in c.get("aliases", []) or ("|" not in key and key == url_key(c.get("sourceUrl", "")))


def due(c, current=None):
    current = current if current is not None else dt.datetime.now(dt.timezone.utc).timestamp()
    return c["state"] in {"verified", "needs-browser", "unverified"} and not (c.get("retryAt") and timestamp(c["retryAt"]) > current)


def snapshot(root, omega):
    pipeline = root / "pipeline"
    warnings = []
    config = read_json(pipeline / "CATEGORIES.json", {"categories": {}})
    overrides = read_json(pipeline / "ENGINE-OUTCOMES.json", {"version": VERSION, "records": {}})
    intake = read_json(pipeline / "ENGINE-INTAKE.json", {"version": VERSION, "candidates": {}})
    skips = read_json(pipeline / "USER-SKIPS.json", {"version": 1, "candidates": []})
    deferrals = read_json(pipeline / "APPLICATION-DEFERRALS.json", {"records": {}})
    recovery = read_json(omega / "loops/state/opportunity.recovery.json", {})
    for label, obj, field in [("categories", config, "categories"), ("outcomes", overrides, "records"),
                              ("intake", intake, "candidates"), ("deferrals", deferrals, "records")]:
        if not isinstance(obj, dict) or not isinstance(obj.get(field), dict):
            raise ValueError(f"Invalid {label} schema; refusing queue selection")
        if any(not isinstance(v, dict) for v in obj[field].values()):
            raise ValueError(f"Invalid nested {label} schema; refusing queue selection")
    if not isinstance(skips, dict) or not isinstance(skips.get("candidates"), list):
        raise ValueError("Invalid user skip schema")
    if any(not isinstance(v, dict) or not isinstance(v.get("keys"), list) or not v.get("reason") for v in skips["candidates"]):
        raise ValueError("Invalid user skip entries")
    if any(not isinstance(v.get("enabled", True), bool) or not isinstance(v.get("keywords", []), list)
           or any(not isinstance(w, str) for w in v.get("keywords", [])) for v in config["categories"].values()):
        raise ValueError("Invalid category enabled/keywords policy")
    if not isinstance(recovery, dict) or not isinstance(recovery.get("candidateCooldowns", {}), dict) or any(
            not isinstance(v, dict) for v in recovery.get("candidateCooldowns", {}).values()):
        raise ValueError("Invalid recovery cooldown schema")
    if not isinstance(recovery.get("uncertainSubmissions", {}), dict) or any(
            not isinstance(v, dict) for v in recovery.get("uncertainSubmissions", {}).values()):
        raise ValueError("Invalid uncertain submission recovery schema")
    candidates = import_records(root)
    record_count = len(candidates)
    candidates += import_career(root, candidates)
    inbox, inbox_count = import_inbox(root, candidates)
    candidates += inbox
    for c in intake["candidates"].values():
        if not any(matches(old, c["key"]) or url_key(old.get("sourceUrl", "")) == url_key(c["sourceUrl"]) for old in candidates):
            candidates.append(dict(c))
    current = dt.datetime.now(dt.timezone.utc).timestamp()
    for c in candidates:
        prior = next((v for k, v in overrides["records"].items() if matches(c, k)), None)
        if prior and c["state"] != "submitted":
            c.update({k: v for k, v in prior.items() if k in {"state", "reason", "updatedAt", "evidence", "confirmation", "retryAt"}})
        uncertain = next((v for k, v in recovery.get("uncertainSubmissions", {}).items() if matches(c, k)), None)
        if uncertain and c["state"] != "submitted":
            resolved = prior and prior.get("state") != "unverified" and prior.get("evidence") and prior.get("confirmation") and timestamp(prior.get("updatedAt")) > timestamp(uncertain.get("at"))
            if not resolved:
                c.update(state="unverified", reason="Interrupted after submit started; reconcile portal evidence, never blind resend")
                if not c.get("retryAt"):
                    c["retryAt"] = dt.datetime.fromtimestamp(timestamp(uncertain.get("at")) + 86400, dt.timezone.utc).isoformat()
        # A previous submission is never turned into a new application by Skip or scope.
        skip = next((v for v in skips["candidates"] if any(matches(c, k) for k in v.get("keys", []))), None)
        if skip and c["state"] not in {"submitted", "unverified"} and not (prior and prior.get("userRequest") and prior.get("state") != "skipped"):
            c.update(state="skipped", reason=skip["reason"])
        personal = False
        recovery_active = False
        if c["state"] not in TERMINAL | {"unverified"}:
            d = next((v for k, v in deferrals["records"].items() if matches(c, k) or canonical(k).split("|")[0] == url_key(c["sourceUrl"])), None)
            if d and not d.get("releasedAt") and not (prior and prior.get("releasedDeferral") and prior.get("userRequest")):
                # Personal-fact gaps do not heal with time. Technical retries may become due.
                personal = d.get("reason") in {"manual-heavy", "user-action"}
                if personal or timestamp(d.get("retryAt")) > current:
                    c.update(state="deferred", reason=d.get("detail", d.get("reason", "deferred"))[:350], retryAt=None if personal else d.get("retryAt"))
            for k, value in recovery.get("candidateCooldowns", {}).items():
                if matches(c, k) and timestamp(value.get("retryAfter", value.get("until", 0))) > current:
                    recovery_active = True
                    c.update(state="deferred", reason="Interrupted candidate cooldown; reconcile before retry")
            if c["state"] == "deferred" and not personal and not recovery_active and prior and prior.get("retryAt") and timestamp(prior["retryAt"]) <= current:
                c.update(state="needs-browser", reason="Technical retry due; inspect prior evidence before any submit")
        if c["state"] not in TERMINAL | {"unverified"}:
            category = c.get("category", "").lower()
            cats = [v for k, v in config["categories"].items() if k == category or any(w.lower() in category for w in v.get("keywords", []))]
            if cats and not any(v.get("enabled", True) for v in cats):
                c.update(state="out-of-scope", reason="Category disabled by user")
        if c["state"] in {"verified", "needs-browser"}:
            # Only an unambiguous ISO deadline can be automatically dated; relative prose stays visible.
            deadline = re.fullmatch(r"(?:\*\*)?(20\d\d-\d\d-\d\d)(?:\*\*)?", c.get("deadline", ""))
            if deadline and deadline[1] < dt.datetime.now().date().isoformat():
                c.update(state="deferred", reason="Recorded ISO deadline has passed; verify current source before closure")
            future = re.search(r"(?:recheck|do not act before|opens?|reopens?)\s+(20\d\d-\d\d-\d\d)", c.get("reason", "") + " " + c.get("deadline", ""), re.I)
            if future and future[1] > dt.datetime.now().date().isoformat():
                c.update(state="deferred", reason="Future application opening " + future[1], retryAt=future[1] + "T12:00:00Z")
        c["due"] = due(c, current)
    def rank(c):
        text = (c["name"] + " " + c.get("category", "")).lower()
        return (0 if c["state"] == "unverified" else 1, 0 if c.get("effort") == "low" else 1,
                0 if any(w in text for w in ("travel", "creator", "ambassador", "builder", "ai", "product")) else 1, c["key"])
    candidates.sort(key=rank)
    counts = {"actionable": 0, "reconcile": 0, "deferred": 0, "skipped": 0, "submitted": 0, "closed": 0, "outOfScope": 0, "unknown": 0}
    for c in candidates:
        bucket = {"verified": "actionable", "needs-browser": "actionable", "unverified": "reconcile", "out-of-scope": "outOfScope"}.get(c["state"], c["state"])
        if bucket == "reconcile" and not c["due"]:
            bucket = "deferred"
        counts[bucket if bucket in counts else "unknown"] += 1
    answers = omega / "loops/answers/opportunity.jsonl"
    pending = sum(bool(l.strip()) for l in answers.read_text().splitlines()) if answers.exists() else 0
    if counts["unknown"]:
        warnings.append(f'{counts["unknown"]} legacy records need status reconciliation; they are not automatically eligible.')
    next_action = (f'Reconcile {counts["reconcile"]} uncertain outcomes before any retry; then inspect {counts["actionable"]} ready candidates.'
                   if counts["reconcile"] else f'Inspect and complete {counts["actionable"]} ready candidates.' if counts["actionable"]
                   else 'No ready applications. Hunt should replenish from new sources; do not revisit personal-fact walls.')
    return {"version": VERSION, "generatedAt": now(), "counts": counts, "pendingAnswers": pending,
            "candidates": candidates, "nextAction": next_action, "warnings": warnings,
            "sources": {"records": record_count, "inboxRows": inbox_count},
            "enabledCategories": [k for k, v in config["categories"].items() if v.get("enabled", True)]}


def prepare(root, omega, lane, output=None):
    with locked(root):
        state = snapshot(root, omega)
        atomic_json(root / "pipeline/ENGINE-STATE.json", state)
        selected = [c for c in state["candidates"] if c["due"]][:8]
        # Reject/archive prose cannot expand the model prompt without bound.
        selected = [{k: (v[:1500] if isinstance(v, str) else v) for k, v in c.items()
                     if k in {"key", "name", "state", "reason", "sourceUrl", "recordPath", "category", "deadline", "effort", "origin", "due"}} for c in selected]
        packet = {**state, "lane": lane, "root": str(root), "omega": str(omega), "candidates": selected}
        if lane == "opportunity-hunt":
            packet["candidates"] = []
            packet["knownSources"] = sorted({urlsplit(c["sourceUrl"]).netloc for c in state["candidates"] if c["sourceUrl"]})[:100]
            packet["searchHistory"] = read_json(root / "pipeline/ENGINE-SEARCHES.json", {"entries": []})["entries"][-12:]
        if lane == "opportunity-followup":
            def recent(c):
                path = root / c.get("recordPath", "")
                return max(timestamp(c.get("updatedAt")), path.stat().st_mtime if path.is_file() else 0)
            submitted = sorted((c for c in state["candidates"] if c["state"] == "submitted"), key=recent, reverse=True)[:12]
            packet["recentSubmitted"] = [{k: str(c.get(k, ""))[:1500] for k in
                ("key", "name", "sourceUrl", "recordPath", "evidence", "confirmation", "updatedAt")} for c in submitted]
        if output:
            atomic_json(output, packet)
        return packet


def record(root, omega, args):
    with locked(root):
        state = snapshot(root, omega)
        candidate = next((c for c in state["candidates"] if matches(c, args.key)), None)
        if not candidate:
            raise ValueError("Unknown candidate key; add verified intake before recording an outcome")
        if candidate["state"] == "submitted" and args.state != "submitted":
            raise ValueError("Cannot reopen or overwrite historical submission; record post-submission follow-up separately")
        if candidate["state"] == "unverified" and args.state == "skipped":
            raise ValueError("Preserve uncertain submission state; a user skip is not a withdrawal or reconciliation")
        if candidate["state"] == "skipped" and args.state != "skipped" and not args.user_request:
            raise ValueError("Only the user can reopen a user-skipped candidate")
        if args.state == "skipped" and not args.user_request:
            raise ValueError("User skip requires exact user-request provenance")
        evidence = Path(args.evidence).expanduser() if args.evidence else None
        if evidence and not evidence.is_absolute():
            evidence = root / evidence
        if args.state in {"submitted", "verified", "closed"}:
            if not evidence or not evidence.is_file() or evidence.stat().st_size == 0:
                raise ValueError("This transition requires an existing nonempty evidence file")
        if args.state == "submitted" and (not args.confirmation or evidence.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}):
            raise ValueError("Submitted requires screenshot evidence and an explicit portal confirmation")
        if args.state == "deferred" and not args.reason:
            raise ValueError("Deferral requires concrete reason, not elapsed time")
        if candidate["state"] == "unverified" and args.state in {"verified", "needs-browser", "deferred", "closed"} and (not evidence or not evidence.is_file() or evidence.stat().st_size == 0 or not args.confirmation):
            raise ValueError("Uncertain submission requires portal evidence and explicit reconciliation before changing state")
        file = root / "pipeline/ENGINE-OUTCOMES.json"
        data = read_json(file, {"version": VERSION, "records": {}, "history": []})
        item = {"key": candidate["key"], "state": args.state, "reason": args.reason,
                "evidence": str(evidence) if evidence else None, "confirmation": args.confirmation,
                "updatedAt": now(), "priorState": candidate["state"], "actor": "opportunity-engine"}
        if args.state == "unverified":
            item["retryAt"] = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=24)).isoformat()
        if args.retry_minutes:
            if args.state != "deferred" or args.retry_minutes < 1:
                raise ValueError("Only technical deferrals may set a positive retry duration")
            if not re.search(r"technical|site.failure|no.progress|network|timeout", args.reason, re.I) or re.search(r"personal|missing.fact|user.action|manual.heavy", args.reason, re.I):
                raise ValueError("Personal-fact deferrals never expire; retry duration requires a technical reason")
            item["retryAt"] = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=args.retry_minutes)).isoformat()
        if args.user_request:
            item["userRequest"] = args.user_request
            if candidate["state"] == "deferred" and args.state in {"verified", "needs-browser"}:
                if not evidence or not evidence.is_file() or evidence.stat().st_size == 0:
                    raise ValueError("Releasing a personal-fact deferral requires evidence of the new user-provided facts")
                item["releasedDeferral"] = True
        data["records"][candidate["key"]] = item
        data.setdefault("history", []).append(item)
        atomic_json(file, data)
    # A persisted, candidate-specific outcome is a real milestone. Keep this tied
    # to the runner's unique progress file; a failed checkpoint never rolls back
    # a durable application outcome or manufactures evidence.
    run_id = os.environ.get("RUN_ID", "")
    progress = omega / "loops/receipts/opportunity" / (run_id + ".progress.json")
    if re.fullmatch(r"\d{8}-\d{6}", run_id) and progress.is_file() and evidence and evidence.is_file() and evidence.stat().st_size:
        try:
            from application_progress import record as checkpoint
            checkpoint(progress, candidate["key"], "portal-outcome-" + args.state, evidence)
        except (ValueError, OSError, KeyError, TypeError) as exc:
            print(f"Outcome preserved; progress checkpoint unavailable: {exc}", file=sys.stderr)
    return prepare(root, omega, "opportunity")


def validate(raw):
    required = ("name", "sourceUrl", "category", "cycle", "eligibility", "evidence", "openStatus", "effort")
    if not isinstance(raw, dict) or any(not raw.get(k) for k in required):
        raise ValueError("Candidate needs name, sourceUrl, category, cycle, eligibility, evidence, openStatus and effort")
    if any(not isinstance(raw[k], str) or len(raw[k]) > 2000 for k in required if k != "evidence") or raw["effort"] not in {"low", "unknown"}:
        raise ValueError("Candidate string fields must be bounded; effort must be low or unknown")
    if not url_key(raw["sourceUrl"]).startswith("https://") or raw["openStatus"] not in {"open", "unknown"}:
        raise ValueError("Invalid official source or open status")
    if not isinstance(raw["evidence"], list) or not all(isinstance(e, dict) and e.get("url") and e.get("excerpt") for e in raw["evidence"]):
        raise ValueError("Source evidence requires URL and short verified excerpt")
    if len(raw["evidence"]) > 8 or any(not isinstance(e["excerpt"], str) or len(e["excerpt"]) > 1500 for e in raw["evidence"]):
        raise ValueError("Use at most eight bounded source excerpts, not page dumps")


def add_many(root, omega, raws):
    """Validate and add several candidates under one lock and one snapshot (feeds add dozens)."""
    for raw in raws:
        validate(raw)
    results = []
    with locked(root):
        state = snapshot(root, omega)
        skips = read_json(root / "pipeline/USER-SKIPS.json", {"candidates": []})
        path = root / "pipeline/ENGINE-INTAKE.json"
        data = read_json(path, {"version": VERSION, "candidates": {}})
        existing = list(state["candidates"])
        for raw in raws:
            key = canonical(raw["sourceUrl"] + "|" + raw["cycle"])
            incoming = {"key": key, "sourceUrl": raw["sourceUrl"], "aliases": [norm(raw["name"]), url_key(raw["sourceUrl"])]}
            if any(any(matches(incoming, k) for k in skip["keys"]) or norm(raw["name"]) == norm(skip.get("name", "")) for skip in skips["candidates"]):
                results.append({"added": False, "state": "skipped", "reason": "User explicitly skipped this candidate; no automatic reintake"})
                continue
            duplicate = next((c for c in existing if matches(c, key) or url_key(c["sourceUrl"]) == url_key(raw["sourceUrl"])), None)
            if duplicate:
                results.append({"added": False, "duplicate": duplicate["key"], "state": duplicate["state"]})
                continue
            item = {**raw, "key": key, "state": "needs-browser", "reason": "Official-source verified; inspect current form and saved facts before applying", "recordPath": "pipeline/ENGINE-INTAKE.json", "origin": "structured", "addedAt": now(), "aliases": [url_key(raw["sourceUrl"])]}
            data["candidates"][key] = item
            existing.append(item)
            results.append({"added": True, "key": key})
        if any(r["added"] for r in results):
            atomic_json(path, data)
    return results


def add(root, omega, file):
    return add_many(root, omega, [read_json(file, None)])[0]


def prompt(packet):
    print("# DETERMINISTIC OPPORTUNITY QUEUE — current state, not model estimates")
    print(json.dumps(packet, ensure_ascii=False, indent=2))
    print("Do not read full tracker, Hunt Inbox, BLOCKED, questionnaire or old receipts. The engine already indexed them. Read current profile and standing answers, then ONLY the selected candidate record and its relevant evidence. A candidate is selected for inspection, not automatically eligible. Source/form facts outrank old discovery prose. Never fabricate personal facts. No fees, sensitive identifiers, CAPTCHA bypass, AI-prohibited writing, or repeated unknown-fact questions.")
    print("Before Submit: reread rendered answers, check pending user Skip/Stop and actual portal for duplicates; checkpoint submit-started. After confirmed Submit: preserve screenshot, confirmation, material, submission ledger and opportunity record; use engine record to persist state. Uncertain results are unverified, never blind retry. After each outcome run prepare again; finish all actionable work, not an arbitrary application quota. Personal facts do not become known when a cooldown expires.")


def main():
    p = argparse.ArgumentParser()
    repo = Path(__file__).resolve().parents[1]
    p.add_argument("--root", type=Path, default=Path(os.environ.get("OPPORTUNITY_ROOT", repo)),
                   help="workspace holding pipeline/ and profile/ (env OPPORTUNITY_ROOT, default: repo root)")
    p.add_argument("--omega", type=Path, default=Path(os.environ.get("OPPORTUNITY_RUNNER_DIR", repo / ".runner")),
                   help="loop-runner dir holding loops/state, loops/answers, loops/receipts (env OPPORTUNITY_RUNNER_DIR)")
    sub = p.add_subparsers(dest="command", required=True)
    q = sub.add_parser("prepare"); q.add_argument("--lane", default="opportunity"); q.add_argument("--output", type=Path)
    q = sub.add_parser("prompt"); q.add_argument("--packet", type=Path, required=True)
    q = sub.add_parser("add"); q.add_argument("--file", type=Path, required=True)
    q = sub.add_parser("record")
    q.add_argument("--key", required=True); q.add_argument("--state", choices=sorted(STATES), required=True)
    q.add_argument("--reason", default=""); q.add_argument("--evidence", default=""); q.add_argument("--confirmation", default="")
    q.add_argument("--user-request", default=""); q.add_argument("--retry-minutes", type=int, default=0)
    q = sub.add_parser("search-result")
    q.add_argument("--focus", required=True); q.add_argument("--source", required=True); q.add_argument("--added", type=int, required=True); q.add_argument("--reason", default="")
    args = p.parse_args()
    root, omega = args.root.expanduser().resolve(), args.omega.expanduser().resolve()
    try:
        if args.command == "prompt":
            prompt(read_json(args.packet, {})); return
        if args.command == "prepare":
            result = prepare(root, omega, args.lane, args.output)
            print(json.dumps({k: result[k] for k in ("counts", "pendingAnswers", "nextAction", "warnings")})); return
        if args.command == "record":
            result = record(root, omega, args)
            print(json.dumps({"recorded": args.state, "counts": result["counts"]})); return
        if args.command == "add":
            print(json.dumps(add(root, omega, args.file))); return
        if args.command == "search-result":
            with locked(root):
                file = root / "pipeline/ENGINE-SEARCHES.json"
                data = read_json(file, {"version": VERSION, "entries": []})
                data["entries"].append({"at": now(), "focus": args.focus, "source": args.source, "added": args.added, "reason": args.reason[:500]})
                data["entries"] = data["entries"][-200:]
                atomic_json(file, data)
            print(json.dumps({"recorded": True})); return
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f"ENGINE BLOCKED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main() or 0)
