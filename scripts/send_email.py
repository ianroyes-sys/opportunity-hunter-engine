#!/usr/bin/env python3
"""
Send real email from your Gmail account, headlessly.

    send_email.py --to programs@example.org --subject "Application: Example Fellowship" \
                  --body-file draft.md [--attach resumes/upload/business/Your_Resume.pdf] [--cc x@example.org]
    send_email.py ... --dry-run          # print the message, send nothing

Why this exists: the Gmail MCP the hunter used to rely on only has `create_draft` — there is
no send tool, and a scheduled run has no browser session to press Send in. Outreach emails
(recommendation-letter asks, program inquiries, follow-ups) sat as drafts for weeks. This
uses the `gws` CLI (Google Workspace CLI), OAuth-authed to your account, which works headless, so the
loop can actually send them. It also attaches local files — something drafts could never do,
which is why "attach the resume yourself" used to be a manual step on every outreach email.

SAFETY
- Outbound. Only loops whose spec says `outbound: allowed` may call this, and every send
  must be logged as a receipt by the caller.
- Never send to a list, never bulk-send, never send anything the account owner would not send themselves.
- `--dry-run` prints exactly what would go out; use it whenever unsure.
"""

import argparse
import base64
import json
import mimetypes
import os
import subprocess
import sys
from email.message import EmailMessage

GWS = os.environ.get("GWS_BIN", os.path.expanduser("~/.local/bin/gws"))


def build(args):
    msg = EmailMessage()
    msg["To"] = args.to
    msg["Subject"] = args.subject
    if args.cc:
        msg["Cc"] = args.cc
    if args.reply_to:
        msg["Reply-To"] = args.reply_to

    body = open(args.body_file, encoding="utf-8").read() if args.body_file else (args.body or "")
    if not body.strip():
        sys.exit("refusing to send an empty body")
    msg.set_content(body)

    for path in args.attach or []:
        if not os.path.isfile(path):
            sys.exit(f"attachment not found: {path}")
        ctype, encoding = mimetypes.guess_type(path)
        maintype, _, subtype = (ctype or "application/octet-stream").partition("/")
        with open(path, "rb") as fh:
            msg.add_attachment(fh.read(), maintype=maintype, subtype=subtype,
                               filename=os.path.basename(path))
    return msg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--to", required=True)
    ap.add_argument("--subject", required=True)
    ap.add_argument("--body")
    ap.add_argument("--body-file")
    ap.add_argument("--cc")
    ap.add_argument("--reply-to")
    ap.add_argument("--attach", action="append")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    msg = build(args)

    if args.dry_run:
        print("--- DRY RUN, nothing sent ---")
        print(f"To: {args.to}")
        if args.cc:
            print(f"Cc: {args.cc}")
        print(f"Subject: {args.subject}")
        for p in args.attach or []:
            print(f"Attach: {p}")
        print("---")
        print(msg.get_body(preferencelist=("plain",)).get_content())
        return

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    out = subprocess.run(
        [GWS, "gmail", "users", "messages", "send",
         "--params", json.dumps({"userId": "me"}),
         "--json", json.dumps({"raw": raw})],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        sys.exit(f"send failed:\n{out.stderr or out.stdout}")

    try:
        res = json.loads(out.stdout[out.stdout.index("{"):])
        print(f"sent id={res.get('id')} thread={res.get('threadId')}")
    except Exception:
        print(out.stdout.strip())


if __name__ == "__main__":
    main()
