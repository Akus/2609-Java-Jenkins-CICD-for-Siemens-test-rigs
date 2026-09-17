# TODO – growing the home lab

Ideas from [docs/DESIGN-NOTES.md](docs/DESIGN-NOTES.md) mapped onto what's actually on the desk:
one Windows box with WSL2/Docker (the "control room") and **4 × Raspberry Pi** (the "lab").
Ordered roughly by value ÷ effort; each item says what it proves for the Siemens-style setup.

Assumptions: Pis are Pi 4/5 with ≥ 2 GB RAM, on the same LAN as the Windows box, running
Raspberry Pi OS Lite 64-bit or Ubuntu Server. Adjust if some are Pi 3/Zero (they still make fine
"rigs", just not k3s nodes).

Legend: ☐ todo · 🔧 hardware needed · 🎯 what it demonstrates

---

## 0. Baseline (do first)

- ☐ Finish Docker/WSL install → `make up && make smoke` → commit → `make pipeline` green.
- ☐ Fix whatever JCasC / Grafana wrinkles show up on the first real run.
- ☐ Static IPs or DHCP reservations + hostnames for the Pis: `pi-vienna-01`, `pi-vienna-02`,
  `pi-munich-01`, `pi-munich-02` (naming them by "lab" keeps the two-site story).
- ☐ SSH keys only, `pi` user renamed, `unattended-upgrades` on. Ansible inventory for the four
  (see §3) so the rest of this list is repeatable.

---

## 1. Real rigs: the Pis replace `rig-vienna-*` containers

🎯 Physical devices behind a network, real flashing, real "it stopped responding at 2 am".

- ☐ **Cross-build `rig-sim` for arm64** – it's plain Java, so either `docker buildx --platform
  linux/arm64` and push to a local registry (§2), or just `scp` the jar and run it under systemd.
  systemd is closer to what a real rig looks like:
  ```ini
  [Service]
  Environment=RIG_ID=pi-vienna-01 RIG_LAB=vienna RIG_PORT=8080
  ExecStart=/usr/bin/java -jar /opt/rig/rig-sim.jar
  Restart=always
  ```
- ☐ Add the Pis to [rig-api/rigs.yaml](rig-api/rigs.yaml) (`host: pi-vienna-01.local` or IP) and
  to `monitoring/prometheus/prometheus.yml` `rigs` job. Keep the 3 containers as the "simulator
  pool" (label `sim`) — that *is* the digital-twin story: PR builds hit `sim`, nightly hits `pi`.
- ☐ Add Lockable Resources `pi-vienna-01` … with labels `rig vienna hw` and a `TARGET` choice
  parameter (`sim` / `hw`) in the Jenkinsfile → `lock(label: "${LAB} ${TARGET}")`.
- ☐ **Make `/flash` real**: the Pi's `/flash` endpoint writes the received jar to
  `/opt/rig/slots/{a,b}/rig-sim.jar`, flips a `current` symlink, restarts its own service, and
  reports the new version — an **A/B slot with rollback** (restore the symlink if the new jar
  doesn't answer `/health` in 30 s). This is the single most "real" thing on this list.
- ☐ **Serial console**: USB-TTL cable from one Pi's UART to the "lab agent" host 🔧 (~€5).
  `ser2net` exposes it over TCP; the pipeline tails boot logs during "Verify Boot". Proves you've
  touched something that isn't HTTP.
- ☐ **GPIO as "signals"**: LED + button per Pi 🔧. `SIMULATE_BRAKE_TRIGGER` lights the LED, the
  HIL test reads the GPIO back (or a second Pi reads it via a jumper wire = real
  hardware-in-the-loop, two devices, one wire). `gpiozero` in Python or `pi4j` in Java.
- ☐ **node_exporter** on every Pi → CPU temp, throttling flags, disk. Alert on `vcgencmd`
  throttled bits — the Pi equivalent of "board overheating".

---

## 2. MQTT heartbeats (replace HTTP polling)

🎯 Push telemetry, last-will "device vanished" detection, the transport you'd use across a VPN.

- ☐ **Mosquitto** container on the Windows box (`--profile extras`). Auth via password file; TLS
  later.
- ☐ Rig side: publish `rigs/<id>/status` (retained, every 5 s) and set a **Last Will** message
  `rigs/<id>/status = {"state":"OFFLINE"}` — the broker announces a dead rig within the keepalive
  window, no polling needed. In Java: Eclipse Paho client (one dependency).
- ☐ Broker side: `rig-api` gets an MQTT subscriber thread next to the poller; poller becomes a
  fallback for rigs without MQTT (`transport: http|mqtt` per rig in `rigs.yaml`).
- ☐ Commands over MQTT too (`rigs/<id>/cmd`) so a NATed rig behind someone's home router can still
  be driven — that's the "remote lab over flaky VPN" argument.
- ☐ **mqtt-exporter** or Telegraf → Prometheus, so Grafana can show MQTT message rates and
  last-seen per rig.
- ☐ Stretch: **Sparkplug B** payloads — the industrial-IoT MQTT convention (birth/death
  certificates, metric schemas). Niche but very "Siemens".

---

## 3. Ansible for the Pis (config as code for hardware you can't walk to)

🎯 "Versioning and deploying config to remote hardware" (interview Q8), idempotent, reviewable.

- ☐ `ansible/inventory.yml` with groups `vienna`, `munich`, `all_rigs`; `group_vars` for
  per-lab differences (Q15: one codebase, lab-specific behaviour).
- ☐ Roles: `baseline` (users, ssh, updates), `rig-agent` (java, systemd unit, rig-sim jar,
  node_exporter), `mqtt-client`.
- ☐ Jenkins job `deploy-rig-config` → `ansible-playbook --limit vienna` with `--check` first.
  Rollback = `git revert` + rerun.
- ☐ Run it from a container (`ansible/Dockerfile`) so nothing is installed on Windows.

---

## 4. k3s cluster on the Pis + Argo CD

🎯 GitOps: the lab stack itself deployed declaratively; drift visible; two "sites" from one repo.

Only worth it once §1–§3 work — it's the most effort and the least rig-specific. Realistic split:
**2 Pis = k3s (1 server + 1 agent), 2 Pis = stay bare-metal rigs**, because a rig that gets
rescheduled by a scheduler isn't a rig.

- ☐ k3s server on `pi-k3s-01`, agent on `pi-k3s-02` (`curl -sfL https://get.k3s.io | sh -`,
  ~10 min). `kubectl` from WSL via the kubeconfig.
