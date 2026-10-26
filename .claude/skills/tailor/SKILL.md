---
name: tailor
description: Add or adjust an industry-specific resume variant (tech, finance, consulting, operations...) in profile/resume.json and rebuild the PDFs.
---

# /tailor <industry> — make an industry-specific resume variant

Argument = target industry, e.g. `tech`, `finance`, `consulting`, `nonprofit`, `media`. If none is given, ask which.

## What "tailoring" means here
Same facts, different framing. The experience never changes; which achievements lead, and the vocabulary used for them, shifts to match what that industry screens for. Never invent titles, skills or metrics that are not in `profile/profile.md` or `profile/resume.json`.

## Steps
1. Read `profile/resume.json` (the single content source) and `profile/profile.md`.
2. Decide the emphasis: which entries go first, which bullets to keep, which skills group to show. Reword bullets only by adding new keyed bullets to an entry; keep the originals.
3. Add or edit a variant under `"variants"` in `profile/resume.json`.
4. Run `python3 scripts/build_all_resumes.py`. It fails if a variant spills onto a second page; trim bullets until it fits.
5. Rebuild the dashboard: `python3 scripts/build_dashboard.py`.
6. Report which achievements moved to the top and when to use this variant.

## Rules
- No fabrication. Every bullet traces to the profile.
- One page. Contact details exactly as in the profile.
