---
name: Opportunity Followup
slug: opportunity-followup
purpose: Track submitted outcomes and interview signals; draft useful follow-ups, never chase retired manual asks.
section: external
section_order: 0
enabled: true
group: opportunity
group_name: Opportunity Engine
group_tab: FOLLOW-UP
group_order: 3
model: haiku
cwd: .
permission_mode: bypassPermissions
max_passes: 3
max_minutes: 20
width: false
outbound: none
git_backup: false
schedule_hours: 0,4,8,12,16,20
schedule_minute: 51
---

# Follow-up: real post-submission signals
Use CLAUDE.md and runner's compact packet; do not audit every historical wall/questionnaire. Use engine prepare --lane opportunity-followup if needed.
Read only relevant submitted records and recent email/source evidence. No browser, login, send, or application action. Write only pipeline/FOLLOWUP.md and the lane receipt.
Use the packet's recentSubmitted list (at most twelve recently modified submitted records) for targeted checks; its bounded fields identify the relevant records and evidence. This list is a sampling window, not the entire application history. Preserve new invitations and consequential post-submission messages even if their candidate is outside that window. Do not claim all submissions were checked or load the full archive to fill the window.
Preserve and surface actual interview invitations, awards, rejections and consequential post-submission requests with message IDs or source evidence. Category disable and user skip of prospective work never suppress real submitted outcomes.
If email authentication fails, record unavailable once; do not claim no messages or invent "under review."
Draft useful post-submission responses only; do not send. No prospective missing-fact reminders, faculty/transcript chase, or revival of skipped applications.
Include due actionable candidates from the packet, not all old blocked deadlines. Expiry recommendations require current source evidence and apply only to unsubmitted work. A past listing deadline does not expire an existing application.
Rebuild a concise dated FOLLOWUP.md with evidence-linked findings and counts. A genuinely empty check is STATUS: nothing-to-do. Do not restate unchanged walls as progress.
