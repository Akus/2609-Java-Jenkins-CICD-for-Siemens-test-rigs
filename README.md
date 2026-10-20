# HIL test-rig CI/CD lab

A self-contained, Docker Compose based model of a hardware-in-the-loop test lab: Jenkins builds a
Java "firmware", reserves a rig, flashes it, runs JUnit HIL tests against it and releases it; a
Python broker tracks rig state in SQLite; Prometheus + Grafana watch the fleet. Built from the
design notes in [devops-lab-engineer-context.md](devops-lab-engineer-context.md) §6.

```
                       ┌──────────────────────────────┐
   git (this repo) ───▶│ Jenkins (JCasC, Job DSL)     │  lock(label:'vienna')  ─┐ Lockable Resources
                       │  └ lab-agent (JDK17+Maven)   │◀────────────────────────┘
                       └──────┬───────────┬───────────┘
        mvn build/test        │           │ scripts/rig-cli.sh · flash-tool.sh
                              ▼           ▼
                   ┌────────────────┐   ┌────────────────────────────┐
                   │ rig-api        │──▶│ rig-vienna-01  rig-vienna-02│  Java rig simulators
                   │ FastAPI+SQLite │◀──│ rig-munich-01              │  /status /command /flash /metrics
                   │ poller+watchdog│   └────────────────────────────┘
                   └───────┬────────┘              ▲
                           │ /metrics              │ /metrics
                           ▼                       │
                   ┌────────────────┐   ┌──────────┴─────┐
                   │ Prometheus     │──▶│ Grafana        │  fleet dashboard, alerts
                   └────────────────┘   └────────────────┘
```

## Prerequisites

Everything runs in containers — there's no Maven/JDK/Python to install on the host, only the
tools below.

* **WSL2** with an Ubuntu (or other systemd-capable) distro
* **Docker**, either:
  * Docker Engine installed *inside* the WSL distro (recommended — self-contained, doesn't
    depend on a Windows-side GUI toggle), **or**
  * Docker Desktop for Windows with WSL2 integration enabled for the distro
* `make`, `curl`, `jq`, `git` in WSL (`sudo apt install make curl jq git`)
* ~4 GB RAM free for the stack; first `make up` pulls/builds ~2 GB of images

Clone (or open) the repo **inside WSL**. It works from `/mnt/e/...` too, but bind mounts are
noticeably faster from the Linux filesystem (`~/repos/...`).

<details>
<summary>Installing Docker Engine directly in WSL (Ubuntu 24.04)</summary>

If `docker` isn't on `PATH` inside the distro, or resolves to the Windows binary under
`/mnt/c/...` (Docker Desktop's WSL integration isn't enabled/working), install Docker Engine
natively — it only needs systemd, which WSL2 supports (`ps -p 1 -o comm=` should print
`systemd`):

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg jq

sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update

sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable docker --now
sudo usermod -aG docker "$USER"     # open a new shell (or `newgrp docker`) for this to take effect
```

Verify with `docker run --rm hello-world` and `docker compose version`.

</details>

## Quick start

```bash
cp .env.example .env          # optional: change passwords/ports
make up                       # build + start core stack
make smoke                    # wait ~90 s for Jenkins, then verify everything end-to-end
```

| Service | URL | Login |
|---|---|---|
| Jenkins | http://localhost:8080 | admin / admin (`.env`) |
| Grafana – *Test-rig fleet* dashboard | http://localhost:3000 | anonymous viewer; admin / admin to edit |
| Prometheus (targets, alerts) | http://localhost:9090 | – |
| Rig broker API (OpenAPI UI) | http://localhost:8000/docs | – |
| Rig simulators | http://localhost:8101 · 8102 · 8103 | – |
| `make up-extras`: SQLite browser | http://localhost:8081 | – |
| `make up-extras`: Alertmanager | http://localhost:9093 | – |
| `make up-extras`: cAdvisor | http://localhost:8082 | – |

## Run the pipeline

The Jenkins job `rig-hil-pipeline` clones `file:///repo` (this repo, bind-mounted), so it sees
**committed** content on `main`. Commit first, then:

```bash
make pipeline                 # or: Jenkins UI → rig-hil-pipeline → Build with Parameters
```

