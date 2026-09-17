# Design notes: what's missing, how to modernize, how to roll out to a fleet

Written from the perspective of the DevOps Lab Engineer role (Budapest–Vienna–Munich test labs).
The lab in this repo is deliberately minimal; this document is the "and then what?" section.

---

## 1. What the lab does not have yet (and would need in a real setup)

Ordered by how soon you'd hit the gap.

| Gap | Why it matters | Cheapest fix | Proper fix |
|---|---|---|---|
| **Artifact repository** | Firmware must be immutable, checksummed, and retrievable by version for rollback and audit. Jenkins `archiveArtifacts` is not a registry. | Nexus OSS / JFrog Artifactory OSS container, pipeline `mvn deploy` + raw repo for `.bin` | Same, plus retention policy, promotion (`staging` → `release` repo), SBOM attached |
| **Real SCM + webhooks** | `file:///repo` is a lab hack; there is no PR trigger, no branch protection. | Gitea container + webhook to Jenkins multibranch pipeline | GitLab/GitHub + multibranch/Org folder, required status checks |
| **Secrets management** | Admin password is in `.env`; broker has no auth at all. | JCasC reads from Docker secrets; API key header on rig-api | HashiCorp Vault / Azure Key Vault + Jenkins credentials provider; OIDC on Jenkins, mTLS between agent and broker |
| **Log aggregation** | Right now: `docker compose logs`. At 2 am you need "what did rig-munich-01 log before it stopped?" | Loki + Promtail (or Alloy) containers, Grafana Explore | Same, plus rig serial console logs shipped by the lab agent |
| **Rig heartbeat over MQTT** | HTTP polling from the broker is fine for 3 rigs; at 50+ rigs across VPNs, push beats pull, and MQTT tolerates flaky links. | Mosquitto container, rigs publish `rigs/<id>/status` retained; broker subscribes | Same, with LWT ("last will") giving you instant "rig disappeared" instead of a 1-min alert |
| **Remote power control (PDU)** | The first remote fix for a hung board is a power-cycle. | `POST /rigs/{id}/power-cycle` stub calling a PDU driver (mock in lab) | Real PDU (APC/Raritan SNMP or REST) + relay board for the reset line; guarded by reservation check |
| **Serial / JTAG access** | Flashing and debugging real boards is not HTTP. | – | ser2net / USB-over-IP on the lab agent host, OpenOCD in a container, the flash tool drives the vendor loader; the pipeline contract (image in → "ready with version X" out) stays the same |
| **Test result database** | Surefire XML in Jenkins is not queryable across time ("is this test flaky on Munich rigs only?"). | Store junit summaries in the broker DB per reservation | ReportPortal / Allure TestOps, or a Postgres table + Grafana |
| **Alert routing** | Alertmanager posts to a dead webhook. | Teams/Slack webhook receiver | On-call schedule (Opsgenie/PagerDuty), inhibitions per lab, maintenance windows |
| **Backups** | `jenkins_home` and `rigs.db` live in unnamed Docker volumes. | nightly `docker run --rm -v ... tar` cron | Jenkins config is already code (JCasC) – only job history needs backup; move broker DB to Postgres with WAL archiving |
| **Non-developer UI** | Engineers without Jenkins knowledge should be able to say "run suite X on a Munich rig". | Jenkins parameterized build with clear parameter descriptions (already partly there) | Small web UI (or Backstage plugin) in front of the broker + Jenkins API with guardrails: input validation, rig availability shown up front, confirmation for destructive actions |
| **Multi-site topology** | Vienna and Munich are separate networks behind VPNs. | Per-lab Jenkins agent label (`vienna`, `munich`) – already modelled | Agent per lab on lab-local hardware; broker per lab or a central broker with a per-lab proxy; Prometheus per lab with remote-write to a central instance |
| **Lab-specific behaviour** | "Vienna wants A, Munich wants B" in one codebase. | Config per lab (`rigs.yaml` already has `lab`), shared core | Plugin/strategy pattern in the automation library: `LabProfile` objects with overrides, selected by rig metadata; tested with a matrix build |

---

## 2. How I would modernize a setup like this

The goal is not "replace Jenkins with X". Hardware labs are conservative for good reasons (safety
certification, EN 50128-style process requirements, years-old vendor tools). The goal is to move
everything that is *not* the hardware into standard, declarative, reproducible tooling, and to
keep the hardware boundary narrow and well defined.

### 2.1 Treat the rig fleet as an inventory with a control plane

* **Inventory as data, not tribal knowledge**: `rigs.yaml` today; tomorrow a proper inventory
  (NetBox is excellent for this: sites, racks, devices, IPs, custom fields like `board_rev`,
  `jtag_adapter`). The broker syncs from it.
