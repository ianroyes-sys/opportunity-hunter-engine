#!/usr/bin/env python3
"""Rebuild dashboard/index.html from the pipeline. Stdlib only, deterministic.

Usage: python3 scripts/build_dashboard.py   (from the project root)
Skills run this after every tracker update; it costs nothing.
"""
import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OPP_DIR = ROOT / "pipeline" / "opportunities"
TRACKER = ROOT / "pipeline" / "tracker.md"
STATE = ROOT / "autopilot" / "STATE.md"
STOP = ROOT / "STOP"
OUT = ROOT / "dashboard" / "index.html"
ENGINE = ROOT / "pipeline" / "ENGINE-STATE.json"
OWNER = __import__("os").environ.get("OPPORTUNITY_OWNER", "Opportunity pipeline")

FIELD_RE = re.compile(r"^- \*\*(.+?):\*\*\s*(.+)$")

STATUS_META = {
    "found":           ("○", "Found"),
    "vetted":          ("◎", "Vetted"),
    "materials-ready": ("✎", "Materials ready"),
    "awaiting-ian":    ("⏸", "Needs your OK"),
    "submitted":       ("➤", "Submitted"),
    "interview":       ("★", "Interview"),
    "won":             ("✓", "Won"),
    "rejected":        ("✕", "Rejected"),
    "expired":         ("✕", "Expired"),
}
STATUS_CLASS = {
    "found": "neutral", "vetted": "info", "materials-ready": "violet",
    "awaiting-ian": "warn", "submitted": "good", "interview": "good",
    "won": "good", "rejected": "muted", "expired": "muted",
}
for _state, _label, _class in [
    ("verified", "Ready", "info"), ("needs-browser", "Inspect form", "info"),
    ("unverified", "Reconcile outcome", "warn"), ("reconcile-wait", "Unverified · retry deferred", "warn"), ("deferred", "Deferred", "muted"),
    ("skipped", "Skipped by you", "muted"), ("closed", "Closed", "muted"),
    ("out-of-scope", "Outside enabled scope", "muted"), ("unknown", "Status unknown", "warn"),
]:
    STATUS_META[_state] = ("○", _label)
    STATUS_CLASS[_state] = _class
CATEGORY_ORDER = ["internship", "scholarship", "fellowship", "conference",
                  "competition", "remote job", "ambassadorship"]


def esc(s):
    return html.escape(str(s), quote=True)


def parse_opportunity(path):
    opp = {"file": path.name, "title": path.stem, "fields": {}}
    for line in path.read_text().splitlines():
        if line.startswith("# ") and opp["title"] == path.stem:
            opp["title"] = line[2:].strip()
        m = FIELD_RE.match(line.strip())
        if m:
            opp["fields"][m.group(1).strip().lower()] = m.group(2).strip()
    return opp


def get(opp, key, default="—"):
    return opp["fields"].get(key, default)


def category_of(opp):
    raw = get(opp, "category", "").lower()
    for c in CATEGORY_ORDER:
        if c in raw:
            return c
    return "other"


STATUS_MATCH_PRIORITY = ["expired", "rejected", "won", "interview", "submitted",
                          "awaiting-ian", "materials-ready", "vetted", "found"]


def status_of(opp):
    if "engine_state" in opp:
        return opp["engine_state"]
    raw = get(opp, "status", "").lower().strip().strip("*` ")
    # Narrative tails ("not submitted", "not rejected") must never become outcomes.
    if re.search(r"\b(?:unverified|submission[- ]unverified|submitted[- ]unverified)\b", raw):
        return "unverified"
    if re.match(r"(?:not|never|no)\s+(?:yet\s+)?submitted\b", raw):
        return "unknown"
    aliases = {"held": "deferred", "blocked": "deferred", "awaiting-ian": "deferred", "user-skipped": "skipped"}
    token = re.match(r"[a-z]+(?:-[a-z]+)*", raw)
    token = token.group(0) if token else "unknown"
    return aliases.get(token, token if token in STATUS_META else "unknown")


