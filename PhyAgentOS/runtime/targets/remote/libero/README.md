# LIBERO Remote Target

This directory contains the real LIBERO TargetWS integration.

## Components

- `proxy.py`: runtime-side `LiberoRemoteTargetProxy`, used by the PhyAgentOS
  watchdog in the `paos` environment.
- `server.py`: standalone TargetWS server for a machine that has LIBERO,
  robosuite, MuJoCo, and the benchmark assets installed. It intentionally avoids
  importing the PhyAgentOS package so it can run in a LIBERO Python 3.8
  environment.

## Start The Target Server

Run this on the LIBERO machine:

```bash
MUJOCO_GL=egl PYTHONWARNINGS=ignore \
conda run -n liberopi python PhyAgentOS/runtime/targets/remote/libero/server.py \
  --host 0.0.0.0 --port 9002 \
  --benchmark-name libero_spatial --task-id 0 --init-state-id 0 \
  --camera-height 256 --camera-width 256 \
  --max-steps 300 --num-steps-wait 10
```

The runtime target endpoint is:

```text
targetws://<libero-host>:9002
```

`target.describe` returns benchmark metadata including task list information.
`target.action_chunk` and `target.execution_status` return `episode_summary`
for benchmark artifacts.
