---
name: Opportunity Hunt
slug: opportunity-hunt
purpose: Find and source-verify new eligible opportunities in parallel — never opens a form, never submits.
section: external
section_order: 0
enabled: true
group: opportunity
group_name: Opportunity Engine
group_tab: HUNT
group_order: 2
model: sonnet
cwd: .
permission_mode: bypassPermissions
max_passes: 8
max_minutes: 35
width: true
outbound: none
git_backup: false
schedule_hours: 0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23
schedule_minute: 34
---

# Hunt: supply usable candidates
Read CLAUDE.md and the runner's compact packet plus relevant profile facts. Honor enabled categories and permanent user skips. Do not read entire historical inbox/tracker each pass.
If needed prepare a packet using:
python3 engine/opportunity_engine.py prepare --lane opportunity-hunt --output /tmp/opportunity-hunt-packet.json

The runner's model-free ATS feed (`engine/ats_feed.py`) already tops up the queue with entry-level U.S. jobs and internships from Greenhouse/Ashby/Lever boards and SimplifyJobs before every Hunt and Apply run. Do not spend searches re-finding ATS job postings; use web search for what boards can't list: fellowships, ambassador programs, hackathons, competitions, summits, and employer career pages that are not on Greenhouse/Ashby/Lever.
Prioritize profile-matched fellowships, ambassador programs, grants, competitions, funded travel and full-time openings within enabled categories. Rotate source families when a niche produces no usable leads. Use current profile facts for graduation timing; a class year is not an exact date.
Use public search and official-source reads. Never use the shared browser, log in, submit or send. Publicly readable intake descriptions can be read without interacting; login-only requirements remain unknown, not automatically rejected.
Bound source reads and preserve short eligibility/open-date/funding excerpts. Search snippets are discovery, not final eligibility proof.
Distinguish application-time friction from future participation: a future interview or content deliverable alone is not manual-heavy. Verify airfare/transport, lodging and required costs separately for funded travel; no fee-bearing applications. Do not call a free ticket a free trip.

Add verified candidates through:
python3 engine/opportunity_engine.py add --file /path/to/candidate.json
Candidate JSON fields: name, sourceUrl, category, cycle, eligibility string, evidence [{url, excerpt}], openStatus (open|unknown), effort (low|unknown), optional deadline. Use current --help/schema if validation rejects a field; never fabricate values.
Unknown application effort is allowed as needs-browser when official opportunity eligibility and credible current source are established. Apply owns final intake verification.
If structured intake is unavailable, append one new row to HUNT-INBOX with canonical source/cycle and evidence; never edit prior rows or header. No tracker/SUBMISSIONS/BLOCKED edits.

Target quality, not a fixed count. Work across at least three enabled source families when earlier searches dry up, within the scheduled budget; do not pad with stale or ineligible leads. Do not repetitively inspect recorded dead ends.
Read the packet's searchHistory before choosing each focus. Avoid consecutively repeating a zero-yield source/focus family unless a concrete new opening or source change justifies it. Use other enabled families first; do not reread historical narration to reconstruct rotation.
After each family, write bounded search memory with:
python3 engine/opportunity_engine.py search-result --focus FOCUS --source SOURCE --added COUNT --reason REASON
COUNT is actual newly accepted candidates, not search hits. Save concise rejection/provider reasons, never full HTML or personal data. This memory complements candidate evidence; it is not a submission or browser milestone.
Receipt: new accepted keys, URLs and eligibility/funding evidence; source families searched; rejected/duplicate counts; actual provider errors. No new valid candidates is nothing-to-do, not fabricated success.