def engine_opportunities(opps, path=ENGINE, now=None):
    """Use canonical deduplicated snapshot; retain markdown only for display metadata."""
    if not path.exists():
        return opps, None, ["Engine snapshot absent. Showing legacy record history only; current readiness is unknown."]
    try:
        value = json.loads(path.read_text())
        count_keys = ("actionable", "reconcile", "deferred", "skipped", "submitted", "closed", "outOfScope", "unknown")
        if value.get("version") != 2 or not isinstance(value.get("candidates"), list):
            raise ValueError("Unsupported schema")
        if not all(type(value.get("counts", {}).get(k)) is int and value["counts"][k] >= 0 for k in count_keys):
            raise ValueError("Invalid counts")
        stamp = datetime.fromisoformat(value["generatedAt"].replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            raise ValueError("Timestamp requires timezone")
        warnings = value.get("warnings", [])
        if not isinstance(warnings, list) or not all(isinstance(w, str) for w in warnings):
            raise ValueError("Invalid warnings")
        warnings = list(warnings)
        age = ((now or datetime.now(timezone.utc)) - stamp).total_seconds()
        if age > 7200 or age < -300:
            warnings.insert(0, "Snapshot is stale or future-dated. Counts describe recorded history, not current readiness.")
        by_file = {o["file"]: o for o in opps}
        result = []
        allowed = {"verified", "needs-browser", "unverified", "deferred", "skipped", "submitted", "closed", "out-of-scope", "unknown"}
        for candidate in value["candidates"]:
            if candidate.get("state") not in allowed or not all(isinstance(candidate.get(k), str) for k in ("name", "recordPath", "sourceUrl", "category")):
                raise ValueError("Invalid candidate")
            if "due" in candidate and type(candidate["due"]) is not bool:
                raise ValueError("Invalid retry eligibility")
            name = Path(candidate["recordPath"]).name
            base = by_file.get(name, {"file": name, "fields": {}})
            display_state = candidate["state"]
            if candidate.get("due") is False and display_state in {"verified", "needs-browser", "unverified"}:
                display_state = "reconcile-wait" if display_state == "unverified" else "deferred"
            result.append({**base, "title": candidate["name"], "engine_state": display_state, "fields": {**base["fields"], "url": candidate["sourceUrl"], "category": candidate["category"]}})
        return result, value, warnings
    except (ValueError, TypeError, KeyError, AttributeError, OSError):
        return [], None, ["Engine snapshot is invalid. Queue and outcome counts withheld; original records are preserved."]


def fit_of(opp):
    m = re.search(r"(\d)\s*/\s*5", get(opp, "fit score", ""))
    return int(m.group(1)) if m else 0


def urgency(opp):
    d = get(opp, "deadline", "").lower()
    if any(w in d for w in ("open now", "asap", "rolling")):
        return 0
    m = re.search(r"(20\d\d)-(\d\d)-(\d\d)", d)
    if m:
        try:
            days = (datetime(*map(int, m.groups())) - datetime.now()).days
            return max(days, 0)
        except ValueError:
            pass
    return 999


def tracker_section(header):
    lines, capture = [], False
    for line in TRACKER.read_text().splitlines():
        if line.startswith("## "):
            capture = line[3:].strip().lower().startswith(header.lower())
            continue
        if capture and line.strip().startswith("- "):
            lines.append(line.strip()[2:])
    return lines


def md_inline(s):
    s = esc(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    return s


def autopilot_state():
    if STOP.exists():
        return ("stopped", "Stopped by you — delete the STOP file to allow restart")
    if STATE.exists():
        txt = STATE.read_text()
        m = re.search(r"^- \*\*Status:\*\*\s*(.+)$", txt, re.M)
        n = re.search(r"^- \*\*Last cycle:\*\*\s*(.+)$", txt, re.M)
        status = (m.group(1).strip() if m else "unknown")
        last = (n.group(1).strip() if n else "never")
        mode = "on" if status.lower().startswith(("on", "scheduled")) else "off"
        return (mode, f"Last run: {last}")
    return ("off", "Not started")


def card(opp):
    st = status_of(opp)
    icon, label = STATUS_META[st]
    cat = category_of(opp)
    fit = fit_of(opp)
    stars = "★" * fit + "☆" * (5 - fit)
    url = get(opp, "url", "")
    murl = re.search(r"https?://\S+", url)
    link = (f'<a class="cardlink" href="{esc(murl.group(0).rstrip(")—,"))}" '
            f'target="_blank" rel="noopener">Open listing ↗</a>' if murl else "")
    urg = urgency(opp)
    urgent = urg <= 14
    return f"""
    <article class="card{' card-urgent' if urgent else ''}">
      <div class="cardtop">
        <span class="chip chip-{esc(cat.replace(' ', ''))}">{esc(cat)}</span>
        <span class="pill pill-{STATUS_CLASS[st]}"><span class="pillicon">{icon}</span>{label}</span>
      </div>
      <h3>{esc(opp['title'])}</h3>
      <p class="org">{md_inline(get(opp, 'org'))}</p>
      <dl>
        <div><dt>Deadline</dt><dd class="{'due' if urgent else ''}">{md_inline(get(opp, 'deadline'))}</dd></div>
        <div><dt>Value</dt><dd>{md_inline(get(opp, 'value'))}</dd></div>
      </dl>
      <div class="cardfoot">
        <span class="fit" title="Fit score {fit}/5"><span class="stars">{stars}</span> fit</span>
        {link}
      </div>
    </article>"""


def main():
    opps = sorted((parse_opportunity(p) for p in sorted(OPP_DIR.glob("*.md"))),
                  key=lambda o: (urgency(o), -fit_of(o)))
    opps, engine, engine_warnings = engine_opportunities(opps)
    active = [o for o in opps if status_of(o) not in ("won", "rejected", "expired", "closed")]
    submitted = [o for o in opps if status_of(o) in ("submitted", "interview", "won")]
    due_soon = [o for o in active if status_of(o) in ("verified", "needs-browser") and urgency(o) <= 14]
    actions = [engine["nextAction"]] if engine else ["Queue readiness is not verified. See state warning above."]
    focuses = tracker_section("Next hunt")
    ap_mode, ap_detail = autopilot_state()
    resumes = sorted(p.name for p in (ROOT / "resumes").glob("*.docx")) \
        if (ROOT / "resumes").exists() else []

    tiles = [
        ("Tracked", len(active), "retained pipeline records"),
        ("Due ≤ 14 days", len(due_soon), "or open-now / rolling"),
        ("Deferred", engine["counts"]["deferred"] if engine else sum(status_of(o) == "deferred" for o in opps), "no repeated questions"),
        ("Submitted", engine["counts"]["submitted"] if engine else len(submitted), "recorded history, not awards"),
    ]
    unavailable = ENGINE.exists() and engine is None
    if unavailable:
        tiles = [(label, "—", "snapshot unavailable") for label, _, _ in tiles]
    tiles_html = "".join(
        f'<div class="tile"><span class="tilenum">{n}</span>'
        f'<span class="tilelabel">{esc(t)}</span>'
        f'<span class="tilesub">{esc(s)}</span></div>'
        for t, n, s in tiles)

    submitted_by_cat = {}
    for o in submitted:
        c = category_of(o)
        submitted_by_cat[c] = submitted_by_cat.get(c, 0) + 1
    cat_rows = sorted(submitted_by_cat.items(), key=lambda kv: -kv[1])
    applied_rows_html = "".join(
        f'<tr><td><span class="chip chip-{esc(c.replace(" ", ""))}">{esc(c)}</span></td>'
        f'<td class="num">{n}</td></tr>'
        for c, n in cat_rows) or '<tr><td colspan="2">No readable submission records.</td></tr>'
    applied_table_html = f"""<table class="appliedtable">
        <thead><tr><th>Category</th><th class="num">Recorded submissions</th></tr></thead>
        <tbody>{applied_rows_html}</tbody>
        <tfoot><tr><td>Total</td><td class="num">{'—' if unavailable else len(submitted)}</td></tr></tfoot>
      </table>"""

    actions_html = "".join(f"<li>{md_inline(a)}</li>" for a in actions) or \
        "<li>Nothing — you're clear.</li>"
    focus_html = "".join(f"<li>{md_inline(f)}</li>" for f in focuses)
    cards_html = "".join(card(o) for o in active) or \
        '<p class="empty">Pipeline is empty — run <code>/hunt</code>.</p>'
    resumes_html = "".join(
        f'<li><span class="docicon">▤</span>{esc(r)}</li>' for r in resumes) or \
        "<li>Run <code>/tailor tech</code> or <code>/tailor business</code> to generate variants.</li>"

    ap_class = {"on": "good", "off": "neutral", "stopped": "warn"}[ap_mode]
    ap_label = {"on": "● Autopilot ON (scheduled)", "off": "○ Autopilot off",
                "stopped": "⏸ Autopilot STOPPED"}[ap_mode]

    approve_html = '<div class="approve"><div>' + "<br>".join(esc(w) for w in engine_warnings) + '</div></div>' if engine_warnings else ""
    ap_label = "○ Queue snapshot" if engine else "○ Legacy history"
    ap_class = "neutral"
    ap_detail = ("Generated " + engine["generatedAt"] + "; not worker status") if engine else "Current worker state not inferred"

    now = datetime.now().strftime("%b %d, %Y · %I:%M %p")
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Opportunity Hunter — {esc(OWNER)}</title>
<style>
:root {{
  --bg:#0c0e12; --surface:#14171d; --surface2:#1a1e26; --border:#262b35;
  --ink:#eef1f6; --ink2:#9aa3b2; --ink3:#6b7484;
  --accent:#7aa2ff; --accent2:#b388ff;
  --good:#4ade80; --warn:#fbbf24; --bad:#f87171;
  --chip-internship:#7aa2ff; --chip-scholarship:#4ade80; --chip-fellowship:#b388ff;
  --chip-conference:#fbbf24; --chip-competition:#f472b6; --chip-remotejob:#2dd4bf;
  --chip-ambassadorship:#fb923c; --chip-other:#9aa3b2;
}}
@media (prefers-color-scheme: light) {{
  :root {{ --bg:#f6f7f9; --surface:#ffffff; --surface2:#f0f2f5; --border:#e3e6ec;
    --ink:#171b22; --ink2:#525a68; --ink3:#8a92a1;
    --accent:#3b63d8; --accent2:#7c4dcc;
    --good:#15803d; --warn:#b45309; --bad:#b91c1c;
    --chip-internship:#3b63d8; --chip-scholarship:#15803d; --chip-fellowship:#7c4dcc;
    --chip-conference:#b45309; --chip-competition:#be2f6f; --chip-remotejob:#0f766e;
    --chip-ambassadorship:#c2410c; }}
}}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ background:var(--bg); color:var(--ink); min-height:100vh;
  font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,sans-serif;
  -webkit-font-smoothing:antialiased; }}
.wrap {{ max-width:1080px; margin:0 auto; padding:40px 24px 80px; }}
header {{ display:flex; flex-wrap:wrap; gap:16px; align-items:flex-end;
  justify-content:space-between; margin-bottom:8px; }}
h1 {{ font-size:26px; letter-spacing:-.02em; font-weight:750; }}
h1 .grad {{ background:linear-gradient(90deg,var(--accent),var(--accent2));
  -webkit-background-clip:text; background-clip:text; color:transparent; }}
.meta {{ color:var(--ink3); font-size:13px; }}
.appill {{ display:inline-flex; align-items:center; gap:8px; padding:8px 14px;
  border-radius:999px; border:1px solid var(--border); background:var(--surface);
  font-size:13px; font-weight:600; }}
.appill small {{ color:var(--ink3); font-weight:400; }}
.appill.good {{ border-color:color-mix(in srgb,var(--good) 40%,var(--border)); color:var(--good); }}
.appill.warn {{ color:var(--warn); }}
.appill.neutral {{ color:var(--ink2); }}
.tiles {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr));
  gap:12px; margin:28px 0 36px; }}
