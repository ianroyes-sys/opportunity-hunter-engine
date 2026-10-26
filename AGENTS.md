# Opportunity Hunter — operating contract

Read this before any hunt, apply, follow-up or cull run. `autopilot/UNATTENDED.md` adds the unattended rules; `loop-specs/*.md` hold each lane's prompt.

## Outcome and authority
Find suitable opportunities (jobs, internships, scholarships, fellowships, competitions, ambassador programs) and complete truthful applications through verified submission. The owner decides, in `autopilot/CONFIG.md`, whether Apply may submit on its own or must stop before Submit. A real wall on one candidate never blocks the others.

## Sources and compact operation
- Read `profile/profile.md` and `profile/standing-answers.md` for every factual claim; read only the relevant saved material after that.
- The deterministic engine at `engine/opportunity_engine.py` selects work, deduplicates, applies scope/skip/deferral rules and prepares compact packets. `engine/ats_feed.py` tops up the queue from public Greenhouse, Ashby and Lever boards and the SimplifyJobs lists.
- Begin with the runner-provided packet; otherwise run `python3 engine/opportunity_engine.py prepare --lane <lane> --output <path>`. Use `--help` for the current interface.
- Do not reread the entire tracker, Hunt Inbox or submission archive each pass. Inspect only records cited in the packet.
- Refresh the packet after each candidate. Eight candidates per packet is a context boundary, not a quota.
- Canonical identity is official URL/requisition plus cycle. Never infer a duplicate from employer name alone.

## Safety and truth
- Never invent a factual answer, experience, availability, credential, reference or consent. One required unknown personal fact is enough to defer the candidate without asking.
- Never pay a fee or enter payment details, SSN, government ID or bank information. Never bypass CAPTCHA, anti-bot controls, MFA or assessments.
- Respect forms that prohibit AI-written answers. Exclude opportunities that need faculty recommendations unless the profile says one is available.
- Choose the resume variant from `resumes/upload/<variant>/` that matches the posting (built by `scripts/build_all_resumes.py`). Verify rendered answers and the uploaded filename before one Submit click.
- Accounts on application portals are normal steps. Store passwords with `scripts/cred.sh` (macOS Keychain); never print or commit them.

## Durable outcomes
- A user skip persists until the user explicitly reopens that exact opportunity.
- Technical friction can have a dated retry. Missing personal facts need new facts, not a timer.
- A click that may have submitted is `unverified`: reconcile portal/email evidence before any retry. Never resend blindly.
- `submitted` requires screenshot evidence plus a confirmation text/ID. Append `pipeline/SUBMISSIONS.md` once and persist the outcome with `engine record`. Accounts, drafts and filled forms are not applications.
- Never demote submitted/interview/won because a deadline passed.

## Ownership
Apply alone drives the browser. Hunt uses public search only and writes structured intake (`engine add`) or an append-only row in `pipeline/HUNT-INBOX.md`. Follow-up reads submitted evidence and writes `pipeline/FOLLOWUP.md`; it sends nothing. Cull recommends evidence-backed closures and never deletes history.
Check the project `STOP` file before every application and before Submit. Rebuild the dashboard (`python3 scripts/build_dashboard.py`) after outcomes.
