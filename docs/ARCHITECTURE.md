# Architecture

## Components and data flow

```mermaid
flowchart LR
    subgraph ci [CI]
        J[Jenkins controller<br/>JCasC · Job DSL · Lockable Resources]
        A[lab-agent<br/>JDK 17 · Maven · python3]
        J -- JNLP/WebSocket --> A
    end

    subgraph broker [Rig broker]
        API[rig-api<br/>FastAPI]
        DB[(SQLite<br/>rigs · reservations · status_history)]
        P[poller<br/>every 5 s]
        W[watchdog<br/>TTL expiry]
        API --- DB
        P --- DB
        W --- DB
    end

    subgraph rigs [Simulated rigs]
        R1[rig-vienna-01]
        R2[rig-vienna-02]
        R3[rig-munich-01]
    end

    subgraph mon [Monitoring]
        PR[Prometheus<br/>+ alert rules]
        G[Grafana]
        AM[Alertmanager<br/>extras]
        PR --> G
        PR -.-> AM
    end

    A -- "reserve / release / quarantine<br/>(scripts/rig-cli.sh)" --> API
    A -- "POST /flash · GET /status<br/>(flash-tool.sh, HIL tests)" --> R1
    P -- "GET /status" --> R1 & R2 & R3
    PR -- "/prometheus" --> J
    PR -- "/metrics" --> API
    PR -- "/metrics (heartbeat)" --> R1 & R2 & R3
```

## Pipeline sequence

```mermaid
sequenceDiagram
    participant J as Jenkins (lab-agent)
    participant L as Lockable Resources
    participant B as rig-api
    participant R as rig-vienna-01

    J->>J: mvn compile · test · package (firmware-1.0.N.bin)
    J->>L: lock(label: vienna, quantity: 1)
    L-->>J: RIG = rig-vienna-01
    J->>B: POST /rigs/rig-vienna-01/reserve {owner, ttl 1500s}
    B-->>J: 201 reservation
    J->>R: POST /flash (bytes, X-Firmware-Version)
    R-->>J: 202 FLASHING
    loop until IDLE or timeout
        J->>R: GET /status
    end
    J->>R: HIL tests: POST /command SIMULATE_BRAKE_TRIGGER …
    R-->>J: BRAKE_ENGAGED
    J->>J: junit reports · hil-report.txt
    J->>B: POST /rigs/rig-vienna-01/release  (post { always })
    J->>L: unlock
```

## Rig state machine (rig-sim)

```mermaid
stateDiagram-v2
    [*] --> IDLE
    IDLE --> BUSY: POST /command
    BUSY --> IDLE: done (~1 s)
    BUSY --> FAILING: random fault (FAIL_RATE)
    IDLE --> FLASHING: POST /flash
    FLASHING --> IDLE: verified (FLASH_SECONDS)
    FLASHING --> FAILING: verification failed
    IDLE --> FAILING: POST /fault (chaos)
    FAILING --> IDLE: POST /reset
```

The broker adds two derived states: `UNREACHABLE` (poll failed) and `UNKNOWN` (never polled).

## Why two locking mechanisms?

| | Lockable Resources (Jenkins) | Broker reservation (rig-api) |
|---|---|---|
| Scope | Jenkins builds only | anything: Jenkins, humans, other tools |
| Queueing | built in – builds wait on the lock | none – 409, caller retries/queues |
| Survives Jenkins crash | lock is released when the build dies | TTL + watchdog force-release |
| Knows rig health | no | yes – refuses FAILING/quarantined rigs |
| Audit trail | build log | `reservations` table, `/reservations` |

In production you would keep one as the source of truth (usually the broker) and have the other
mirror it – that's what `jenkins/pipelines/watchdog.Jenkinsfile` does for quarantine.

## Port map

| Port | Service |
|---|---|
| 8080 | Jenkins (50000: inbound agent TCP, unused when WebSocket) |
| 8000 | rig-api |
| 8101–8103 | rig simulators (container port 8080) |
| 9090 | Prometheus |
| 3000 | Grafana |
| 8081 / 9093 / 8082 | sqlite-web / Alertmanager / cAdvisor (extras) |

All containers share the `lab` Docker network; service names are DNS names (`rig-api`, `rig-vienna-01`, …).