.tile {{ background:var(--surface); border:1px solid var(--border); border-radius:16px;
  padding:18px 20px; display:flex; flex-direction:column; gap:2px; }}
.tilenum {{ font-size:30px; font-weight:750; letter-spacing:-.02em;
  font-variant-numeric:tabular-nums; }}
.tilelabel {{ font-size:13px; font-weight:600; color:var(--ink2); }}
.tilesub {{ font-size:12px; color:var(--ink3); }}
.appliedtable {{ width:100%; border-collapse:collapse; background:var(--surface);
  border:1px solid var(--border); border-radius:16px; overflow:hidden; margin:0 0 36px; }}
.appliedtable th, .appliedtable td {{ padding:12px 20px; text-align:left; font-size:13.5px; }}
.appliedtable thead th {{ color:var(--ink3); font-weight:600; font-size:12px;
  text-transform:uppercase; letter-spacing:.04em; border-bottom:1px solid var(--border); }}
.appliedtable tbody tr:not(:last-child) td {{ border-bottom:1px solid var(--border); }}
.appliedtable tfoot td {{ border-top:1px solid var(--border); font-weight:700; color:var(--ink); }}
.appliedtable td.num, .appliedtable th.num {{ text-align:right;
  font-variant-numeric:tabular-nums; color:var(--ink2); }}
