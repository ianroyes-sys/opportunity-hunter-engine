#!/bin/bash
# Application-portal logins, stored in the macOS keychain — never in this repo.
#
#   cred.sh set <site> <username>    prompts for the password (never pass it as an argument)
#   cred.sh new <site> <username>    GENERATE a strong password and store it, printing nothing
#   cred.sh get <site>               prints the password, exit 1 if not stored
#   cred.sh user <site>              prints the username
#   cred.sh list                     which sites are stored
#   cred.sh rm <site>                forget one
#
# `new` exists because `set` prompts on stdin, and a headless loop run has no stdin to answer
# it with — so an application whose first page *creates an account* could never be completed
# unattended (this blocked SEO Career). `new` generates the password inside this script and
# writes it straight to the keychain: it is never typed, never passed as an argument, and
# never printed. The loop then reads it back with `get` only at the moment it fills the form.
#
# Why the keychain: the hunter submits applications unattended, and portals like Handshake
# want an account. A password in a dotfile would end up in the repo, in a log, or in a
# commit. The keychain keeps it out of all three — `get` is the only thing that ever reads
# it, and nothing in this project may echo the result into a file.
#
# Arguments are visible in `ps` output, which is why `set` prompts instead of taking the
# password on the command line.

set -uo pipefail

SERVICE_PREFIX="opportunity-hunter"
CMD="${1:-}"
SITE="${2:-}"

need_site() { [ -n "$SITE" ] || { echo "usage: cred.sh $CMD <site>" >&2; exit 2; }; }

case "$CMD" in
  set)
    need_site
    USER_NAME="${3:-}"
    [ -n "$USER_NAME" ] || { echo "usage: cred.sh set <site> <username>" >&2; exit 2; }
    printf "password for %s (%s): " "$SITE" "$USER_NAME" >&2
    stty -echo 2>/dev/null; read -r PW; stty echo 2>/dev/null; echo >&2
    [ -n "$PW" ] || { echo "empty password, nothing stored" >&2; exit 2; }
    security add-generic-password -U \
      -s "$SERVICE_PREFIX:$SITE" -a "$USER_NAME" -w "$PW" \
      -D "opportunity-hunter portal login" 2>/dev/null \
      && echo "stored $SITE ($USER_NAME)" \
      || { echo "keychain write failed" >&2; exit 3; }
    unset PW
    ;;

  new)
    need_site
    USER_NAME="${3:-}"
    [ -n "$USER_NAME" ] || { echo "usage: cred.sh new <site> <username>" >&2; exit 2; }
    if security find-generic-password -s "$SERVICE_PREFIX:$SITE" >/dev/null 2>&1; then
      echo "already stored for $SITE — use 'rm' first if you really want a new one" >&2
      exit 2
    fi
    # Keep generated passwords at 18 characters and guarantee every common portal rule.
    # Workday does not count underscore as a special character, so include `!` explicitly.
    PW="A1a!$(LC_ALL=C tr -dc 'A-Za-z0-9' < /dev/urandom | head -c 14)"
    [ ${#PW} -eq 18 ] || { echo "password generation failed" >&2; exit 3; }
    security add-generic-password -U \
      -s "$SERVICE_PREFIX:$SITE" -a "$USER_NAME" -w "$PW" \
      -D "opportunity-hunter portal login" 2>/dev/null \
      && echo "generated and stored a password for $SITE ($USER_NAME) — not printed" \
      || { echo "keychain write failed" >&2; exit 3; }
    unset PW
    ;;

  get)
    need_site
    security find-generic-password -s "$SERVICE_PREFIX:$SITE" -w 2>/dev/null || {
      echo "no stored credential for $SITE" >&2; exit 1; }
    ;;

  user)
    need_site
    security find-generic-password -s "$SERVICE_PREFIX:$SITE" 2>/dev/null \
      | awk -F'"' '/"acct"/ {print $4}' || exit 1
    ;;

  list)
    security dump-keychain 2>/dev/null \
      | awk -F'"' '/"svce".*'"$SERVICE_PREFIX"':/ {print $4}' \
      | sed "s/^$SERVICE_PREFIX://" | sort -u
    ;;

  rm)
    need_site
    security delete-generic-password -s "$SERVICE_PREFIX:$SITE" >/dev/null 2>&1 \
      && echo "removed $SITE" || { echo "nothing stored for $SITE" >&2; exit 1; }
    ;;

  *)
    sed -n '2,17p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit 2
    ;;
esac