- ☐ Convert the monitoring stack to manifests: `kube-prometheus-stack` Helm chart (Prometheus +
  Grafana + Alertmanager + node-exporter in one go). Reuse `alerts.yml` as a `PrometheusRule`,
  `rig-fleet.json` as a dashboard ConfigMap.
- ☐ `rig-api` as a Deployment + PVC (SQLite on a PVC is fine for one replica; Postgres StatefulSet
  when you want two).
- ☐ **Argo CD** on the cluster, `Application` per component pointing at `deploy/` in this repo.
  Change a replica count in git → watch Argo sync → that's the demo.
- ☐ Two Argo `ApplicationSet` environments `vienna` / `munich` with Kustomize overlays
  (different fail-rate, different rig inventory) → "same manifests, two sites, no drift".
- ☐ Jenkins **Kubernetes plugin**: build/unit-test pods on k3s (`maven:3.9-eclipse-temurin-17`
  image), HIL stage still `agent { label 'lab' }`. Proves the "disposable agents for build,
  physical agent for hardware" split.
- ☐ Keep Jenkins itself on the Windows box in Compose — moving it is work without a lesson.

---

## 5. Missing platform pieces (cheap, all containers on the Windows box)

- ☐ **Gitea** – real SCM; Jenkins multibranch pipeline via webhook; retire `file:///repo`.
- ☐ **Local registry** (`registry:2`) or Gitea's built-in package registry – pushes arm64 images
  for the Pis; `mvn deploy` for the firmware jar with version + sha256. This is the "artifact
  repository" gap.
- ☐ **Loki + Alloy** – ship `journalctl` from every Pi and container logs from Compose; add a
  Logs panel per rig to the Grafana dashboard.
- ☐ **Alertmanager → real receiver** – Telegram/Discord/ntfy.sh webhook, so a `RigDown` at 2 am
  actually buzzes the phone. Test with `docker compose stop rig-vienna-02`.
