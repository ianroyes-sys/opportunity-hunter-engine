---
name: Opportunity Cull
slug: opportunity-cull
purpose: Recommend evidence-backed closure of unsubmitted listings while preserving all application history.
section: external
section_order: 0
enabled: true
group: opportunity
group_name: Opportunity Engine
group_tab: CULL
group_order: 4
model: sonnet
cwd: .
permission_mode: bypassPermissions
max_passes: 2
max_minutes: 20
width: false
outbound: none
git_backup: true
schedule_hours: 2
schedule_minute: 10
schedule_day: 28
---

# Maintenance: evidence-backed closure without deleting history
Use CLAUDE.md and the runner's compact packet. Never open a browser, log in, submit, send or edit prospective questionnaires.
This lane writes maintenance recommendations to its receipt (and a dedicated pipeline/MAINTENANCE.md if useful); Apply/engine owns candidate-state mutation. It no longer edits tracker cells or deletes BLOCKED sections.
Review only due unsubmitted candidates or new Follow-up expiry recommendations, not every record. Verify the exact current official listing and cycle. A source-verified application closure can support closed; a 404 alone is uncertain, and a recheck date is not a deadline.
Never convert submitted/interview/won/unverified to expired because a listing deadline passed, a wall is old or a required action may have been missed. Only actual portal/email outcome evidence supports a post-submission status transition. Preserve receipts, questions, walls and previous state history.
Category disable is not expiry. Permanent user skips remain skipped. No deletion, reminder chase or resurrection after cooldown.
Receipt: reviewed exact keys, evidence-backed closure recommendations, uncertain cases and preservation checks. Zero recommendations is STATUS: nothing-to-do.
