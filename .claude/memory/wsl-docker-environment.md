---
name: wsl-docker-environment
description: "WSL/Docker on this Windows box was broken on 2026-09-17; user is reinstalling. Don't probe WSL or run docker from the Windows side unless asked."
metadata: 
  node_type: memory
  type: project
  originSessionId: cb7a4532-255b-4397-8a78-36dd072aa597
  modified: 2026-09-17T20:50:49.157Z
---

On 2026-09-17 WSL commands hung/returned nothing and the user said "leave WSL, I'll fix it";
later that day Docker was being (re)installed. The user does not want me to probe `wsl.exe`
or run `docker` on the Windows host until they say it's ready.

**Why:** Probing a half-installed WSL/Docker wastes turns and produced timeouts; the user
handles the host-side setup themselves.

**How to apply:** Prepare files and static checks only; ask before running anything that
needs WSL or the Docker daemon. When Docker is back, the verification path is
`make up && make smoke` from WSL (see [[hil-lab-project]]).