.appliedtable tfoot td.num {{ color:var(--ink); }}
h2 {{ font-size:15px; font-weight:700; letter-spacing:.04em; text-transform:uppercase;
  color:var(--ink2); margin:36px 0 14px; }}
.actions {{ background:var(--surface); border:1px solid var(--border);
  border-left:3px solid var(--warn); border-radius:14px; padding:16px 20px; }}
.actions li {{ margin:6px 0 6px 18px; }}
.approve {{ background:color-mix(in srgb,var(--accent) 12%,var(--surface));
  border:1px solid color-mix(in srgb,var(--accent) 45%,var(--border));
  border-radius:16px; padding:18px 22px; margin:24px 0 4px; }}
.approve-go {{ background:color-mix(in srgb,var(--good) 14%,var(--surface));
  border-color:color-mix(in srgb,var(--good) 50%,var(--border)); }}
.approve strong {{ font-size:16px; }}
.approvenames {{ color:var(--ink2); font-size:13.5px; margin-top:4px; }}
.approvehow {{ color:var(--ink3); font-size:13px; margin-top:8px; }}
.approve code {{ background:var(--surface2); border:1px solid var(--border);
  border-radius:6px; padding:2px 7px; font-size:12.5px; color:var(--ink); }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(300px,1fr)); gap:14px; }}
