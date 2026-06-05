# OpenPI-Compatible Policy Runtime

This directory contains the OpenPI-compatible policy wire integration.

## Components

- `client.py`: websocket client used by runtime skills for `openpi://` and
  `policyws://` endpoints.
- `lerobot_pi0_server.py`: standalone websocket policy server for LeRobot
  pi0-family checkpoints. The checkpoint `config.json` `type` selects the
  LeRobot policy class: `pi0`, `pi05`, or `pi0fast`.
- `../msgpack_numpy.py`: numpy msgpack wire codec used by the OpenPI-compatible
  protocol.

## Start A pi0.5 Policy Server

Run this in the environment that has LeRobot and the pi0.5 checkpoint:

```bash
conda run -n lerobot-pi python -m PhyAgentOS.runtime.policy.openpi.lerobot_pi0_server \
  --model-dir /path/to/pi05/checkpoint \
  --host 0.0.0.0 --port 8000 --device cuda
```

The runtime policy endpoint is:

```text
openpi://<policy-host>:8000
```

On connect, the server returns metadata including `policy_type`, `backend`,
`model_dir`, `chunk_size`, `n_action_steps`, and `action_dim`.