Stages: `Build → Unit Tests → Package → Reserve Rig → Flash Firmware → Verify Boot → HIL Tests → Report`,
and `post { always }` releases the rig on the broker even if the build blows up.

Things to try:

* Start **three** Vienna builds back-to-back: two run in parallel on `rig-vienna-01/02`, the third
  waits on the lock (*Manage Jenkins → Lockable Resources* shows who holds what).
* Run with `LAB=munich`: that rig has a 15 % fault rate, so flashes/tests fail now and then – watch
  the retry, then the quarantine path (`QUARANTINE_ON_FAILURE`).
* `rig-watchdog` runs every 10 min and mirrors broker quarantine into Jenkins reservations.

## Chaos demo (monitoring path)

```bash
make chaos-fault              # rig-munich-01 → FAILING
# Grafana: state timeline turns red; Prometheus /alerts: RigFailing (30 s), then RigQuarantined
make rigs                     # broker shows FAILING, then quarantined=true after 3 polls
make chaos-reset              # reset the board + lift quarantine
docker compose stop rig-vienna-02   # → RigDown + RigUnreachableByBroker; `start` it again to recover
```

## Working with rigs from the shell

```bash
export RIG_API_URL=http://localhost:8000
scripts/rig-cli.sh list
scripts/rig-cli.sh reserve any --lab vienna --owner me --ttl 600
scripts/rig-cli.sh status rig-vienna-01
scripts/flash-tool.sh --rig rig-vienna-01 --image some.bin --version 2.0.0
scripts/rig-cli.sh release rig-vienna-01 --owner me
```

## Tests

```bash
make test           # rig-api: ruff + pytest · rig-sim: mvn test — all inside containers
```

The HIL suite (`hil-tests/`, maven-failsafe `*IT`) needs a live rig; Jenkins runs it, or:

```bash
docker run --rm --network lab -v "$PWD/hil-tests:/src" -w /src maven:3.9.8-eclipse-temurin-17 \
  mvn -B verify -Drig.host=rig-vienna-01 -Drig.port=8080
```

## Layout

| Path | What |
|---|---|
| `docker-compose.yml`, `.env.example`, `Makefile` | the lab |
| `Jenkinsfile` | HIL pipeline (declarative + `lock()` + broker calls) |
| `jenkins/` | controller image, plugin list, JCasC (`casc/jenkins.yaml`), agent image, watchdog pipeline |
| `rig-sim/` | Java 17 rig board simulator (state machine, HTTP API, Prometheus metrics, unit tests) |
| `hil-tests/` | `RigClient` + JUnit 5 integration tests (failsafe) |
| `rig-api/` | FastAPI broker: SQLAlchemy models, Alembic migration, poller, watchdog, pytest suite |
| `monitoring/` | Prometheus scrape + alert rules, Alertmanager, Grafana datasource + dashboard |
| `scripts/` | `rig-cli.sh`, `flash-tool.sh`, `smoke.sh` |
| `docs/` | [ARCHITECTURE.md](docs/ARCHITECTURE.md), [DESIGN-NOTES.md](docs/DESIGN-NOTES.md) (what's missing, modernization, mass IoT rollout) |
| `kubernetes/` | Kustomize manifests to run this same stack on a cluster instead of `docker compose` – see [kubernetes/README.md](kubernetes/README.md) |

## Troubleshooting

| Symptom | Check |
|---|---|
| `lab-agent` offline | `docker compose logs jenkins-agent` – it polls the controller for its JNLP secret; controller must be healthy first |
| Job `rig-hil-pipeline` missing | `docker compose logs jenkins \| grep -i -E 'casc\|dsl'` – JCasC/Job DSL error |
| Pipeline can't clone `file:///repo` | files must be committed on `main`; from `/mnt/...` ensure the repo isn't marked unsafe (`safe.directory=*` is set in both images) |
| Rig "already reserved" after a crash | broker TTL frees it (default 30 min); `scripts/rig-cli.sh release <rig>` frees it now |
| Grafana panels empty | Prometheus → Status → Targets; Jenkins target is red until Jenkins finished booting |
| Ports clash | change `*_PORT` in `.env` |