.card {{ background:var(--surface); border:1px solid var(--border); border-radius:18px;
  padding:20px; display:flex; flex-direction:column; gap:10px;
  transition:transform .15s ease, border-color .15s ease; }}
.card:hover {{ transform:translateY(-2px); border-color:var(--ink3); }}
.card-urgent {{ border-left:3px solid var(--bad); }}
.cardtop {{ display:flex; justify-content:space-between; gap:8px; align-items:center; }}
.chip {{ font-size:11px; font-weight:700; letter-spacing:.05em; text-transform:uppercase;
  padding:3px 10px; border-radius:999px; border:1px solid; }}
.chip-internship {{ color:var(--chip-internship); border-color:var(--chip-internship); }}
.chip-scholarship {{ color:var(--chip-scholarship); border-color:var(--chip-scholarship); }}
.chip-fellowship {{ color:var(--chip-fellowship); border-color:var(--chip-fellowship); }}
.chip-conference {{ color:var(--chip-conference); border-color:var(--chip-conference); }}
.chip-competition {{ color:var(--chip-competition); border-color:var(--chip-competition); }}
.chip-remotejob {{ color:var(--chip-remotejob); border-color:var(--chip-remotejob); }}
.chip-ambassadorship {{ color:var(--chip-ambassadorship); border-color:var(--chip-ambassadorship); }}
.chip-other {{ color:var(--chip-other); border-color:var(--chip-other); }}
.pill {{ display:inline-flex; align-items:center; gap:5px; font-size:12px; font-weight:600;
  padding:3px 10px; border-radius:999px; background:var(--surface2); color:var(--ink2); }}
