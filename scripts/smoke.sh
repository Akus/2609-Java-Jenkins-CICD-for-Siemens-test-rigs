#!/usr/bin/env bash
# Smoke test after `make up`: every service answers, broker sees the rigs, a reserve/flash/test
# cycle works end-to-end from the host (no Jenkins involved).
set -euo pipefail
cd "$(dirname "$0")/.."

JENKINS="http://localhost:${JENKINS_PORT:-8080}"
GRAFANA="http://localhost:${GRAFANA_PORT:-3000}"
PROM="http://localhost:${PROMETHEUS_PORT:-9090}"
export RIG_API_URL="http://localhost:${RIG_API_PORT:-8000}"

pass() { printf '  \033[32m✔\033[0m %s\n' "$*"; }
fail() { printf '  \033[31m✘\033[0m %s\n' "$*"; exit 1; }
check() { local name="$1"; shift; if "$@" >/dev/null 2>&1; then pass "$name"; else fail "$name"; fi; }

echo "== Endpoints"
check "Jenkins login page"        curl -fsS "$JENKINS/login"
check "Jenkins /prometheus"       curl -fsS "$JENKINS/prometheus/"
check "rig-api /healthz"          curl -fsS "$RIG_API_URL/healthz"
check "rig-api /metrics"          curl -fsS "$RIG_API_URL/metrics"
check "Prometheus healthy"        curl -fsS "$PROM/-/healthy"
check "Grafana health"            curl -fsS "$GRAFANA/api/health"
for p in 8101 8102 8103; do
  check "rig :$p /health"          curl -fsS "http://localhost:$p/health"
  check "rig :$p /metrics"         curl -fsS "http://localhost:$p/metrics"
done

echo "== Broker inventory"
bash scripts/rig-cli.sh list
count=$(curl -fsS "$RIG_API_URL/rigs" | jq 'length')
[ "$count" -ge 3 ] && pass "broker knows $count rigs" || fail "expected >= 3 rigs, got $count"

echo "== Prometheus targets"
# cadvisor only exists in the extras profile – don't count it against the core stack
down=$(curl -fsS "$PROM/api/v1/targets" | jq -r '.data.activeTargets[] | select(.health != "up" and .labels.job != "cadvisor") | .labels.job + "/" + .labels.instance' || true)
if [ -z "$down" ]; then pass "all scrape targets up"; else echo "$down"; fail "some scrape targets down (Jenkins may still be starting)"; fi

echo "== Reserve → flash → HIL-style command → release (rig-vienna-01)"
bash scripts/rig-cli.sh wait-for-ready rig-vienna-01 --timeout 60
bash scripts/rig-cli.sh reserve rig-vienna-01 --owner smoke-test --ttl 120 >/dev/null && pass "reserved"
tmp=$(mktemp); head -c 4096 /dev/urandom > "$tmp"
bash scripts/flash-tool.sh --rig rig-vienna-01 --image "$tmp" --version "smoke-$(date +%s)" --timeout 60 && pass "flashed"
rm -f "$tmp"
res=$(curl -fsS -X POST http://localhost:8101/command -H 'Content-Type: application/json' -d '{"cmd":"SIMULATE_BRAKE_TRIGGER"}' | jq -r .result)
[ "$res" = "BRAKE_ENGAGED" ] && pass "SIMULATE_BRAKE_TRIGGER -> BRAKE_ENGAGED" || fail "unexpected command result: $res"
bash scripts/rig-cli.sh release rig-vienna-01 --owner smoke-test >/dev/null && pass "released"

echo "== Jenkins"
if curl -fsS "$JENKINS/job/rig-hil-pipeline/api/json" >/dev/null; then pass "job rig-hil-pipeline exists"; else fail "rig-hil-pipeline job missing (JCasC/Job DSL failed?)"; fi
agent=$(curl -fsS "$JENKINS/computer/lab-agent/api/json" | jq -r '.offline')
[ "$agent" = "false" ] && pass "lab-agent online" || fail "lab-agent offline – check: docker compose logs jenkins-agent"

echo
echo "All good. Open:"
echo "  Jenkins    $JENKINS   (admin / \$JENKINS_ADMIN_PASSWORD)  → run 'rig-hil-pipeline'"
echo "  Grafana    $GRAFANA"
echo "  Prometheus $PROM/alerts"
echo "  Broker     $RIG_API_URL/docs"