* **Rig agent on/next to each board**: a small Go/Python daemon (or a NanoMQ/MQTT client on the
  board itself) that exposes `/status`, `/metrics`, serial console, flash hooks — exactly the
  contract the simulator implements. The pipeline never talks to vendor tools directly.
* **Broker becomes the single source of truth** for who holds what; Jenkins `lock()` mirrors it.
  Add a **capability model** (`board_type=ZUB-3`, `has_can=true`) so a pipeline asks for
  "a rig with capabilities X" rather than a name.

### 2.2 Pipelines

* **Shared pipeline library** (Jenkins Shared Library) with `withRig(label) { ... }` that does
  reserve → flash → wait → run → release, so every team's Jenkinsfile is 10 lines.
* **Separate build from HIL**: build/unit-test on cheap, disposable Kubernetes agents (Jenkins
  Kubernetes plugin or GitLab runners); only the HIL stage runs on the lab agent. Artifacts flow
  through the registry, never through the workspace.
* **Async HIL runs**: long tests should not pin a Jenkins executor. The pipeline submits a job to
  the broker (`POST /runs`), the broker drives the rig and calls back (webhook) or the pipeline
  polls with `waitUntil`. This also decouples "Jenkins down" from "test still running".
* **Flake management as a feature**: quarantine rigs (already done) *and* quarantine tests —
  track pass rates per test × rig type; auto-retry only known-flaky tests, fail fast on new failures.
* **Everything as code**: JCasC + Job DSL (done), Prometheus rules, Grafana dashboards, agent
  images — all in git, all reviewed via PR, deployed by the same pipeline they describe.

### 2.3 Platform

* **Container-first agents**: the `lab-agent` image is the model — pinned toolchain, rebuilt weekly,
  scanned (Trivy). Vendor tools that only run on Windows get a Windows agent (VM) with the same
  contract, driven by PowerShell scripts checked into the repo.
* **GitOps for the lab stack**: today Docker Compose; the next step is k3s per lab site with the
  same manifests (Helm/Kustomize) applied by Argo CD, so Vienna and Munich are guaranteed identical
  and drift is visible.
* **Observability standardization**: OpenTelemetry for traces across broker → agent → rig
  (a failing HIL test gets a trace ID linking the Jenkins step, the broker reservation and the rig's
  serial log). Loki for logs, Prometheus for metrics, Grafana for all three.
* **Identity**: Jenkins and Grafana behind the corporate IdP (OIDC/SAML); broker API with short-lived
  tokens issued per build (Jenkins → broker via a service account, humans via the IdP). Least
  privilege per lab: Munich engineers can reset Munich rigs, not Vienna's.
* **Digital twin in CI**: the rig simulator in this repo is a crude twin. Invest in it — a faithful
  simulator lets 80 % of test runs skip real hardware, reserve rigs only for the final gate, and
  gives developers a local `docker compose up` loop. (Siemens already does this for Sidytrac RT.)

### 2.4 Process

* Trunk-based development with short-lived branches; PR checks run on the simulator, `main` runs
  on hardware nightly + on demand.
* Runbooks live next to alerts (`annotations.runbook_url`), written for the person in the other
  office at 2 am, and are tested by having someone *else* follow them.
* SLOs for the lab itself: rig availability, queue wait time, mean time to reset. Once those are
  on a dashboard, capacity discussions become data-driven.

---

## 3. CI/CD for mass deployment to many IoT / embedded devices

"Deploy to 3 rigs" and "deploy to 3,000 devices in the field" are different problems. The pipeline
in this repo is the *last stage before release* — it proves an image is good. Getting that image
onto a fleet safely is a separate system with its own rules.

### 3.1 Principles

1. **Never push. Devices pull.** A device polls (or is nudged via MQTT) for its *desired* version and
   pulls the image when it can — after a maintenance window, on a good link, when not in use. Push
   deployments to devices behind NAT/VPN/flaky links are how you brick a fleet.
2. **Immutable, signed artifacts.** Every image has a version, a SHA-256, and a signature
   (cosign/Sigstore or vendor secure boot chain). Devices verify before flashing. The build
   pipeline is the only thing that can sign.
3. **A/B partitions + automatic rollback.** The device flashes to the inactive slot, reboots, runs a
   self-test, and only then marks the new slot "good"; a watchdog reverts to the old slot otherwise.
   The `flash-tool.sh` rollback path here is a toy version of that.
4. **Desired state, not commands.** The control plane stores "device X should run version Y"; the
   device reports "I am running Z". Convergence is observable; missing devices are visible as
   drift, not as lost fire-and-forget commands.
5. **Progressive rollout with automatic halt.** Canary (1 %) → 10 % → 50 % → 100 %, gated on
   health metrics reported by the devices themselves (boot success rate, crash counters, app-level
   KPIs). A regression in the canary halts the wave automatically.
