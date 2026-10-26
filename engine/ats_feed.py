#!/usr/bin/env python3
"""ATS feed: deterministic, model-free intake for the Opportunity Engine.

Hunt's model-driven web search yields ~0 candidates/hour once the niche families dry up,
which starves Apply. Most completed applications land on Greenhouse/Ashby/Lever, so this feed reads
those boards' public JSON APIs directly, plus the SimplifyJobs intern/new-grad listings, and
adds fitting entry-level roles through opportunity_engine.add (same dedupe, skip and schema
rules as any other intake).

Scope is set in pipeline/ATS-FEED.json (default: entry-level full-time jobs and internships in
major U.S. cities or U.S.-remote). Backpressure keeps the queue
near a target instead of flooding it; per-company caps keep it from carpet-bombing one employer.
Apply still reads the live posting and form before anything is submitted.
"""
import argparse
import concurrent.futures as cf
import csv
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qs, urlencode

sys.path.insert(0, str(Path(__file__).resolve().parent))
import opportunity_engine as engine  # noqa: E402

UA = "Mozilla/5.0 (opportunity-engine ats-feed; personal job search)"
SIMPLIFY = {
    "simplify-interns": "https://raw.githubusercontent.com/SimplifyJobs/Summer2027-Internships/dev/.github/scripts/listings.json",
    "simplify-newgrad": "https://raw.githubusercontent.com/SimplifyJobs/New-Grad-Positions/dev/.github/scripts/listings.json",
}
DEFAULTS = {
    "enabled": True,
    "queueTarget": 30,          # top up actionable candidates to this many, never beyond
    "maxAddsPerRun": 25,
    "maxPerCompanyPerRun": 2,
    "maxOpenPerCompany": 3,     # actionable/deferred, not-yet-terminal records per employer
    "maxAgeDays": 30,
    "boardsPerRun": 160,
    "excludeCities": [],         # lowercase city names to skip, e.g. ["detroit"]
    "extraBoards": [],          # e.g. "greenhouse:figma", "ashby:ramp", "lever:plaid"
    "blockedCompanies": [],
    "excludeInternTerms": "",   # regex of internship terms to skip, e.g. "summer\\s*2027"
    "targetsCsv": "",           # optional CSV (column "Role URL") whose ATS boards are also polled
    "eligibilityNote": "Entry-level/early-career role in a major U.S. city or U.S.-remote, inside the configured job scope. "
                       "Apply must read the live description for degree/experience/location requirements before submitting; "
                       "close it if they don't fit.",
}
STATES = set("AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split())
MAJOR = {c.lower() for c in """New York|NYC|Manhattan|Brooklyn|Jersey City|Hoboken|Newark|Stamford|San Francisco|SF|Bay Area|
South San Francisco|Oakland|San Jose|Palo Alto|Mountain View|Menlo Park|Sunnyvale|Redwood City|Santa Clara|Cupertino|San Mateo|
Los Angeles|LA|Santa Monica|Culver City|Irvine|San Diego|Seattle|Bellevue|Redmond|Austin|Dallas|Houston|Fort Worth|Plano|
Irving|San Antonio|Chicago|Boston|Cambridge|Somerville|Washington|Washington DC|Washington, D.C.|Arlington|Reston|McLean|
Atlanta|Miami|Fort Lauderdale|Tampa|Orlando|Denver|Boulder|Phoenix|Scottsdale|Tempe|Philadelphia|Pittsburgh|Minneapolis|
Nashville|Charlotte|Raleigh|Durham|Salt Lake City|Lehi|Portland|Baltimore|Columbus|Huntsville|Birmingham|St. Louis|
Kansas City|Las Vegas|Sacramento|Indianapolis|Cincinnati|Cleveland|Princeton|New Haven|Providence|Richmond|Madison""".replace("\n", "").split("|")}
LEVEL = re.compile(r"\b(intern(ship)?s?|co-?op|new[ -]?grad(uate)?|graduate|university|campus|entry[ -]level|early[ -]career|"
                   r"associate|analyst|coordinator|representative|sdr|bdr|rotational|apprentice(ship)?|fellow(ship)?|"
                   r"junior|jr\.?|founder'?s associate|chief of staff|generalist|class of 2027|2027)\b", re.I)
FUNCTION = re.compile(r"\b(operations|ops|bizops|strategy|strategic|business|growth|marketing|sales|development|partnerships?|"
                      r"finance|financial|accounting|fp&a|investment|investing|venture|capital markets|product|program|"
                      r"customer success|solutions|gtm|go[- ]to[- ]market|community|content|creator|brand|data analyst|"
                      r"analytics|ai|agent|automation|ios|mobile|swift|chief of staff|founder|generalist|revenue|economics|"
                      r"trading|quant|research analyst|consulting|consultant|deployment|implementation)\b", re.I)
EXCLUDE = re.compile(r"\b(senior|sr\.?|staff|principal|lead|leader|manager|director|head|vp|vice president|president|"
                     r"ii|iii|iv|architect|phd|ph\.d|postdoc|doctoral|mba|nurse|nursing|clinical|physician|pharmac|"
                     r"mechanical|electrical|hardware|firmware|manufacturing|technician|machinist|warehouse|driver|"
                     r"attorney|counsel|paralegal|account executive|executive assistant|security clearance|cleared|"
                     r"ts/sci|embedded|rf|silicon|asic|fpga|tutor|annotator|annotation|labeler|transcription|translator|interpreter|"
                     r"polish|spanish|french|german|japanese|korean|mandarin|chinese|portuguese|italian|arabic|hindi|bilingual|"
                     r"trainer|ai training|bosnian|croatian|serbian|dutch|swedish|turkish|vietnamese|russian|ukrainian|"
                     r"safety engineer|part[- ]time|temporary|contract|seasonal|volunteer|unpaid)\b", re.I)
FOREIGN = re.compile(r"\b(united kingdom|england|scotland|ireland|uk|canada|ontario|quebec|british columbia|india|germany|"
                     r"france|spain|netherlands|poland|singapore|japan|china|australia|brazil|mexico|israel|switzerland|"
                     r"sweden|denmark|portugal|romania|philippines|emea|apac|latam|europe)\b", re.I)
SW_OK = re.compile(r"\b(ios|mobile|swift|ai|agent|agentic|full[- ]?stack|front[- ]?end|product|applied|forward deployed|founding)\b", re.I)


def log(*a):
    print("[ats-feed]", *a, file=sys.stderr)


def get_json(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def cached(cache, name, url, max_age):
    path = cache / (name + ".json")
    if path.is_file() and time.time() - path.stat().st_mtime < max_age:
        return json.loads(path.read_text())
    data = get_json(url, timeout=60)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data))
    tmp.replace(path)
    return data


