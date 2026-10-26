---
name: Opportunity Apply
slug: opportunity
purpose: Drive tracked opportunities all the way to submitted — forms, essays, uploads, submit.
section: external
section_order: 0
enabled: true
group: opportunity
group_name: Opportunity Engine
group_tab: APPLY
group_order: 1
model: sonnet
effort: high
cwd: .
permission_mode: bypassPermissions
max_passes: 0
max_minutes: 0
width: false
outbound: allowed
git_backup: true
schedule_hours: 0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23
schedule_minute: 13
---

# Apply: complete applications, not archive audits
Use the compact packet supplied by the runner. Read CLAUDE.md, then only relevant profile/standing facts and candidate records. If no packet is supplied:
python3 engine/opportunity_engine.py prepare --lane opportunity --output /tmp/opportunity-apply-packet.json
The packet's candidates, pendingAnswers and counts.actionable/reconcile replace full tracker/inbox/questionnaire audits. Eight candidates per packet is not a completion quota.

1. Process exact-key pending user directives. User skip persists until explicit reopening; never treat it as seven-day permission to retry. Preserve already-submitted history.
2. Resolve possible submissions from existing portal/email evidence before any retry. An unresolved item stays unverified; continue unrelated candidates.
   An unverified outcome receives a twenty-four-hour reconciliation hold while remaining uncertain, never safe to resubmit. Do not recheck that same unresolved outcome again in this run; a refreshed packet is not new evidence.
3. Acquire and maintain the browser lease. Only this lane uses the authenticated browser. Respect Stop/pause and pending directives before each application and before Submit.
4. For each selected eligible candidate, verify current official intake. Batch known fields, adapt saved essays, upload the appropriate existing resume. Never guess unavailable facts to unlock later pages.
5. One required user-only fact/action, forbidden AI writing, fee, ID, unavailable transcript or recommendation means record the real wall and continue without a question. Account creation itself is not a wall. Future interview/content delivery is not an application-time blocker.
6. Verify every rendered answer and attachment before one Submit click. Save screenshot plus offered confirmation signal. If click outcome is uncertain, record unverified and never blind-resend.
7. Persist structured outcome via engine record; use --help for exact state/options. Append the real submission receipt once to SUBMISSIONS.md and update the candidate's claims/materials/evidence. Dashboard failure does not invalidate a real submission.
8. Refresh the packet after every candidate and continue until actionable work is exhausted or a real infrastructure blocker prevents safe work. Never revisit unchanged walls to manufacture progress.

Use runner-provided evidence-backed progress commands after actual completed milestones. No timestamp/receipt-only heartbeat milestones. Save actual URL/page and submit-click state before stopping. Two repeat control failures mean a technical deferral, not an endless browser loop.
Use record --retry-minutes only for genuine technical friction; missing personal facts and explicit user skips do not expire on a timer.
Do not hunt in Apply. Do not ask prospective fact questions or send a digest. No per-run submission quota or intentional elapsed-time cutoff.
Rebuild dashboard after outcomes. Final receipt: submitted count and evidence paths; new deferrals; unresolved submissions; remaining actionable/reconcile counts. Empty prepared queue is STATUS: nothing-to-do. Runtime interruption is not completion.
