# Kubernetes manifests

Lift-and-shift of [docker-compose.yml](../docker-compose.yml)'s core stack onto a Kubernetes
cluster, targeting the 2× Raspberry Pi 4B (8GB, ARM64) home lab described in the sibling
`2608-k8s-home-lab` repo (kubeadm, Calico, MetalLB, local-path-provisioner). Same Kustomize
base/overlay layout as `2607-flux-simple-kubernetes-cluster` and `2608-k8s-home-lab`, so this
folder should feel familiar if you've looked at either.

```
kubernetes/
├── base/                  # every workload, generic (no registry, no real secrets)
│   ├── jenkins/           ├── rig-api/       ├── monitoring/prometheus/
│   ├── jenkins-agent/     ├── rig-sim/       ├── monitoring/grafana/
│   └── extras/            # optional: alertmanager + sqlite-web (docker-compose's --profile extras)
└── overlays/
    └── home-lab/          # the Pi cluster: real image registry + admin credentials
```

## Before you deploy

**1. Have the 4 custom images on GHCR.** `prom/prometheus`, `grafana/grafana` and
`prom/alertmanager` are pulled as-is (already multi-arch); Jenkins, the agent, `rig-api` and
`rig-sim` are built from this repo's own Dockerfiles by GitHub Actions
(`.github/workflows/image-*.yml`, sharing `build-image.yml`): every push to `main` that touches
an image's folder builds it natively for `linux/amd64` and `linux/arm64` and pushes
`ghcr.io/akus/2609-<name>:latest` plus `:sha-<commit>`. Run a workflow by hand from the Actions
tab (`workflow_dispatch`) to force a rebuild, e.g. to pick up a new Jenkins LTS or plugin
versions. `rig-api`'s image is only pushed if its test stage (ruff + pytest) passes.

The packages must be **public** so the nodes can pull without an `imagePullSecret`: after the
first run, check each one under the repo's *Packages* → *Package settings* → *Change
visibility*.

**2. Set real admin credentials:**

```bash
cp kubernetes/overlays/home-lab/secrets.env.example kubernetes/overlays/home-lab/secrets.env
# edit JENKINS_ADMIN_PASSWORD / GRAFANA_ADMIN_PASSWORD in secrets.env – it's gitignored
```

**3. Have a `local-path` StorageClass.** Rancher's local-path-provisioner (the "simple"
storage option in `2608-k8s-home-lab`'s README) registers itself as `local-path`, which every
PVC here uses. If your cluster is on Longhorn instead, change `storageClassName` in the
`pvc.yaml` files (or drop the field for the cluster default).

## Deploy

```bash
kubectl apply -k kubernetes/overlays/home-lab
kubectl -n hil-lab get pods -w
```

Add `- ../../base/extras` to the overlay's `resources:` to also get sqlite-web and
Alertmanager (see `base/extras/kustomization.yaml` for why they're opt-in, not default).

Everything is reached through ingress-nginx's MetalLB IP
(`kubectl -n ingress-nginx get svc ingress-nginx-controller`, `192.168.1.240` on the home lab)
by hostname — point these at it in the router's DNS or `/etc/hosts`:

| URL | |
|---|---|
| http://jenkins.home.lan | Jenkins (login from `secrets.env`) |
| http://grafana.home.lan | Grafana, rig fleet dashboard (anonymous view) |
| http://prometheus.home.lan | Prometheus |
| http://rig-api.home.lan/docs | rig broker API |

To pick up newly built images (all tagged `latest`, so they're always re-pulled):
`kubectl -n hil-lab rollout restart deploy`.

## What changed vs. docker-compose, and why

- **`file:///repo` → the GitHub remote.** Under compose, the JCasC job DSL clones the
  bind-mounted `file:///repo`. The job URL is now `${LAB_REPO_URL:-file:///repo}`: compose leaves
  it unset (unchanged behaviour), the `jenkins` Deployment sets it to this repo's GitHub URL. So
  on the cluster a change to the `Jenkinsfile` or `scripts/` is live as soon as it's **pushed** to
  `main` (not just committed), with no pod restart. The JCasC root URL works the same way via
  `JENKINS_PUBLIC_URL` (set by the overlay to the Ingress hostname).
- **Bind-mounted config files → ConfigMaps generated from tracked copies.** `jenkins/casc/jenkins.yaml`,
  `rig-api/rigs.yaml` and the Prometheus/Grafana config all get mounted from ConfigMaps
  instead of directories. They're generated from copies under `base/*/config/` (or `base/jenkins/casc/`)
  rather than the originals directly, because kustomize's `configMapGenerator` refuses to read
  files outside its own directory (a restriction `kubectl apply -k` can't relax — see the comment
  in `base/kustomization.yaml`). Run `kubernetes/sync-config.sh` after editing any of the
  originals, then re-run `kubectl kustomize kubernetes/base` to check for drift before applying.
- **cAdvisor dropped, on purpose.** It reads `/var/lib/docker`, which doesn't exist under
  containerd (what `2608-k8s-home-lab`'s nodes run), and kubelet already exposes the same
  per-container CPU/memory metrics natively — nothing to add.
- **LoadBalancer ports → Ingress hostnames.** Compose publishes host ports; here every Service
  is `ClusterIP` and the `home-lab` overlay adds one Ingress per UI on ingress-nginx (already
  running behind MetalLB on the home lab). Plain HTTP; no cert-manager on this cluster.

## Known gaps

- `coleifer/sqlite-web` (the `extras` layer) — confirm it actually publishes an `arm64`
  manifest before relying on it; unverified as of writing.
- `sqlite-web` mounts the same `ReadWriteOnce` `rig-api-data` PVC as `rig-api`. With
  local-path-provisioner that only works if both pods land on the same node — there's no pod
  affinity set up to force that, so it may fail to schedule on a 2-node cluster.
- Deployed to the home lab (all pods Ready, every Prometheus target up except `cadvisor`,
  which `monitoring/prometheus/prometheus.yml` still lists for compose), but the HIL pipeline
  hasn't been run end-to-end on the cluster yet.
- Resource requests/limits are sized for a 2×8GB Pi cluster with headroom to spare; revisit
  if you add more to the `extras` layer or run parallel Jenkins builds like the root
  README's demo suggests.
