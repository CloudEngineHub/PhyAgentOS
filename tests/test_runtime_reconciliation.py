from dataclasses import replace

import httpx
import pytest
from test_forge_agenttask_integration_v023 import _bound_system

from PhyAgentOS.forge.reconciliation import reconcile_runtime_references
from PhyAgentOS.forge.tool_client import ForgeToolClient
from PhyAgentOS.skill_runtime.state import RuntimeState, RuntimeStateStore


async def _unknown_task(tmp_path, monkeypatch, semantics="action"):
    coordinator, task, _, invocations, sessions, bindings = await _bound_system(
        tmp_path, monkeypatch
    )
    accepted = (
        await coordinator.start_session(task.task_id, "demo.session", {})
        if semantics == "session"
        else await coordinator.start_action(task.task_id, "demo.action", {})
    )
    invocation = accepted["data"]["invocation_id"]
    observe = coordinator.observe_session if semantics == "session" else coordinator.observe_action
    observe(task.task_id, invocation, {"ok": True, "data": {"phase": "unknown"}})
    await coordinator.finalize_task(task.task_id)
    binding = task.primary_skill_binding
    states = RuntimeStateStore(tmp_path / "states")
    state = RuntimeState(
        skill_name=binding.skill_name,
        profile=binding.runtime_profile,
        status="running",
        flow_name="paos-example-forge-local",
        gateway_url=binding.gateway_url,
        runtime_instance_id=binding.runtime_instance_id,
        gateway_identity=binding.gateway_identity,
        active_invocations=tuple(invocations),
        active_sessions=tuple(sessions),
        active_task_bindings=tuple(bindings),
    )
    states.save(state)
    return coordinator, task, invocation, state, states


@pytest.mark.parametrize("phase", ["succeeded", "failed", "cancelled", "stopped"])
@pytest.mark.parametrize("semantics", ["action", "session"])
async def test_terminal_task_unknown_execution_can_be_reconciled(
    tmp_path, monkeypatch, phase, semantics
):
    coordinator, task, invocation, state, states = await _unknown_task(
        tmp_path, monkeypatch, semantics
    )
    requests = []

    def gateway(request):
        requests.append((request.method, request.url.path))
        data = (
            {"gateway_identity": state.gateway_identity}
            if request.url.path == "/tools"
            else {"phase": phase}
        )
        return httpx.Response(200, json={"ok": True, "data": data})

    async with ForgeToolClient(state.gateway_url, transport=httpx.MockTransport(gateway)) as client:
        report = await reconcile_runtime_references(
            state.skill_name, states=states, tasks=coordinator.store, client=client
        )
    updated = coordinator.get_task(task.task_id)
    assert updated.status.value == "failed"  # preserve the original verdict
    assert updated.execution_records[0].status == phase
    released = report.released_sessions if semantics == "session" else report.released_invocations
    assert released == [invocation]
    assert not report.unresolved
    assert not states.load(state.skill_name).active_task_bindings
    assert not states.load(state.skill_name).active_invocations
    assert not states.load(state.skill_name).active_sessions
    assert requests == [("GET", "/tools"), ("GET", f"/invocations/{invocation}")]
    assert coordinator.store.has_event(task.task_id, "execution_reconciled")


@pytest.mark.parametrize(
    "failure",
    [
        "unknown",
        "running",
        "unreachable",
        "wrong_gateway",
        "wrong_invocation",
        "new_runtime",
        "missing_task",
    ],
)
async def test_uncertain_or_mismatched_facts_never_release_references(
    tmp_path, monkeypatch, failure
):
    coordinator, _, invocation, state, states = await _unknown_task(tmp_path, monkeypatch)
    if failure == "new_runtime":
        states.save(replace(state, runtime_instance_id="replacement-runtime"))
    if failure == "missing_task":
        from PhyAgentOS.forge.task import AgentTaskStore

        tasks = AgentTaskStore(tmp_path / "other-workspace")
    else:
        tasks = coordinator.store

    def gateway(request):
        if failure == "unreachable":
            raise httpx.ConnectError("offline")
        if request.url.path == "/tools":
            data = {
                "gateway_identity": "replacement"
                if failure == "wrong_gateway"
                else state.gateway_identity
            }
        else:
            data = {"phase": failure if failure in {"unknown", "running"} else "succeeded"}
            if failure == "wrong_invocation":
                data["invocation_id"] = "another-invocation"
        return httpx.Response(200, json={"ok": True, "data": data})

    async with ForgeToolClient(state.gateway_url, transport=httpx.MockTransport(gateway)) as client:
        report = await reconcile_runtime_references(
            state.skill_name, states=states, tasks=tasks, client=client
        )
    assert report.unresolved
    assert states.load(state.skill_name).active_invocations == (invocation,)
    assert states.load(state.skill_name).active_task_bindings == state.active_task_bindings


async def test_active_unknown_action_is_rechecked_on_agent_recovery(tmp_path, monkeypatch):
    coordinator, task, client, invocations, _, bindings = await _bound_system(tmp_path, monkeypatch)
    accepted = await coordinator.start_action(task.task_id, "demo.action", {})
    invocation = accepted["data"]["invocation_id"]
    coordinator.observe_action(task.task_id, invocation, {"ok": True, "data": {"phase": "unknown"}})
    updated = await coordinator.reconcile_nonterminal()
    assert client.status_calls == [invocation]
    assert updated.execution_records[0].status == "succeeded"
    assert not invocations
    assert bindings  # the task still needs finalization


async def test_runtime_changed_during_get_preserves_new_state_and_reports_no_release(
    tmp_path, monkeypatch
):
    coordinator, _, _, state, states = await _unknown_task(tmp_path, monkeypatch)

    def gateway(request):
        if request.url.path == "/tools":
            data = {"gateway_identity": state.gateway_identity}
        else:
            states.save(replace(state, runtime_instance_id="replacement-runtime"))
            data = {"phase": "succeeded"}
        return httpx.Response(200, json={"ok": True, "data": data})

    async with ForgeToolClient(state.gateway_url, transport=httpx.MockTransport(gateway)) as client:
        report = await reconcile_runtime_references(
            state.skill_name, states=states, tasks=coordinator.store, client=client
        )
    assert not report.released_invocations and not report.released_bindings
    assert report.unresolved
    assert states.load(state.skill_name).active_invocations == state.active_invocations
    assert states.load(state.skill_name).active_task_bindings == state.active_task_bindings