def clean_url(url):
    u = urlsplit(url.strip())
    keep = {k: v for k, v in parse_qs(u.query).items() if k in {"gh_jid", "jobId", "id"}}
    return urlunsplit(("https", u.netloc.lower(), u.path.rstrip("/"), urlencode(keep, doseq=True), ""))


def ats_of(url):
    u = urlsplit(url)
    parts = [p for p in u.path.split("/") if p]
    if not parts:
        return None
    host = u.netloc.lower()
    if host.endswith("greenhouse.io") and "embed" not in parts[0]:
        return ("greenhouse", parts[0].lower())
    if host == "jobs.ashbyhq.com":
        return ("ashby", parts[0])
    if host == "jobs.lever.co":
        return ("lever", parts[0])
    return None


def us_location(locs, remote=False, excluded=()):
    """True when at least one location is a major U.S. metro or U.S.-remote, and not only an excluded city."""
    ok = False
    for raw in locs:
        loc = (raw or "").strip()
        low = loc.lower()
        if not low or any(c in low for c in excluded) or FOREIGN.search(low):
            continue
        us = bool(re.search(r"\b(usa|u\.s\.a?\.?|united states|us)\b", low)) or \
            (re.search(r",\s*([A-Z]{2})\b", loc) and re.search(r",\s*([A-Z]{2})\b", loc)[1] in STATES)
        city = re.split(r",|\(|-|–|/", low)[0].strip()
        if "remote" in low or remote:
            if us or low in {"remote", "remote - anywhere"}:
                ok = True
        elif city in MAJOR or low in MAJOR:
            if us or city in MAJOR:
                ok = True
    return ok


def fits_title(title, simplify_category=None):
    if EXCLUDE.search(title):
        return False
    if simplify_category:  # Simplify lists are already intern/new-grad scoped.
        if simplify_category in {"Product", "Quant", "AI/ML/Data"}:
            return True
        if simplify_category == "Software":
            return bool(SW_OK.search(title))
        return False
    return bool(LEVEL.search(title) and FUNCTION.search(title))