- ☐ **Smart plug per Pi** 🔧 (Tasmota/Shelly, ~€10 each) → `POST /rigs/{id}/power-cycle` in
  `rig-api` calls the plug's HTTP API. Remote power-cycle is the first thing the on-call does;
  now it's a button in the broker. Guard it: refuse if the rig is reserved by someone else.
- ☐ **Test-results table** in `rig-api` (`runs`: rig, firmware, suite, pass/fail, duration) written
  by the Jenkinsfile post-step → Grafana "pass rate per rig over 30 days". Flaky-rig detection.
- ☐ **Secrets**: move admin passwords from `.env` to Docker secrets; API key on `rig-api` mutating
  endpoints (`X-Api-Key`), key stored as a Jenkins credential. Vault is overkill here — say so.
- ☐ **Small web UI** for "run suite X on a free Vienna rig" (HTMX + FastAPI templates inside
  `rig-api`, or a Streamlit page). Interview Q14.

---

## 6. Fleet rollout simulation (the mass-IoT story, no extra hardware)

🎯 Canary / waves / auto-halt — the difference between "deploy to 3 rigs" and "deploy to 3,000 devices".

- ☐ `docker compose --scale rig-sim=30` behind the broker (drop the fixed container names for a
  scaled service; register via MQTT birth message instead of `rigs.yaml`).
- ☐ `POST /campaigns {version, cohort, waves:[1,10,50,100]}` in `rig-api`; devices *pull* the
  desired version (`GET /rigs/{id}/desired`) and self-flash; broker tracks desired vs reported.
- ☐ Auto-halt rule: Prometheus alert `CampaignCanaryFailing` (flash-failed rate in the current
  wave > 5 %) → `rig-api` pauses the campaign. Jenkins job just kicks it off and waits.
- ☐ Include the 4 Pis as the final "production" cohort. Break the firmware on purpose → watch the
  canary sims fail, the campaign halt, the Pis stay untouched. That's the demo.
- ☐ Read up on **Mender** / **Eclipse hawkBit** and note in DESIGN-NOTES how this toy maps to them.

---

## 7. Zabbix next to Prometheus (not instead of)

🎯 Two monitoring stacks, each on the layer it's good at; Grafana on top of both.

Prometheus = the software I run (rig-api, Jenkins, rig metrics with labels).
Zabbix = the infrastructure under it (Pis as hosts, network, PDUs/smart plugs, Windows box),
plus what Prometheus doesn't have: escalations, acknowledgements, maintenance windows, inventory.

