#!/usr/bin/env bash
# rig-cli – thin wrapper around the rig broker API, used by the Jenkinsfile and by humans.
#
#   rig-cli.sh list [--lab vienna]
#   rig-cli.sh reserve <rig-id|any> [--lab vienna] --owner <who> [--ttl <seconds>]
#   rig-cli.sh release <rig-id> [--owner <who>]
#   rig-cli.sh status <rig-id>              # broker row + live rig status (JSON)
#   rig-cli.sh state <rig-id>               # just the state word, e.g. IDLE
#   rig-cli.sh host <rig-id>                # hostname the rig is reachable at
#   rig-cli.sh wait-for-ready <rig-id> [--timeout <seconds>]
#   rig-cli.sh quarantine <rig-id> --reason "<text>"
#   rig-cli.sh unquarantine <rig-id>
#   rig-cli.sh reset <rig-id>
#
# Env: RIG_API_URL (default http://localhost:8000)
set -euo pipefail

API="${RIG_API_URL:-http://localhost:8000}"
CURL=(curl -fsS --max-time 10 -H 'Content-Type: application/json')

die() { echo "rig-cli: $*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "'$1' is required"; }
need curl; need jq

cmd="${1:-}"; [ -n "$cmd" ] || die "missing command (see header for usage)"
shift
target=""
if [ $# -gt 0 ] && [[ "$1" != --* ]]; then target="$1"; shift; fi

owner="" ttl="" lab="" timeout=120 reason="manual"
while [ $# -gt 0 ]; do
  case "$1" in
    --owner)   owner="$2"; shift 2 ;;
    --ttl)     ttl="$2"; shift 2 ;;
    --lab)     lab="$2"; shift 2 ;;
    --timeout) timeout="$2"; shift 2 ;;
    --reason)  reason="$2"; shift 2 ;;
    *) die "unknown option $1" ;;
  esac
done

json_body() {  # build {"owner":..,"ttl_s":..} omitting keys that were not given
  jq -cn --arg owner "$owner" --arg ttl "$ttl" '
    (if $owner != "" then {owner: $owner} else {} end)
    + (if $ttl != "" then {ttl_s: ($ttl | tonumber)} else {} end)'
}

case "$cmd" in
  list)
    "${CURL[@]}" "$API/rigs${lab:+?lab=$lab}" \
      | jq -r '(["RIG","LAB","STATE","FIRMWARE","RESERVED_BY","QUARANTINED"] | @tsv),
               (.[] | [.id, .lab, .state, .firmware, (.reserved_by // "-"), (.quarantined|tostring)] | @tsv)' \
      | column -t
    ;;

  reserve)
    [ -n "$target" ] || die "reserve needs a rig id or 'any'"
    [ -n "$owner" ] || die "reserve needs --owner"
    if [ "$target" = "any" ]; then
      "${CURL[@]}" -X POST "$API/rigs/reserve${lab:+?lab=$lab}" -d "$(json_body)" | jq -r '.rig_id'
    else
      "${CURL[@]}" -X POST "$API/rigs/$target/reserve" -d "$(json_body)" | jq -r '.rig_id'
    fi
    ;;

  release)
    [ -n "$target" ] || die "release needs a rig id"
    "${CURL[@]}" -X POST "$API/rigs/$target/release" -d "$(json_body)" | jq -r '.detail'
    ;;

  status)
    [ -n "$target" ] || die "status needs a rig id"
    "${CURL[@]}" "$API/rigs/$target/status" | jq .
    ;;

  state)
    [ -n "$target" ] || die "state needs a rig id"
    # Prefer the live answer; fall back to the broker's last observation if the rig is unreachable.
    "${CURL[@]}" "$API/rigs/$target/status" | jq -r 'if .reachable then .live.state else .rig.state end'
    ;;

  host)
    [ -n "$target" ] || die "host needs a rig id"
    "${CURL[@]}" "$API/rigs/$target" | jq -r '.host'
    ;;

  wait-for-ready)
    [ -n "$target" ] || die "wait-for-ready needs a rig id"
    deadline=$(( $(date +%s) + timeout ))
    while :; do
      state=$("${CURL[@]}" "$API/rigs/$target/status" 2>/dev/null | jq -r 'if .reachable then .live.state else "UNREACHABLE" end' || echo UNREACHABLE)
      case "$state" in
        IDLE)    echo "$target is IDLE"; exit 0 ;;
        FAILING) die "$target is FAILING – aborting wait" ;;
      esac
      [ "$(date +%s)" -lt "$deadline" ] || die "$target not ready after ${timeout}s (last state: $state)"
      sleep 2
    done
    ;;

  quarantine)
    [ -n "$target" ] || die "quarantine needs a rig id"
    "${CURL[@]}" -X POST "$API/rigs/$target/quarantine" -d "$(jq -cn --arg r "$reason" '{reason:$r}')" | jq -r '.detail'
    ;;

  unquarantine)
    [ -n "$target" ] || die "unquarantine needs a rig id"
    "${CURL[@]}" -X DELETE "$API/rigs/$target/quarantine" | jq -r '.detail'
    ;;

  reset)
    [ -n "$target" ] || die "reset needs a rig id"
    "${CURL[@]}" -X POST "$API/rigs/$target/reset" | jq -r '.detail'
    ;;

  *) die "unknown command '$cmd'" ;;
esac