6. **Cohorts.** Group devices by hardware revision, site, criticality, and maintenance window.
   Roll out per cohort; never mix "prod rail line" with "lab rigs" in one wave.

### 3.2 Reference architecture

```
git ──▶ CI (build, unit, sim tests) ──▶ HIL gate (this repo) ──▶ sign + publish to artifact registry
                                                                       │
                                                       ┌───────────────▼────────────────┐
                                                       │ Fleet control plane            │
                                                       │  • device inventory & cohorts  │
                                                       │  • rollout campaigns (waves)   │
                                                       │  • desired vs reported state   │
                                                       │  • health gates / auto-halt    │
                                                       └───────────────┬────────────────┘
                                                        MQTT (nudge) / HTTPS (pull)
                                          ┌─────────────────────────────┼─────────────────────────┐
                                          ▼                             ▼                         ▼
                                    device agent                  device agent               device agent
                                    A/B slots, verify sig,        ...                        ...
                                    self-test, report health
```

**Off-the-shelf options for the control plane** (don't build this yourself unless you must):

| Tool | Fit |
|---|---|
| **Mender** (open source + enterprise) | Purpose-built OTA for Linux devices, A/B, delta updates, cohorts, phased rollouts. Good default. |
| **Eclipse hawkBit** | Vendor-neutral rollout management with a REST/DDI API; Siemens-friendly ecosystem (Eclipse IoT). |
| **RAUC / SWUpdate** + custom control plane | Device-side updater only; pair with hawkBit (both integrate natively). |
| **AWS IoT Jobs / Azure Device Update / Azure IoT Hub** | If the fleet already lives in a cloud; strong rollout + telemetry story. |
| **Fleet management via k3s / KubeEdge / Talos** | When the device can run containers – then updates are just image tags and Argo/Flux does the rollout. |
| **Ansible / Salt** | Fine for a few hundred *reachable* Linux boxes with SSH; wrong tool for NATed field devices. |

### 3.3 CI/CD-specific issues and how to solve them

| Problem | Approach |
|---|---|
| **Heterogeneous hardware** (board rev A/B/C, different flash layouts) | Build a matrix in CI; artifacts carry a `compatible_hw` list; the control plane only offers an image to matching devices; HIL gate must include every supported revision (that's what rig pools per board type are for). |
| **Bandwidth / metered links** | Delta updates (Mender/RAUC support them), download resume, pull only in maintenance windows, local caching proxy per site. |
| **Bricking risk** | A/B + rollback + a "golden" recovery partition; the canary cohort contains *your own* lab rigs first (this repo's pipeline is literally the 0 % canary). |
| **Devices that are offline for weeks** | Desired-state model: they converge when they return; campaigns don't "finish" — they report coverage. Version-skew rules: an image must be able to update from any version N-3..N. |
| **Config vs firmware** | Separate channels: firmware (rare, heavy, signed) and configuration (frequent, small, also signed). Both versioned, both rollback-able. Never bake site config into the image. |
| **Traceability / audit (rail safety)** | Every campaign records who approved, which artifact hash, which cohorts, and per-device outcome — exportable. Pipeline attaches SBOM + test reports to the artifact; signatures make the chain verifiable. |
| **Secrets on devices** | Per-device identity (X.509 from a factory/enrollment step, TPM if available); no shared credentials; short-lived tokens for the update channel. |
| **Observability at scale** | Devices push a compact health report (boot count, active slot, version, last error) over MQTT; the control plane aggregates; Grafana shows rollout progress per cohort and the auto-halt rule watches the canary's error rate. |
| **Testing the rollout itself** | The lab simulates the fleet: hundreds of rig-sim containers behind the control plane is a cheap, realistic soak test of a campaign before any real device sees it. |
| **Emergency stop** | One button/API that pauses all campaigns and pins desired = reported; practiced in game days. |

### 3.4 How this repo maps onto that

* `rig-sim` ≈ device agent contract (status, flash, self-test, metrics).
* `rig-api` ≈ a tiny control plane: inventory, reservations (≈ cohorts), health (≈ reported state),
  quarantine (≈ auto-halt for one device).
* `flash-tool.sh` ≈ the updater with verification + rollback.
* `Jenkinsfile` ≈ the quality gate that produces a signed, proven artifact — the input of a fleet
  rollout, not the rollout itself.

Next concrete step if you wanted to grow it: add `POST /campaigns {version, cohort, wave%}` to the
broker, give the simulator an "A/B slot + self-test" behaviour, and let a Jenkins job drive a
canary → full rollout across 20 rig-sim containers with an auto-halt rule in Prometheus.
