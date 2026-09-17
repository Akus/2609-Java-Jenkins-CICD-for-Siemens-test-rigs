#!/usr/bin/env bash
# flash-tool – push a firmware image to a rig, wait for it to come back, verify the version.
#
#   flash-tool.sh --rig <rig-id> --image <file> --version <ver> [--timeout <s>] [--no-rollback]
#   flash-tool.sh --rig-ip <host[:port]> --image <file> --version <ver> ...   # bypass the broker
#
# Exit codes: 0 ok · 2 flash rejected · 3 timeout · 4 verification failed (rolled back if possible)
#
# In a real lab this wraps the vendor loader (JTAG/OpenOCD/serial); the protocol to the rest of
# the pipeline stays the same: image in, "ready with version X" out, rollback on failure.
set -euo pipefail

API="${RIG_API_URL:-http://localhost:8000}"
rig="" host="" image="" version="" timeout=120 rollback=1

while [ $# -gt 0 ]; do
  case "$1" in
    --rig)         rig="$2"; shift 2 ;;
    --rig-ip)      host="$2"; shift 2 ;;
    --image)       image="$2"; shift 2 ;;
    --version)     version="$2"; shift 2 ;;
    --timeout)     timeout="$2"; shift 2 ;;
    --no-rollback) rollback=0; shift ;;
    *) echo "flash-tool: unknown option $1" >&2; exit 1 ;;
  esac
done

[ -n "$image" ] && [ -f "$image" ] || { echo "flash-tool: --image must point to an existing file" >&2; exit 1; }
[ -n "$version" ] || { echo "flash-tool: --version required" >&2; exit 1; }

if [ -z "$host" ]; then
  [ -n "$rig" ] || { echo "flash-tool: --rig or --rig-ip required" >&2; exit 1; }
  host=$(curl -fsS "$API/rigs/$rig" | jq -r '"\(.host):\(.port)"')
fi
case "$host" in *:*) ;; *) host="$host:8080" ;; esac
base="http://$host"

status() { curl -fsS --max-time 5 "$base/status" 2>/dev/null || echo '{"state":"UNREACHABLE"}'; }

previous=$(status | jq -r '.firmware // "unknown"')
sha=$(sha256sum "$image" | cut -d' ' -f1)
echo "flash-tool: ${rig:-$host} <- $image ($(stat -c%s "$image") bytes, sha256 ${sha:0:12}...) version $version (was $previous)"

# 1. push the image
http_code=$(curl -sS -o /tmp/flash-resp.json -w '%{http_code}' --max-time 60 \
  -X POST "$base/flash" \
  -H 'Content-Type: application/octet-stream' \
  -H "X-Firmware-Version: $version" \
  -H "X-Firmware-SHA256: $sha" \
  --data-binary "@$image")
if [ "$http_code" != "202" ]; then
  echo "flash-tool: rig rejected flash (HTTP $http_code): $(cat /tmp/flash-resp.json)" >&2
  exit 2
fi

# 2. wait for the board to come back
deadline=$(( $(date +%s) + timeout ))
while :; do
  state=$(status | jq -r '.state')
  case "$state" in
    IDLE)    break ;;
    FAILING) echo "flash-tool: rig reports FAILING during flash: $(status | jq -r '.last_error')" >&2; break ;;
  esac
  if [ "$(date +%s)" -ge "$deadline" ]; then
    echo "flash-tool: timeout after ${timeout}s waiting for rig (state=$state)" >&2
    exit 3
  fi
  sleep 2
done

# 3. verify
actual=$(status | jq -r '.firmware')
if [ "$state" = "IDLE" ] && [ "$actual" = "$version" ]; then
  echo "flash-tool: OK – rig runs $actual"
  exit 0
fi

echo "flash-tool: verification FAILED (state=$state firmware=$actual expected=$version)" >&2
if [ "$rollback" = "1" ]; then
  # Simulated rollback: reset the board; a real loader would re-flash the last known-good image.
  echo "flash-tool: rolling back – resetting rig to last known-good ($previous)" >&2
  curl -fsS -X POST "$base/reset" -o /dev/null || true
fi
exit 4
