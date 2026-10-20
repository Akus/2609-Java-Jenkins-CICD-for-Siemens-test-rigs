#!/usr/bin/env bash
# Re-copies the small config files that docker-compose bind-mounts straight from the repo
# into the ConfigMap sources kustomize reads them from.
#
# Why a copy instead of kustomize reading the originals directly: kustomize's configMapGenerator
# `files:` refuses to read anything outside the kustomization's own directory tree (a security
# restriction `kubectl apply -k` can't relax, and symlinks don't get around it either - it
# resolves the real path first). So these live as tracked copies under kubernetes/base/, and
# this script is the "keep them in sync" step - run it after editing any of the originals below,
# then re-run `kubectl kustomize kubernetes/base` (or overlays/home-lab) to confirm no drift.
set -euo pipefail
cd "$(dirname "$0")/.."

pairs=(
  "jenkins/casc/jenkins.yaml                                    kubernetes/base/jenkins/casc/jenkins.yaml"
  "rig-api/rigs.yaml                                             kubernetes/base/rig-api/config/rigs.yaml"
  "monitoring/prometheus/prometheus.yml                          kubernetes/base/monitoring/prometheus/config/prometheus.yml"
  "monitoring/prometheus/alerts.yml                               kubernetes/base/monitoring/prometheus/config/alerts.yml"
  "monitoring/grafana/provisioning/datasources/prometheus.yml    kubernetes/base/monitoring/grafana/config/datasource-prometheus.yml"
  "monitoring/grafana/provisioning/dashboards/dashboards.yml     kubernetes/base/monitoring/grafana/config/dashboards-provider.yml"
  "monitoring/grafana/provisioning/dashboards/rig-fleet.json     kubernetes/base/monitoring/grafana/config/rig-fleet.json"
  "monitoring/alertmanager/alertmanager.yml                      kubernetes/base/extras/config/alertmanager.yml"
)

changed=0
for pair in "${pairs[@]}"; do
  read -r src dst <<<"$pair"
  if ! cmp -s "$src" "$dst" 2>/dev/null; then
    cp "$src" "$dst"
    echo "synced: $src -> $dst"
    changed=1
  fi
done
[ "$changed" -eq 0 ] && echo "already in sync"
exit 0