.pill-good {{ color:var(--good); }} .pill-warn {{ color:var(--warn); }}
.pill-info {{ color:var(--accent); }} .pill-violet {{ color:var(--accent2); }}
.pill-muted {{ color:var(--ink3); }}
.card h3 {{ font-size:16.5px; font-weight:700; letter-spacing:-.01em; }}
.org {{ font-size:13px; color:var(--ink2); margin-top:-4px; }}
dl {{ display:flex; flex-direction:column; gap:6px; font-size:13px; }}
dl div {{ display:flex; gap:8px; }}
dt {{ color:var(--ink3); min-width:64px; flex-shrink:0; }}
dd {{ color:var(--ink2); }}
dd.due {{ color:var(--bad); font-weight:600; }}
.cardfoot {{ display:flex; justify-content:space-between; align-items:center;
  margin-top:auto; padding-top:8px; border-top:1px solid var(--border); }}
.fit {{ font-size:12px; color:var(--ink3); }}
.stars {{ color:var(--warn); letter-spacing:2px; }}
.cardlink {{ font-size:13px; font-weight:600; color:var(--accent); text-decoration:none; }}
.cardlink:hover {{ text-decoration:underline; }}
.twocol {{ display:grid; grid-template-columns:1fr 1fr; gap:14px; }}
@media (max-width:720px) {{ .twocol {{ grid-template-columns:1fr; }} }}
.panel {{ background:var(--surface); border:1px solid var(--border); border-radius:16px;
  padding:18px 22px; }}
.panel h2 {{ margin-top:0; }}
.panel li {{ margin:7px 0 7px 4px; list-style:none; color:var(--ink2); font-size:13.5px; }}
.docicon {{ color:var(--accent); margin-right:8px; }}
.stopbox {{ margin-top:36px; background:var(--surface); border:1px dashed var(--border);
  border-radius:16px; padding:18px 22px; font-size:13.5px; color:var(--ink2); }}
.stopbox code {{ background:var(--surface2); border:1px solid var(--border);
  border-radius:6px; padding:2px 7px; font-size:12.5px; }}
.empty {{ color:var(--ink3); }}
strong {{ color:var(--ink); font-weight:650; }}
footer {{ margin-top:48px; color:var(--ink3); font-size:12px; text-align:center; }}
</style></head><body>
<div class="wrap">
  <header>
    <div>
      <h1>Opportunity <span class="grad">Hunter</span></h1>
      <p class="meta">{esc(OWNER)} · updated {now}</p>
    </div>
    <span class="appill {ap_class}">{ap_label}&nbsp;<small>{esc(ap_detail)}</small></span>
  </header>

  <div class="tiles">{tiles_html}</div>

  <h2>➤ Recorded submission history</h2>
  <p class="meta">Not awards or bookings. Historical receipts have not all been reverified today.</p>
  {applied_table_html}

  {approve_html}

  <h2>⚡ Action items</h2>
  <div class="actions"><ul>{actions_html}</ul></div>

  <h2>Pipeline</h2>
  <div class="grid">{cards_html}</div>

  <div class="twocol">
    <div class="panel"><h2>🔍 Next hunt focuses</h2><ul>{focus_html}</ul></div>
    <div class="panel"><h2>▤ Tailored resumes</h2><ul>{resumes_html}</ul></div>
  </div>

  <div class="stopbox">
    <strong>Stop autopilot:</strong> type <code>stop</code> in the Claude Code session,
    or run <code>touch STOP</code> in the project folder.
    Autopilot checks for that file before every cycle and shuts down if it exists.
  </div>

  <footer>Generated by scripts/build_dashboard.py — refresh after any /hunt, /apply, /followup, or /autopilot run</footer>
</div>
</body></html>"""
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text("\n".join(line.rstrip() for line in page.splitlines()) + "\n")
    print(f"Dashboard written: {OUT} ({len(active)} retained, {len(submitted)} submitted history)")


if __name__ == "__main__":
    main()
