# Unattended workflow
Read CLAUDE.md as the single safety/fact contract. Historical policies are archived, not cumulative.
Runtime: application windows are ten minutes per milestone; infrastructure backoff is fifteen minutes; an interrupted candidate cools down for twenty-four hours.

## Pipeline
Hunt → verified candidate intake → deterministic preparation → Apply → evidence-backed outcome → Follow-up.
The engine owns queue selection, canonical IDs, pending answers, exclusions and compact context. The model owns source verification, factual judgment and live form work.

Use the packet supplied by the runner. If absent:
python3 engine/opportunity_engine.py prepare --lane opportunity --output /tmp/opportunity-manual-packet.json
Read only that packet and referenced candidate/profile material. Refresh after each completed or deferred candidate; do not reread multi-thousand-line ledgers. Consult command --help rather than inventing options.
Hunt may use add --file candidate.json after checking the current schema; fallback is an append-only new row in HUNT-INBOX with official URL, cycle, verified eligibility, funding, deadline and application-effort evidence.
Apply persists outcomes through record --key KEY --state STATE and the supported evidence/confirmation/reason options. Preserve human-readable receipts too.
Use record --retry-minutes only for technical deferrals, never personal-fact walls or user skips. After each source-family search, persist search-result --focus FOCUS --source SOURCE --added COUNT --reason REASON. Hunt's packet searchHistory is its bounded memory; rotate away from recent zero-yield families instead of reading the full inbox.

## Selection
Respect enabled CATEGORIES, terminal outcomes, permanent user skips, uncertainty and due retry conditions. Missing facts do not become available because a week passed. A user skip never expires. Verified new facts or a changed site can release the corresponding wall without reviving unrelated skips.
Reconcile possible submissions before attempting them. A reconcile item is read-only until non-submission is established. If unresolved, preserve uncertainty and move on; don't block unrelated applications.
Recording unverified preserves uncertainty and starts a twenty-four-hour reconciliation hold. Do not repeatedly reconcile the same unresolved outcome in one run. Hold expiry permits another evidence check, never a blind resubmission.
Prioritize according to autopilot/CONFIG.md and the enabled categories. Do not reject a program merely because an interview, content delivery or attendance is required after selection; distinguish application-time requirements from later obligations and never fabricate a commitment.

## Execution
Inspect visible application requirements briefly. Known fields, uploaded existing materials and truthful permitted essays remain automatic. One unavailable required personal answer/action means defer immediately without a questionnaire.
Two failed interactions with the same control, or a genuinely stalled portal, means evidence-backed technical deferral. No blind retry loops; no forced page traversal to inventory questions.
Finish useful in-progress work without an arbitrary submission quota. Persist actual page/field/review/submit milestones with runner's progress command. A startup packet or report is not a fake browser milestone. Runtime watchdogs are enforced by the runner, not a reason to invent progress.

## Schedules and reporting
Apply/Hunt hourly; Follow-up every four hours; Cull monthly. Overlapping Apply runs skip under a single-run/browser lease. Recovery backoff handles infrastructure failures; empty queues are successful no-op outcomes.
Report verified submissions with receipt paths, newly deferred reasons, unresolved submission checks, excluded counts and genuinely due next retry. Do not claim received no invitations when email authentication failed.
No push digest or prospective manual-input reminders. Never suppress an actual interview, award or consequential post-submission deadline.
The machine must stay awake and online for scheduled runs.
