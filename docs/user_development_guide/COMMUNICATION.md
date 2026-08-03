# Forge communication boundary

PAOS communicates with Forge Gateway over asynchronous HTTP and WebSocket connections:

- `/agent/runtime/capabilities`, `/agent/runtime/status`, and `/agent/runtime/context` provide capability and live context reads.
- `/agent/sessions` creates a session; `/agent/sessions/{session_id}` is the only execution-terminal source; its cancel endpoint handles cancellation.
- `/agent/runtime/reset` performs explicit reset while PAOS has no active lineage.
- `/ws/images` and `/ws/state` provide best-effort evidence observations.

PAOS persists its own state before outbound mutation. Gateway execution responses are mapped into public contracts, while verification and recovery remain entirely on the PAOS side.
