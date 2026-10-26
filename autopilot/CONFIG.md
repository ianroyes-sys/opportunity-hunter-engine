# Autopilot configuration

Edit this file to match how much autonomy you want.

- Submit policy: `review` (stop before Submit and wait for the owner) or `auto` (submit with evidence under standing authorization). Default: `review`.
- Scheduler: run `scripts/run_lane.sh <lane>` from cron or launchd. Suggested: Apply hourly at :13, Hunt hourly at :34, Follow-up every four hours at :51, Cull monthly.
- Categories: `pipeline/CATEGORIES.json` is authoritative. Disabling a category moves its candidates out of scope; it never deletes them.
- Job scope: set cities, exclusions and eligibility text in `pipeline/ATS-FEED.json` (see `engine/ats_feed.py` DEFAULTS).
- Missing personal facts, recommendations and transcripts: defer and continue; no outreach.
- Safety: never fabricate, pay fees, enter sensitive identifiers or bypass anti-bot/MFA/assessments.
- Stop controls: `touch STOP` in the project root, or `touch .runner/loops/paused/<lane>` for one lane.