def alive(url):
    """Simplify marks some removed postings active; confirm the official page still serves the job."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=15) as r:
            final = r.geturl()
            return r.status == 200 and "error=true" not in final and urlsplit(final).path.rstrip("/").count("/") >= 2
    except Exception:
        return False


def score(job):
    t = job["title"].lower()
    s = 0
    if re.search(r"product|operations|bizops|strategy|growth|chief of staff|founder|generalist|ai|agent", t):
        s += 3
    if re.search(r"financ|fintech|invest|capital|trading|quant|accounting", t):
        s += 2
    if job["remote"]:
        s += 1
    if job["ageDays"] <= 7:
        s += 1
    if not job["intern"]:
        s += 2  # full-time roles rank above internships
    return s


# ---------- sources ----------
def simplify_jobs(cache, cfg):
    out = []
    now = time.time()
    for name, url in SIMPLIFY.items():
        try:
            data = cached(cache, name, url, 3 * 3600)
        except Exception as exc:  # network/provider failure is reported, never fatal
            log(f"{name} unavailable: {exc}")
            continue
        for x in data:
            if not (x.get("active") and x.get("is_visible", True)):
                continue
            age = (now - x.get("date_posted", 0)) / 86400
            degrees = x.get("degrees") or []
            if age > cfg["maxAgeDays"] or (degrees and "Bachelor's" not in degrees):
                continue
            url = clean_url(x["url"])
            if not ats_of(url) or not fits_title(x.get("title", ""), x.get("category")):
                continue
            locs = x.get("locations") or []
            if not us_location(locs, excluded=cfg["excludeCities"]):
                continue
            intern = name == "simplify-interns"
            skip = cfg.get("excludeInternTerms") or ""
            terms = [t for t in (x.get("terms") or []) if re.search(r"202[67]", t) and not (skip and re.search(skip, t, re.I))]
            if intern and not terms:
                continue
            out.append({"company": x["company_name"], "title": x["title"], "url": url, "locations": locs,
                        "remote": any("remote" in l.lower() for l in locs), "ageDays": round(age, 1),
                        "posted": dt.datetime.fromtimestamp(x["date_posted"], dt.timezone.utc).date().isoformat(),
                        "intern": intern, "cycle": (terms[0] if intern else "new-grad-2027"),
                        "feed": name, "api": url})
    return out


def board_jobs(kind, token, cfg):
    now = time.time()
    out = []
    if kind == "greenhouse":
        api = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs"
        for j in get_json(api).get("jobs", []):
            stamp = j.get("first_published") or j.get("updated_at") or ""
            out.append((j.get("title", ""), j.get("absolute_url", ""), [(j.get("location") or {}).get("name", "")], False, stamp, api))
    elif kind == "ashby":
        api = f"https://api.ashbyhq.com/posting-api/job-board/{token}"
        for j in get_json(api).get("jobs", []):
            if j.get("isListed") is False:
                continue
            locs = [j.get("location", "")] + [s.get("location", "") for s in j.get("secondaryLocations") or []]
            country = ((j.get("address") or {}).get("postalAddress") or {}).get("addressCountry", "")
            if country:
                locs = [l + (", United States" if country in {"United States", "USA", "US"} else ", " + country) for l in locs]
            out.append((j.get("title", ""), j.get("jobUrl", ""), locs, bool(j.get("isRemote")) and country in {"", "United States", "USA", "US"}, j.get("publishedAt", ""), api))
    elif kind == "lever":
        api = f"https://api.lever.co/v0/postings/{token}?mode=json"
        for j in get_json(api):
            cats = j.get("categories") or {}
            locs = cats.get("allLocations") or [cats.get("location", "")]
            country = j.get("country", "")
            if country == "US":
                locs = [l + ", United States" for l in locs]
            stamp = dt.datetime.fromtimestamp(j.get("createdAt", 0) / 1000, dt.timezone.utc).isoformat()
            out.append((j.get("text", ""), j.get("hostedUrl", ""), locs, j.get("workplaceType") == "remote" and country in {"", "US"}, stamp, api))
    jobs = []
    for title, url, locs, remote, stamp, api in out:
        if not url or not fits_title(title):
            continue
        try:
            age = (now - dt.datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp()) / 86400
        except ValueError:
            age = 0.0
        if age > cfg["maxAgeDays"] or not us_location(locs, remote, cfg["excludeCities"]):
            continue
        intern = bool(re.search(r"\bintern|co-?op\b", title, re.I))
        if intern and cfg.get("excludeInternTerms") and re.search(cfg["excludeInternTerms"], title, re.I):
            continue
        season = re.search(r"(spring|summer|fall|winter)\s*(202[67])", title, re.I)
        cycle = (f"{season[1].title()} {season[2]}" if season else "internship-2026-27") if intern else "posted-" + dt.date.today().strftime("%Y-%m")
        jobs.append({"company": token, "title": title, "url": clean_url(url), "locations": [l for l in locs if l],
                     "remote": remote or any("remote" in l.lower() for l in locs), "ageDays": round(age, 1),
                     "posted": stamp[:10], "intern": intern, "cycle": cycle, "feed": kind, "api": api})
    return jobs


def simplify_names(cache):
    names = {}
    for name in SIMPLIFY:
        path = cache / (name + ".json")
        if path.is_file():
            for x in json.loads(path.read_text()):
                b = ats_of(x.get("url", ""))
                if b and x.get("company_name"):
                    names[b[1].lower()] = x["company_name"]
    return names


def harvest_boards(root, cache, cfg, state_boards):
    boards = set()
    for spec in cfg["extraBoards"]:
        if ":" in spec:
            boards.add(tuple(spec.split(":", 1)))
    snap = engine.read_json(root / "pipeline/ENGINE-STATE.json", {"candidates": []})
    for c in snap.get("candidates", []):
        b = ats_of(c.get("sourceUrl", ""))
        if b:
            boards.add(b)
    targets = Path(cfg["targetsCsv"]).expanduser() if cfg.get("targetsCsv") else None
    if targets and not targets.is_absolute():
        targets = root / targets
    if targets and targets.is_file():
        for row in csv.DictReader(targets.open()):
            b = ats_of(row.get("Role URL", ""))
            if b:
                boards.add(b)
    for name in SIMPLIFY:
        path = cache / (name + ".json")
        if path.is_file():
            for x in json.loads(path.read_text()):
                b = ats_of(x.get("url", ""))
                if b:
                    boards.add(b)
    # Least recently fetched first, so every board is visited on rotation.
    return sorted(boards, key=lambda b: state_boards.get(f"{b[0]}:{b[1]}", {}).get("fetchedAt", 0))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    repo = Path(__file__).resolve().parents[1]
    p.add_argument("--root", type=Path, default=Path(os.environ.get("OPPORTUNITY_ROOT", repo)))
    p.add_argument("--omega", type=Path, default=Path(os.environ.get("OPPORTUNITY_RUNNER_DIR", repo / ".runner")))
    p.add_argument("--dry", action="store_true", help="show what would be added; write nothing")
    p.add_argument("--force", action="store_true", help="ignore queue backpressure")
    a = p.parse_args()
    root, omega = a.root.expanduser().resolve(), a.omega.expanduser().resolve()
    pipeline = root / "pipeline"
    cfg_path = pipeline / "ATS-FEED.json"
    cfg = {**DEFAULTS, **engine.read_json(cfg_path, {})}
    if not cfg_path.exists() and not a.dry:
        engine.atomic_json(cfg_path, DEFAULTS)
    if not cfg["enabled"]:
        print(json.dumps({"added": 0, "reason": "disabled in ATS-FEED.json"}))
        return 0
    cache = pipeline / ".ats-cache"
    cache.mkdir(exist_ok=True)
    state_path = pipeline / "ATS-FEED-STATE.json"
    state = engine.read_json(state_path, {"boards": {}, "runs": []})

    snap = engine.snapshot(root, omega)
    actionable = snap["counts"]["actionable"]
    room = cfg["maxAddsPerRun"] if a.force else max(0, min(cfg["maxAddsPerRun"], cfg["queueTarget"] - actionable))
    if room == 0:
        print(json.dumps({"added": 0, "actionable": actionable, "reason": "queue at target"}))
        return 0

    open_per_company = {}
    for c in snap["candidates"]:
        b = ats_of(c.get("sourceUrl", ""))
        if b and c["state"] not in engine.TERMINAL:
            open_per_company[b[1].lower()] = open_per_company.get(b[1].lower(), 0) + 1
    known = {engine.url_key(c.get("sourceUrl", "")) for c in snap["candidates"]}
    blocked = {b.lower() for b in cfg["blockedCompanies"]}

    jobs = simplify_jobs(cache, cfg)
    boards = harvest_boards(root, cache, cfg, state["boards"])[: cfg["boardsPerRun"]]
    errors = 0
    pool = cf.ThreadPoolExecutor(max_workers=16)
    futures = {pool.submit(board_jobs, k, t, cfg): (k, t) for k, t in boards}
    try:
        done = list(cf.as_completed(futures, timeout=120))
    except cf.TimeoutError:
        done = [f for f in futures if f.done()]
        log(f"board fetch deadline hit; {len(done)}/{len(futures)} finished")
    for f in done:
        k, t = futures[f]
        entry = state["boards"].setdefault(f"{k}:{t}", {})
        entry["fetchedAt"] = time.time()
        try:
            found = f.result()
            entry.update(ok=True, matches=len(found))
            jobs += found
        except Exception as exc:
            errors += 1
            entry.update(ok=False, error=str(exc)[:120])

    pool.shutdown(wait=False, cancel_futures=True)

    seen, fresh = set(), []
    for j in sorted(jobs, key=lambda j: (-score(j), j["ageDays"])):
        key = engine.url_key(j["url"])
        company = (ats_of(j["url"]) or ("", j["company"]))[1].lower()
        if key in known or key in seen or company in blocked:
            continue
        seen.add(key)
        j["companyKey"] = company
        fresh.append(j)

    names = simplify_names(cache)
    added, per_run, sample, batch = [], {}, [], []
    for j in fresh:
        if len(added) >= room:
            break
        c = j["companyKey"]
        if per_run.get(c, 0) >= cfg["maxPerCompanyPerRun"] or open_per_company.get(c, 0) + per_run.get(c, 0) >= cfg["maxOpenPerCompany"]:
            continue
        company = j["company"] if j["feed"].startswith("simplify") else names.get(c, j["company"].replace("-", " ").title())
        cand = {
            "name": f"{company} — {j['title']}",
            "sourceUrl": j["url"],
            "category": "internship" if j["intern"] else "full-time new-grad",
            "cycle": j["cycle"],
            "eligibility": cfg["eligibilityNote"],
            "evidence": [{"url": j["api"], "excerpt": f"{company} | {j['title']} | {'; '.join(j['locations'])[:300]} | posted {j['posted']} | listed active via {j['feed']}"},
                         {"url": j["url"], "excerpt": "Official ATS posting URL from the employer's public job board."}],
            "openStatus": "open",
            "effort": "unknown",
        }
        if a.dry:
            sample.append(cand["name"] + " · " + "; ".join(j["locations"])[:60])
            added.append(j["url"])
            per_run[c] = per_run.get(c, 0) + 1
            continue
        if j["feed"].startswith("simplify") and not alive(j["url"]):
            log(f"stale listing skipped: {j['url']}")
            continue
        try:
            engine.validate(cand)
        except (ValueError, AttributeError) as exc:
            log(f"skipped invalid {j['url']}: {exc}")
            continue
        batch.append(cand)
        added.append(j["url"])
        per_run[c] = per_run.get(c, 0) + 1

    if batch and not a.dry:
        try:
            results = engine.add_many(root, omega, batch)
            added = [r["key"] for r in results if r.get("added")]
        except ValueError as exc:
            log(f"batch rejected: {exc}")
            added = []

    summary = {"added": len(added), "actionableBefore": actionable, "room": room, "matched": len(fresh),
               "boardsFetched": len(boards), "boardErrors": errors, "at": engine.now()}
    if a.dry:
        summary["sample"] = sample[:40]
    else:
        state["runs"] = (state.get("runs", []) + [summary])[-200:]
        engine.atomic_json(state_path, state)
        with engine.locked(root):
            file = pipeline / "ENGINE-SEARCHES.json"
            data = engine.read_json(file, {"version": engine.VERSION, "entries": []})
            data["entries"].append({"at": engine.now(), "focus": "ats-feed entry-level US roles", "source": "greenhouse/ashby/lever APIs + SimplifyJobs",
                                    "added": len(added), "reason": f"{len(fresh)} fitting unseen postings; {len(boards)} boards fetched, {errors} errors"})
            data["entries"] = data["entries"][-200:]
            engine.atomic_json(file, data)
    print(json.dumps(summary, indent=2 if a.dry else None))
    return 0


if __name__ == "__main__":
    sys.exit(main())
