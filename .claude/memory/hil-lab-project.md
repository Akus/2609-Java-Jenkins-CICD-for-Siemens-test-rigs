---
name: hil-lab-project
description: "Purpose and status of the HIL test-rig CI/CD lab repo (Siemens Mobility DevOps Lab Engineer interview prep); everything runs in Docker Compose from WSL, no host toolchains."
metadata: 
  node_type: memory
  type: project
  originSessionId: cb7a4532-255b-4397-8a78-36dd072aa597
  modified: 2026-09-17T20:51:00.777Z
---

The repo is interview prep / portfolio for the Siemens Mobility "DevOps Lab Engineer – DS Tooling"
role (Budapest, job 518173). On 2026-09-17 I built a full Docker Compose lab from the notes in
`devops-lab-engineer-context.md` §6: Jenkins (JCasC + Lockable Resources + self-registering agent),
Java rig simulator ×3, FastAPI rig broker with SQLite/Alembic, JUnit HIL tests, Prometheus/Grafana,
`scripts/rig-cli.sh` + `flash-tool.sh`, docs in `docs/`.

**Why:** The user wants a runnable demo of rig reservation, flashing, HIL testing and fleet
monitoring, plus written answers on modernization and mass IoT deployment (`docs/DESIGN-NOTES.md`).

**How to apply:**
- Build/test only inside containers (`make test`, image build stages) — the user explicitly said
  not to use local Windows binaries (no Maven wrapper, no host pytest).
- Not yet verified end-to-end as of 2026-09-17 because Docker was unavailable ([[wsl-docker-environment]]);
  first thing to do when Docker is back: `make up && make smoke`, then run `rig-hil-pipeline`.
- The Jenkins job clones `file:///repo` → files must be committed on `main` for the pipeline to see them.