- ☐ `zabbix-server-pgsql` + `zabbix-web-nginx-pgsql` + Postgres containers (`--profile zabbix`, ~1 GB RAM).
- ☐ Zabbix agent 2 on every Pi via the Ansible `baseline` role; link the "Linux by Zabbix agent" template.
- ☐ ICMP ping + SNMP/HTTP checks for the smart plugs and the router → "is the lab network alive".
- ☐ Maintenance window for the Pis during flash campaigns (so a reboot isn't an incident).
- ☐ Grafana **Zabbix datasource** plugin → add a "Lab infrastructure" row to the fleet dashboard.
- ☐ Route Zabbix triggers to the same ntfy/Telegram receiver as Alertmanager; compare the
  escalation/ack workflow with Alertmanager's lack of one — that's the interview answer.

---

## 8. ThingsBoard as the "grown-up control plane"

🎯 Off-the-shelf IoT platform: device registry, MQTT ingestion, rule chains, **OTA updates**,
dashboards with buttons for non-coders. Overlaps heavily with rig-api + §2 + §6 — the point is to
compare a product with the hand-rolled version, not to replace rig-api.

- ☐ ThingsBoard CE container + Postgres (~2 GB RAM). Create device profile `rig`, one device per
  Pi + sim, provision credentials via Ansible.
- ☐ Rigs publish the same status to ThingsBoard's MQTT (`v1/devices/me/telemetry`); dashboard
  with state timeline + an RPC button "reset" → the "engineers trigger things safely" UI (Q14).
- ☐ **OTA**: upload the firmware jar as a package, assign to device group `vienna`, watch it roll
  out; then break a build and see it fail. Write the comparison with `rig-api` campaigns into
  DESIGN-NOTES §3 (and mention Siemens' own equivalent, Insights Hub/MindSphere).
- ☐ Decide honestly afterwards which one stays; it's fine if the answer is "ThingsBoard for the
  fleet, rig-api only for reservations".

---

## 9. Security (the lab has almost none today – fix in this order)

🎯 Q12 (VPN/firewalls/least privilege) and the rail-safety angle: traceability > firewalls.

- ☐ **Segment the network**: Pis on their own VLAN/guest subnet 🔧 (managed switch or router
  guest network). Only the lab-agent host may reach rig ports; Pis may reach the Windows box only
  on MQTT + registry ports. `ufw` default-deny on the Pis.
- ☐ **Secrets**: admin passwords from `.env` → Docker secrets; `rig-api` mutating endpoints
  require `X-Api-Key` (Jenkins credential); per-device MQTT credentials (username = rig id).
- ☐ **Local CA** (`step-ca` or openssl in `ansible/pki`): TLS for Mosquitto with client certs
  (= device identity), Traefik/Caddy in front of Jenkins/Grafana/rig-api with CA-signed certs,
  certs pushed by Ansible, expiry alert in Zabbix.
- ☐ **Identity**: Keycloak/Authentik as OIDC IdP for Jenkins, Grafana, Zabbix, ThingsBoard.
  Roles `vienna-engineer` / `munich-engineer` / `lab-admin`; rig-api checks the role before
  reset/power-cycle/quarantine.
- ☐ **Signed firmware**: `cosign sign-blob` in the Jenkins Package stage, public key on the Pis,
  `/flash` verifies before switching slots. Unsigned image → rejected, alert.
- ☐ **Supply chain**: Trivy on every image in the pipeline, Renovate for pins, SBOM (`syft`)
  archived with the firmware.
- ☐ **Harden the Pis**: SSH keys only, `fail2ban`, `unattended-upgrades`, read-only root
  (overlayfs) so a bad flash can't brick the OS; only `/opt/rig/slots` writable.
- ☐ **Audit trail**: rig-api logs who/when/what for reserve/release/flash/reset/power-cycle to a
  table + Loki; Grafana "audit" panel. Rail labs care about this more than about anything above.
- ☐ **Monitoring as security**: Zabbix/Loki alerts on failed SSH logins, unknown MAC on the lab
  VLAN, cert expiry < 14 d.
- ☐ Note the real-Siemens delta in DESIGN-NOTES: corporate IdP/PKI already exist (integration, not
  building), lab network isolated from office and from production rail systems, jump hosts, no
  unauthenticated services ever.

---

## 10. Hygiene / polish (do as you go)

- ☐ GitHub Actions (or Gitea Actions) running `make test` on every push, so the repo itself has CI.
- ☐ Pin every image tag (already done) and add **Renovate** to bump them.
- ☐ Trivy scan of built images in the pipeline.
- ☐ `docs/RUNBOOK.md`: one page per alert (`RigDown`, `RigFailing`, …) written for "someone in
  the other office at 2 am". Link them via `annotations.runbook_url`.
- ☐ Short screen recording: three Vienna builds queuing on the lock + a Pi getting flashed + the
  Grafana timeline going red then quarantined. Worth more than any README in an interview.

---

## Suggested order

1. §0 → §1 (bare-metal Pis as rigs, A/B flash, one serial cable) — biggest realism gain.
2. §3 Ansible — needed anyway to keep four Pis sane.
3. §9 security basics (VLAN, secrets, API key, SSH hardening) — cheap once Ansible exists; the
   CA/OIDC/signing items can wait until §2 and §5 need them.
4. §2 MQTT — small code change, big architectural talking point.
5. §5 Gitea + registry + Loki + alert receiver — fills the obvious gaps.
6. §7 Zabbix — one evening; gives you the "two stacks, two layers" answer.
7. §6 fleet simulation — no hardware, very strong story.
8. §8 ThingsBoard — compare its OTA with your §6; keep whichever you can defend.
9. §4 k3s + Argo CD — last, on the two spare Pis, once everything else is stable.
