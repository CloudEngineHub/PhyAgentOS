"""CLI commands for PhyAgentOS."""

import asyncio
import os
import select
import signal
import sys
from pathlib import Path

# Force UTF-8 encoding for Windows console
if sys.platform == "win32":
    if sys.stdout.encoding != "utf-8":
        os.environ["PYTHONIOENCODING"] = "utf-8"
        # Re-open stdout/stderr with UTF-8 encoding
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

import typer
from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory
from prompt_toolkit.patch_stdout import patch_stdout
from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table
from rich.text import Text

from PhyAgentOS import __logo__, __version__
from PhyAgentOS.config.paths import get_workspace_path
from PhyAgentOS.config.schema import Config
from PhyAgentOS.utils.helpers import sync_workspace_templates

app = typer.Typer(
    name="paos",
    help=f"{__logo__} PhyAgentOS - Personal AI Assistant",
    no_args_is_help=True,
)

console = Console()
EXIT_COMMANDS = {"exit", "quit", "/exit", "/quit", ":q"}
RUNTIME_PROTOCOL_TEMPLATE_FILES = {"TARGETS.md", "SKILLS.md", "SESSIONS.md"}

# ---------------------------------------------------------------------------
# CLI input: prompt_toolkit for editing, paste, history, and display
# ---------------------------------------------------------------------------

_PROMPT_SESSION: PromptSession | None = None
_SAVED_TERM_ATTRS = None  # original termios settings, restored on exit


def _flush_pending_tty_input() -> None:
    """Drop unread keypresses typed while the model was generating output."""
    try:
        fd = sys.stdin.fileno()
        if not os.isatty(fd):
            return
    except Exception:
        return

    try:
        import termios
        termios.tcflush(fd, termios.TCIFLUSH)
        return
    except Exception:
        pass

    try:
        while True:
            ready, _, _ = select.select([fd], [], [], 0)
            if not ready:
                break
            if not os.read(fd, 4096):
                break
    except Exception:
        return


def _restore_terminal() -> None:
    """Restore terminal to its original state (echo, line buffering, etc.)."""
    if _SAVED_TERM_ATTRS is None:
        return
    try:
        import termios
        termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, _SAVED_TERM_ATTRS)
    except Exception:
        pass


def _init_prompt_session() -> None:
    """Create the prompt_toolkit session with persistent file history."""
    global _PROMPT_SESSION, _SAVED_TERM_ATTRS

    # Save terminal state so we can restore it on exit
    try:
        import termios
        _SAVED_TERM_ATTRS = termios.tcgetattr(sys.stdin.fileno())
    except Exception:
        pass

    from PhyAgentOS.config.paths import get_cli_history_path

    history_file = get_cli_history_path()
    history_file.parent.mkdir(parents=True, exist_ok=True)

    _PROMPT_SESSION = PromptSession(
        history=FileHistory(str(history_file)),
        enable_open_in_editor=False,
        multiline=False,   # Enter submits (single line mode)
    )


def _print_agent_response(response: str, render_markdown: bool) -> None:
    """Render assistant response with consistent terminal styling."""
    content = response or ""
    body = Markdown(content) if render_markdown else Text(content)
    console.print()
    console.print(f"[cyan]{__logo__} PhyAgentOS[/cyan]")
    console.print(body)
    console.print()


def _is_exit_command(command: str) -> bool:
    """Return True when input should end interactive chat."""
    return command.lower() in EXIT_COMMANDS


async def _read_interactive_input_async() -> str:
    """Read user input using prompt_toolkit (handles paste, history, display).

    prompt_toolkit natively handles:
    - Multiline paste (bracketed paste mode)
    - History navigation (up/down arrows)
    - Clean display (no ghost characters or artifacts)
    """
    if _PROMPT_SESSION is None:
        raise RuntimeError("Call _init_prompt_session() first")
    try:
        with patch_stdout():
            return await _PROMPT_SESSION.prompt_async(
                HTML("<b fg='ansiblue'>You:</b> "),
            )
    except EOFError as exc:
        raise KeyboardInterrupt from exc



def version_callback(value: bool):
    if value:
        console.print(f"{__logo__} PhyAgentOS v{__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        None, "--version", "-v", callback=version_callback, is_eager=True
    ),
):
    """PhyAgentOS - Personal AI Assistant."""
    pass


# ============================================================================
# Onboard / Setup
# ============================================================================


@app.command()
def onboard():
    """Initialize PhyAgentOS configuration and workspace."""
    from PhyAgentOS.config.loader import get_config_path, load_config, save_config
    from PhyAgentOS.config.schema import Config

    config_path = get_config_path()

    if config_path.exists():
        console.print(f"[yellow]Config already exists at {config_path}[/yellow]")
        console.print("  [bold]y[/bold] = overwrite with defaults (existing values will be lost)")
        console.print("  [bold]N[/bold] = refresh config, keeping existing values and adding new fields")
        if typer.confirm("Overwrite?"):
            config = Config()
            save_config(config)
            console.print(f"[green]✓[/green] Config reset to defaults at {config_path}")
        else:
            config = load_config()
            save_config(config)
            console.print(f"[green]✓[/green] Config refreshed at {config_path} (existing values preserved)")
    else:
        config = Config()
        save_config(config)
        console.print(f"[green]✓[/green] Created config at {config_path}")

    console.print("[dim]Config template now uses `maxTokens` + `contextWindowTokens`; `memoryWindow` is no longer a runtime setting.[/dim]")

    from PhyAgentOS.embodiment_registry import EmbodimentRegistry

    registry = EmbodimentRegistry(config)
    workspace = get_workspace_path()
    if registry.is_fleet:
        shared_workspace = registry.resolve_agent_workspace()
        if not shared_workspace.exists():
            shared_workspace.mkdir(parents=True, exist_ok=True)
            console.print(f"[green]✓[/green] Created shared workspace at {shared_workspace}")
        created = registry.sync_layout()
        for instance in registry.instances(enabled_only=True):
            if instance.workspace.exists():
                console.print(f"[green]✓[/green] Ready robot workspace {instance.robot_id} at {instance.workspace}")
        workspace = shared_workspace
    else:
        if not workspace.exists():
            workspace.mkdir(parents=True, exist_ok=True)
            console.print(f"[green]✓[/green] Created workspace at {workspace}")
        sync_workspace_templates(workspace, exclude=RUNTIME_PROTOCOL_TEMPLATE_FILES)

    _setup_minecraft_workspace_from_targets(workspace)

    console.print(f"\n{__logo__} PhyAgentOS is ready!")
    console.print("\nNext steps:")
    console.print("  1. Add your API key to [cyan]~/.PhyAgentOS/config.json[/cyan]")
    console.print("     Get one at: https://openrouter.ai/keys")
    console.print("  2. Chat: [cyan]paos agent -m \"Hello!\"[/cyan]")
    console.print("\n[dim]Want Telegram/WhatsApp? See: https://github.com/HKUDS/PhyAgentOS#-chat-apps[/dim]")


def _make_provider(config: Config):
    """Create the appropriate LLM provider from config."""
    from PhyAgentOS.providers.base import GenerationSettings
    from PhyAgentOS.providers.openai_codex_provider import OpenAICodexProvider
    from PhyAgentOS.providers.azure_openai_provider import AzureOpenAIProvider

    model = config.agents.defaults.model
    provider_name = config.get_provider_name(model)
    p = config.get_provider(model)

    # OpenAI Codex (OAuth)
    if provider_name == "openai_codex" or model.startswith("openai-codex/"):
        provider = OpenAICodexProvider(default_model=model)
    # Custom: direct OpenAI-compatible endpoint, bypasses LiteLLM
    elif provider_name == "custom":
        from PhyAgentOS.providers.custom_provider import CustomProvider
        provider = CustomProvider(
            api_key=p.api_key if p else "no-key",
            api_base=config.get_api_base(model) or "http://localhost:8000/v1",
            default_model=model,
        )
    # Azure OpenAI: direct Azure OpenAI endpoint with deployment name
    elif provider_name == "azure_openai":
        if not p or not p.api_key or not p.api_base:
            console.print("[red]Error: Azure OpenAI requires api_key and api_base.[/red]")
            console.print("Set them in ~/.PhyAgentOS/config.json under providers.azure_openai section")
            console.print("Use the model field to specify the deployment name.")
            raise typer.Exit(1)
        provider = AzureOpenAIProvider(
            api_key=p.api_key,
            api_base=p.api_base,
            default_model=model,
        )
    else:
        from PhyAgentOS.providers.litellm_provider import LiteLLMProvider
        from PhyAgentOS.providers.registry import find_by_name
        spec = find_by_name(provider_name)
        if not model.startswith("bedrock/") and not (p and p.api_key) and not (spec and (spec.is_oauth or spec.is_local)):
            console.print("[red]Error: No API key configured.[/red]")
            console.print("Set one in ~/.PhyAgentOS/config.json under providers section")
            raise typer.Exit(1)
        provider = LiteLLMProvider(
            api_key=p.api_key if p else None,
            api_base=config.get_api_base(model),
            default_model=model,
            extra_headers=p.extra_headers if p else None,
            provider_name=provider_name,
        )

    defaults = config.agents.defaults
    provider.generation = GenerationSettings(
        temperature=defaults.temperature,
        max_tokens=defaults.max_tokens,
        reasoning_effort=defaults.reasoning_effort,
    )
    return provider


def _load_runtime_config(config: str | None = None, workspace: str | None = None) -> Config:
    """Load config and optionally override the active workspace."""
    from PhyAgentOS.config.loader import load_config, set_config_path

    config_path = None
    if config:
        config_path = Path(config).expanduser().resolve()
        if not config_path.exists():
            console.print(f"[red]Error: Config file not found: {config_path}[/red]")
            raise typer.Exit(1)
        set_config_path(config_path)
        console.print(f"[dim]Using config: {config_path}[/dim]")

    loaded = load_config(config_path)
    if workspace:
        if loaded.is_fleet_mode:
            loaded.embodiments.shared_workspace = workspace
        else:
            loaded.agents.defaults.workspace = workspace
    return loaded


def _print_deprecated_memory_window_notice(config: Config) -> None:
    """Warn when running with old memoryWindow-only config."""
    if config.agents.defaults.should_warn_deprecated_memory_window:
        console.print(
            "[yellow]Hint:[/yellow] Detected deprecated `memoryWindow` without "
            "`contextWindowTokens`. `memoryWindow` is ignored; run "
            "[cyan]paos onboard[/cyan] to refresh your config template."
        )


def _start_runtime_workspace_manager(config: Config):
    """Provision runtime workspace and start the session watchdog when enabled."""
    from PhyAgentOS.runtime.workspace import RuntimeWorkspaceManager

    manager = RuntimeWorkspaceManager(config)
    report = manager.start_watchdog()
    if config.runtime.enabled:
        console.print(f"[green]✓[/green] Runtime workspace: {report.workspace}")
        if report.created:
            console.print(f"  [dim]Created runtime files: {', '.join(report.created)}[/dim]")
        if report.updated:
            console.print(f"  [dim]Updated runtime files: {', '.join(report.updated)}[/dim]")
        if report.enabled_targets or report.disabled_targets:
            console.print(
                "  [dim]Target enable overrides: "
                f"enabled={report.enabled_targets or []}, disabled={report.disabled_targets or []}[/dim]"
            )
        if report.watchdog_started:
            console.print("[green]✓[/green] Runtime watchdog started")
    return manager


# ============================================================================
# Gateway / Server
# ============================================================================


@app.command()
def gateway(
    port: int | None = typer.Option(None, "--port", "-p", help="Gateway port"),
    workspace: str | None = typer.Option(None, "--workspace", "-w", help="Workspace directory"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    config: str | None = typer.Option(None, "--config", "-c", help="Path to config file"),
):
    """Start the PhyAgentOS gateway."""
    from PhyAgentOS.agent.loop import AgentLoop
    from PhyAgentOS.bus.queue import MessageBus
    from PhyAgentOS.channels.manager import ChannelManager
    from PhyAgentOS.config.paths import get_cron_dir
    from PhyAgentOS.cron.service import CronService
    from PhyAgentOS.cron.types import CronJob
    from PhyAgentOS.heartbeat.service import HeartbeatService
    from PhyAgentOS.session.manager import SessionManager

    if verbose:
        import logging
        logging.basicConfig(level=logging.DEBUG)

    from PhyAgentOS.embodiment_registry import EmbodimentRegistry

    config = _load_runtime_config(config, workspace)
    _print_deprecated_memory_window_notice(config)
    port = port if port is not None else config.gateway.port
    registry = EmbodimentRegistry(config)

    console.print(f"{__logo__} Starting PhyAgentOS gateway on port {port}...")
    if registry.is_fleet:
        registry.sync_layout()
    else:
        sync_workspace_templates(config.workspace_path, exclude=RUNTIME_PROTOCOL_TEMPLATE_FILES)
    runtime_manager = _start_runtime_workspace_manager(config)
    bus = MessageBus()
    provider = _make_provider(config)
    session_manager = SessionManager(config.workspace_path)

    # Create cron service first (callback set after agent creation)
    cron_store_path = get_cron_dir() / "jobs.json"
    cron = CronService(cron_store_path)

    # Create agent with cron service
    agent = AgentLoop(
        bus=bus,
        provider=provider,
        workspace=config.workspace_path,
        model=config.agents.defaults.model,
        max_iterations=config.agents.defaults.max_tool_iterations,
        context_window_tokens=config.agents.defaults.context_window_tokens,
        brave_api_key=config.tools.web.search.api_key or None,
        web_proxy=config.tools.web.proxy or None,
        exec_config=config.tools.exec,
        cron_service=cron,
        restrict_to_workspace=config.tools.restrict_to_workspace,
        session_manager=session_manager,
        mcp_servers=config.tools.mcp_servers,
        channels_config=config.channels,
        embodiment_registry=registry,
    )

    # Set cron callback (needs agent)
    async def on_cron_job(job: CronJob) -> str | None:
        """Execute a cron job through the agent."""
        from PhyAgentOS.agent.tools.cron import CronTool
        from PhyAgentOS.agent.tools.message import MessageTool
        reminder_note = (
            "[Scheduled Task] Timer finished.\n\n"
            f"Task '{job.name}' has been triggered.\n"
            f"Scheduled instruction: {job.payload.message}"
        )

        # Prevent the agent from scheduling new cron jobs during execution
        cron_tool = agent.tools.get("cron")
        cron_token = None
        if isinstance(cron_tool, CronTool):
            cron_token = cron_tool.set_cron_context(True)
        try:
            response = await agent.process_direct(
                reminder_note,
                session_key=f"cron:{job.id}",
                channel=job.payload.channel or "cli",
                chat_id=job.payload.to or "direct",
            )
        finally:
            if isinstance(cron_tool, CronTool) and cron_token is not None:
                cron_tool.reset_cron_context(cron_token)

        message_tool = agent.tools.get("message")
        if isinstance(message_tool, MessageTool) and message_tool._sent_in_turn:
            return response

        if job.payload.deliver and job.payload.to and response:
            from PhyAgentOS.bus.events import OutboundMessage
            await bus.publish_outbound(OutboundMessage(
                channel=job.payload.channel or "cli",
                chat_id=job.payload.to,
                content=response
            ))
        return response
    cron.on_job = on_cron_job

    # Create channel manager
    channels = ChannelManager(config, bus)

    def _pick_heartbeat_target() -> tuple[str, str]:
        """Pick a routable channel/chat target for heartbeat-triggered messages."""
        enabled = set(channels.enabled_channels)
        # Prefer the most recently updated non-internal session on an enabled channel.
        for item in session_manager.list_sessions():
            key = item.get("key") or ""
            if ":" not in key:
                continue
            channel, chat_id = key.split(":", 1)
            if channel in {"cli", "system"}:
                continue
            if channel in enabled and chat_id:
                return channel, chat_id
        # Fallback keeps prior behavior but remains explicit.
        return "cli", "direct"

    # Create heartbeat service
    async def on_heartbeat_execute(tasks: str) -> str:
        """Phase 2: execute heartbeat tasks through the full agent loop."""
        channel, chat_id = _pick_heartbeat_target()

        async def _silent(*_args, **_kwargs):
            pass

        return await agent.process_direct(
            tasks,
            session_key="heartbeat",
            channel=channel,
            chat_id=chat_id,
            on_progress=_silent,
        )

    async def on_heartbeat_notify(response: str) -> None:
        """Deliver a heartbeat response to the user's channel."""
        from PhyAgentOS.bus.events import OutboundMessage
        channel, chat_id = _pick_heartbeat_target()
        if channel == "cli":
            return  # No external channel available to deliver to
        await bus.publish_outbound(OutboundMessage(channel=channel, chat_id=chat_id, content=response))

    hb_cfg = config.gateway.heartbeat
    heartbeat = HeartbeatService(
        workspace=config.workspace_path,
        provider=provider,
        model=agent.model,
        on_execute=on_heartbeat_execute,
        on_notify=on_heartbeat_notify,
        interval_s=hb_cfg.interval_s,
        enabled=hb_cfg.enabled,
    )

    if channels.enabled_channels:
        console.print(f"[green]✓[/green] Channels enabled: {', '.join(channels.enabled_channels)}")
    else:
        console.print("[yellow]Warning: No channels enabled[/yellow]")

    cron_status = cron.status()
    if cron_status["jobs"] > 0:
        console.print(f"[green]✓[/green] Cron: {cron_status['jobs']} scheduled jobs")

    console.print(f"[green]✓[/green] Heartbeat: every {hb_cfg.interval_s}s")

    async def run():
        try:
            await cron.start()
            await heartbeat.start()
            await asyncio.gather(
                agent.run(),
                channels.start_all(),
            )
        except KeyboardInterrupt:
            console.print("\nShutting down...")
        finally:
            await agent.close_mcp()
            heartbeat.stop()
            cron.stop()
            agent.stop()
            runtime_manager.stop_watchdog()
            await channels.stop_all()

    asyncio.run(run())




# ============================================================================
# Commands
# ============================================================================

TARGET_MC_PATTERN = "minecraft_java_env"


def _setup_minecraft_workspace_from_targets(workspace: Path) -> None:
    """If TARGETS.md contains a minecraft target, set up its workspace with
    the minecraft-specific EMBODIED.md and ACTION.md."""
    targets_file = workspace / "TARGETS.md"
    if not targets_file.exists():
        return

    targets_content = targets_file.read_text(encoding="utf-8")
    if TARGET_MC_PATTERN not in targets_content:
        return

    try:
        import yaml
        targets_data = yaml.safe_load(targets_content)
    except Exception:
        return

    if not isinstance(targets_data, dict):
        return

    target_list = targets_data.get("targets", [])
    if not isinstance(target_list, list):
        return

    for target in target_list:
        if not isinstance(target, dict):
            continue
        if target.get("id") != TARGET_MC_PATTERN:
            continue
        target_workspace_rel = target.get("workspace", "workspaces/minecraft")
        target_workspace = workspace / target_workspace_rel
        target_workspace.mkdir(parents=True, exist_ok=True)

        # ── copy minecraft EMBODIED.md ──
        from importlib.resources import files as pkg_files
        try:
            tpl_dir = pkg_files("PhyAgentOS") / "templates"
            mc_embodied_src = tpl_dir / "minecraft_embodied.md"
            embodied_dst = target_workspace / "EMBODIED.md"
            if mc_embodied_src.exists() and not embodied_dst.exists():
                embodied_dst.write_text(mc_embodied_src.read_text(encoding="utf-8"), encoding="utf-8")
                console.print(f"[green]✓[/green] Created EMBODIED.md for {TARGET_MC_PATTERN} at {embodied_dst}")
        except Exception:
            pass

        # ── ensure ACTION.md exists ──
        action_file = target_workspace / "ACTION.md"
        if not action_file.exists():
            from PhyAgentOS.utils.action_queue import dump_action_document, empty_action_document
            action_file.write_text(dump_action_document(empty_action_document()), encoding="utf-8")
            console.print(f"[green]✓[/green] Created ACTION.md for {TARGET_MC_PATTERN} at {action_file}")
        break


@app.command()
def agent(
    message: str = typer.Option(None, "--message", "-m", help="Message to send to the agent"),
    session_id: str = typer.Option("cli:direct", "--session", "-s", help="Session ID"),
    workspace: str | None = typer.Option(None, "--workspace", "-w", help="Workspace directory"),
    config: str | None = typer.Option(None, "--config", "-c", help="Config file path"),
    markdown: bool = typer.Option(True, "--markdown/--no-markdown", help="Render assistant output as Markdown"),
    logs: bool = typer.Option(False, "--logs/--no-logs", help="Show PhyAgentOS runtime logs during chat"),
):
    """Interact with the agent directly."""
    from loguru import logger

    from PhyAgentOS.agent.loop import AgentLoop
    from PhyAgentOS.bus.queue import MessageBus
    from PhyAgentOS.config.paths import get_cron_dir
    from PhyAgentOS.cron.service import CronService

    from PhyAgentOS.embodiment_registry import EmbodimentRegistry

    config = _load_runtime_config(config, workspace)
    _print_deprecated_memory_window_notice(config)
    registry = EmbodimentRegistry(config)
    if registry.is_fleet:
        registry.sync_layout()
    else:
        sync_workspace_templates(config.workspace_path, exclude=RUNTIME_PROTOCOL_TEMPLATE_FILES)
    runtime_manager = _start_runtime_workspace_manager(config)

    bus = MessageBus()
    provider = _make_provider(config)

    # Create cron service for tool usage (no callback needed for CLI unless running)
    cron_store_path = get_cron_dir() / "jobs.json"
    cron = CronService(cron_store_path)

    if logs:
        logger.enable("PhyAgentOS")
    else:
        logger.disable("PhyAgentOS")

    agent_loop = AgentLoop(
        bus=bus,
        provider=provider,
        workspace=config.workspace_path,
        model=config.agents.defaults.model,
        max_iterations=config.agents.defaults.max_tool_iterations,
        context_window_tokens=config.agents.defaults.context_window_tokens,
        brave_api_key=config.tools.web.search.api_key or None,
        web_proxy=config.tools.web.proxy or None,
        exec_config=config.tools.exec,
        cron_service=cron,
        restrict_to_workspace=config.tools.restrict_to_workspace,
        mcp_servers=config.tools.mcp_servers,
        channels_config=config.channels,
        embodiment_registry=registry,
    )

    # Show spinner when logs are off (no output to miss); skip when logs are on
    def _thinking_ctx():
        if logs:
            from contextlib import nullcontext
            return nullcontext()
        # Animated spinner is safe to use with prompt_toolkit input handling
        return console.status("[dim]PhyAgentOS is thinking...[/dim]", spinner="dots")

    async def _cli_progress(content: str, *, tool_hint: bool = False) -> None:
        ch = agent_loop.channels_config
        if ch and tool_hint and not ch.send_tool_hints:
            return
        if ch and not tool_hint and not ch.send_progress:
            return
        console.print(f"  [dim]↳ {content}[/dim]")

    if message:
        # Single message mode — direct call, no bus needed
        async def run_once():
            try:
                with _thinking_ctx():
                    response = await agent_loop.process_direct(message, session_id, on_progress=_cli_progress)
                _print_agent_response(response, render_markdown=markdown)
            finally:
                runtime_manager.stop_watchdog()
                await agent_loop.close_mcp()

        asyncio.run(run_once())
    else:
        # Interactive mode — route through bus like other channels
        from PhyAgentOS.bus.events import InboundMessage
        _init_prompt_session()
        console.print(f"{__logo__} Interactive mode (type [bold]exit[/bold] or [bold]Ctrl+C[/bold] to quit)\n")

        if ":" in session_id:
            cli_channel, cli_chat_id = session_id.split(":", 1)
        else:
            cli_channel, cli_chat_id = "cli", session_id

        def _handle_signal(signum, frame):
            sig_name = signal.Signals(signum).name
            _restore_terminal()
            console.print(f"\nReceived {sig_name}, goodbye!")
            sys.exit(0)

        signal.signal(signal.SIGINT, _handle_signal)
        signal.signal(signal.SIGTERM, _handle_signal)
        # SIGHUP is not available on Windows
        if hasattr(signal, 'SIGHUP'):
            signal.signal(signal.SIGHUP, _handle_signal)
        # Ignore SIGPIPE to prevent silent process termination when writing to closed pipes
        # SIGPIPE is not available on Windows
        if hasattr(signal, 'SIGPIPE'):
            signal.signal(signal.SIGPIPE, signal.SIG_IGN)

        async def run_interactive():
            bus_task = asyncio.create_task(agent_loop.run())
            turn_done = asyncio.Event()
            turn_done.set()
            turn_response: list[str] = []

            async def _consume_outbound():
                while True:
                    try:
                        msg = await asyncio.wait_for(bus.consume_outbound(), timeout=1.0)
                        if msg.metadata.get("_progress"):
                            is_tool_hint = msg.metadata.get("_tool_hint", False)
                            ch = agent_loop.channels_config
                            if ch and is_tool_hint and not ch.send_tool_hints:
                                pass
                            elif ch and not is_tool_hint and not ch.send_progress:
                                pass
                            else:
                                console.print(f"  [dim]↳ {msg.content}[/dim]")
                        elif not turn_done.is_set():
                            if msg.content:
                                turn_response.append(msg.content)
                            turn_done.set()
                        elif msg.content:
                            console.print()
                            _print_agent_response(msg.content, render_markdown=markdown)
                    except asyncio.TimeoutError:
                        continue
                    except asyncio.CancelledError:
                        break

            outbound_task = asyncio.create_task(_consume_outbound())

            try:
                while True:
                    try:
                        _flush_pending_tty_input()
                        user_input = await _read_interactive_input_async()
                        command = user_input.strip()
                        if not command:
                            continue

                        if _is_exit_command(command):
                            _restore_terminal()
                            console.print("\nGoodbye!")
                            break

                        turn_done.clear()
                        turn_response.clear()

                        await bus.publish_inbound(InboundMessage(
                            channel=cli_channel,
                            sender_id="user",
                            chat_id=cli_chat_id,
                            content=user_input,
                        ))

                        with _thinking_ctx():
                            await turn_done.wait()

                        if turn_response:
                            _print_agent_response(turn_response[0], render_markdown=markdown)
                    except KeyboardInterrupt:
                        _restore_terminal()
                        console.print("\nGoodbye!")
                        break
                    except EOFError:
                        _restore_terminal()
                        console.print("\nGoodbye!")
                        break
            finally:
                agent_loop.stop()
                runtime_manager.stop_watchdog()
                outbound_task.cancel()
                await asyncio.gather(bus_task, outbound_task, return_exceptions=True)
                await agent_loop.close_mcp()

        asyncio.run(run_interactive())


# ============================================================================
# Channel Commands
# ============================================================================


channels_app = typer.Typer(help="Manage channels")
app.add_typer(channels_app, name="channels")


@channels_app.command("status")
def channels_status():
    """Show channel status."""
    from PhyAgentOS.channels.registry import discover_channel_names, load_channel_class
    from PhyAgentOS.config.loader import load_config

    config = load_config()

    table = Table(title="Channel Status")
    table.add_column("Channel", style="cyan")
    table.add_column("Enabled", style="green")

    for modname in sorted(discover_channel_names()):
        section = getattr(config.channels, modname, None)
        enabled = section and getattr(section, "enabled", False)
        try:
            cls = load_channel_class(modname)
            display = cls.display_name
        except ImportError:
            display = modname.title()
        table.add_row(
            display,
            "[green]\u2713[/green]" if enabled else "[dim]\u2717[/dim]",
        )

    console.print(table)


def _get_bridge_dir() -> Path:
    """Get the bridge directory, setting it up if needed."""
    import shutil
    import subprocess

    # User's bridge location
    from PhyAgentOS.config.paths import get_bridge_install_dir

    user_bridge = get_bridge_install_dir()

    # Check if already built
    if (user_bridge / "dist" / "index.js").exists():
        return user_bridge

    # Check for npm
    if not shutil.which("npm"):
        console.print("[red]npm not found. Please install Node.js >= 18.[/red]")
        raise typer.Exit(1)

    # Find source bridge: first check package data, then source dir
    pkg_bridge = Path(__file__).parent.parent / "bridge"  # PhyAgentOS/bridge (installed)
    src_bridge = Path(__file__).parent.parent.parent / "bridge"  # repo root/bridge (dev)

    source = None
    if (pkg_bridge / "package.json").exists():
        source = pkg_bridge
    elif (src_bridge / "package.json").exists():
        source = src_bridge

    if not source:
        console.print("[red]Bridge source not found.[/red]")
        console.print("Try reinstalling: pip install --force-reinstall PhyAgentOS")
        raise typer.Exit(1)

    console.print(f"{__logo__} Setting up bridge...")

    # Copy to user directory
    user_bridge.parent.mkdir(parents=True, exist_ok=True)
    if user_bridge.exists():
        shutil.rmtree(user_bridge)
    shutil.copytree(source, user_bridge, ignore=shutil.ignore_patterns("node_modules", "dist"))

    # Install and build
    try:
        console.print("  Installing dependencies...")
        subprocess.run(["npm", "install"], cwd=user_bridge, check=True, capture_output=True)

        console.print("  Building...")
        subprocess.run(["npm", "run", "build"], cwd=user_bridge, check=True, capture_output=True)

        console.print("[green]✓[/green] Bridge ready\n")
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Build failed: {e}[/red]")
        if e.stderr:
            console.print(f"[dim]{e.stderr.decode()[:500]}[/dim]")
        raise typer.Exit(1)

    return user_bridge


@channels_app.command("login")
def channels_login():
    """Link device via QR code."""
    import subprocess

    from PhyAgentOS.config.loader import load_config
    from PhyAgentOS.config.paths import get_runtime_subdir

    config = load_config()
    bridge_dir = _get_bridge_dir()

    console.print(f"{__logo__} Starting bridge...")
    console.print("Scan the QR code to connect.\n")

    env = {**os.environ}
    if config.channels.whatsapp.bridge_token:
        env["BRIDGE_TOKEN"] = config.channels.whatsapp.bridge_token
    env["AUTH_DIR"] = str(get_runtime_subdir("whatsapp-auth"))

    try:
        subprocess.run(["npm", "start"], cwd=bridge_dir, check=True, env=env)
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Bridge failed: {e}[/red]")
    except FileNotFoundError:
        console.print("[red]npm not found. Please install Node.js.[/red]")


# ============================================================================
# Status Commands
# ============================================================================


@app.command()
def status():
    """Show PhyAgentOS status."""
    from PhyAgentOS.config.loader import get_config_path, load_config

    config_path = get_config_path()
    config = load_config()
    workspace = config.workspace_path

    console.print(f"{__logo__} PhyAgentOS Status\n")

    console.print(f"Config: {config_path} {'[green]✓[/green]' if config_path.exists() else '[red]✗[/red]'}")
    console.print(f"Workspace: {workspace} {'[green]✓[/green]' if workspace.exists() else '[red]✗[/red]'}")

    if config_path.exists():
        from PhyAgentOS.providers.registry import PROVIDERS

        console.print(f"Model: {config.agents.defaults.model}")

        # Check API keys from registry
        for spec in PROVIDERS:
            p = getattr(config.providers, spec.name, None)
            if p is None:
                continue
            if spec.is_oauth:
                console.print(f"{spec.label}: [green]✓ (OAuth)[/green]")
            elif spec.is_local:
                # Local deployments show api_base instead of api_key
                if p.api_base:
                    console.print(f"{spec.label}: [green]✓ {p.api_base}[/green]")
                else:
                    console.print(f"{spec.label}: [dim]not set[/dim]")
            else:
                has_key = bool(p.api_key)
                console.print(f"{spec.label}: {'[green]✓[/green]' if has_key else '[dim]not set[/dim]'}")


# ============================================================================
# OAuth Login
# ============================================================================

provider_app = typer.Typer(help="Manage providers")
app.add_typer(provider_app, name="provider")


_LOGIN_HANDLERS: dict[str, callable] = {}


def _register_login(name: str):
    def decorator(fn):
        _LOGIN_HANDLERS[name] = fn
        return fn
    return decorator


@provider_app.command("login")
def provider_login(
    provider: str = typer.Argument(..., help="OAuth provider (e.g. 'openai-codex', 'github-copilot')"),
):
    """Authenticate with an OAuth provider."""
    from PhyAgentOS.providers.registry import PROVIDERS

    key = provider.replace("-", "_")
    spec = next((s for s in PROVIDERS if s.name == key and s.is_oauth), None)
    if not spec:
        names = ", ".join(s.name.replace("_", "-") for s in PROVIDERS if s.is_oauth)
        console.print(f"[red]Unknown OAuth provider: {provider}[/red]  Supported: {names}")
        raise typer.Exit(1)

    handler = _LOGIN_HANDLERS.get(spec.name)
    if not handler:
        console.print(f"[red]Login not implemented for {spec.label}[/red]")
        raise typer.Exit(1)

    console.print(f"{__logo__} OAuth Login - {spec.label}\n")
    handler()


@_register_login("openai_codex")
def _login_openai_codex() -> None:
    try:
        from oauth_cli_kit import get_token, login_oauth_interactive
        token = None
        try:
            token = get_token()
        except Exception:
            pass
        if not (token and token.access):
            console.print("[cyan]Starting interactive OAuth login...[/cyan]\n")
            token = login_oauth_interactive(
                print_fn=lambda s: console.print(s),
                prompt_fn=lambda s: typer.prompt(s),
            )
        if not (token and token.access):
            console.print("[red]✗ Authentication failed[/red]")
            raise typer.Exit(1)
        console.print(f"[green]✓ Authenticated with OpenAI Codex[/green]  [dim]{token.account_id}[/dim]")
    except ImportError:
        console.print("[red]oauth_cli_kit not installed. Run: pip install oauth-cli-kit[/red]")
        raise typer.Exit(1)


@_register_login("github_copilot")
def _login_github_copilot() -> None:
    import asyncio

    console.print("[cyan]Starting GitHub Copilot device flow...[/cyan]\n")

    async def _trigger():
        from litellm import acompletion
        await acompletion(model="github_copilot/gpt-4o", messages=[{"role": "user", "content": "hi"}], max_tokens=1)

    try:
        asyncio.run(_trigger())
        console.print("[green]✓ Authenticated with GitHub Copilot[/green]")
    except Exception as e:
        console.print(f"[red]Authentication error: {e}[/red]")
        raise typer.Exit(1)



# ============================================================================
# Minecraft Commands
# ============================================================================


minecraft_app = typer.Typer(help="Minecraft game agent demo")
app.add_typer(minecraft_app, name="minecraft")


@minecraft_app.command("say")
def minecraft_say(
    instruction: str = typer.Argument(help="自然语言指令，如 '挖5个橡木'"),
    bridge_url: str = typer.Option(
        "https://carucated-kattie-cryptogamic.ngrok-free.dev",
        "--url", "-u", help="Bridge HTTP API URL",
    ),
):
    """用自然语言控制 Minecraft bot"""
    import json

    config = _load_runtime_config()
    provider = _make_provider(config)

    system_prompt = (
        "你控制一个 Minecraft 机器人。将用户的请求转为 JSON action 列表。\n"
        "可用动作: move/look/dig/place/collect/craft/chat/jump/sneak/sprint/"
        "attack/interact/use/select_slot/drop/equip.\n"
        "move 参数: {dx, dy, dz, absolute: true/false} 或 {target: \"player\"/\"pig\"/...} 追踪实体\n"
        "chat 参数: {message}\n"
        "look 参数: {yaw, pitch}\n"
        "collect 参数: {block_type, count}\n"
        "dig 参数: {x, y, z}\n"
        "place 参数: {x, y, z, face}\n"
        "只返回 JSON 数组，不要其他文字。示例:\n"
        '[{\"type\":\"chat\",\"params\":{\"message\":\"收到\"}},'
        '{\"type\":\"collect\",\"params\":{\"block_type\":\"oak_log\",\"count\":5}},'
        '{\"type\":\"chat\",\"params\":{\"message\":\"完成\"}}]\n'
        "追踪玩家: [{\"type\":\"move\",\"params\":{\"target\":\"player\"}},"
        '{\"type\":\"chat\",\"params\":{\"message\":\"我来了\"}}]\n'
        "追踪实体: [{\"type\":\"move\",\"params\":{\"target\":\"pig\"}},"
        '{\"type\":\"chat\",\"params\":{\"message\":\"找到猪了\"}}]'
    )

    console.print("[dim]Paos 思考中...[/dim]")
    import asyncio

    async def _ask():
        resp = await provider.chat_with_retry(messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": instruction},
        ])
        return resp.content.strip()

    raw = asyncio.run(_ask())

    try:
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        plan = json.loads(raw)
        if not isinstance(plan, list):
            raise ValueError("not a list")
    except Exception:
        console.print(f"[red]LLM 返回格式错误: {raw[:200]}[/red]")
        raise typer.Exit(1)

    console.print(f"[dim]-> 生成 {len(plan)} 步动作[/dim]")
    for i, a in enumerate(plan):
        console.print(f"  {i+1}. {a['type']}: {a.get('params', {})}")

    from PhyAgentOS.utils.action_queue import append_action, dump_action_document, empty_action_document

    workspace = get_workspace_path()
    mc_workspace = workspace / "workspaces" / "minecraft"
    mc_workspace.mkdir(parents=True, exist_ok=True)
    action_file = mc_workspace / "ACTION.md"

    document = empty_action_document()
    for step in plan:
        action_type = step.get("type", "")
        parameters = step.get("params", {})
        if action_type:
            document = append_action(document, action_type=action_type, parameters=parameters)

    action_file.write_text(dump_action_document(document), encoding="utf-8")
    console.print(f"\n[dim]已写入 {len(plan)} 步动作到 {action_file}[/dim]")
    console.print("[dim]启动 watchdog 执行:[/dim]")
    console.print("  [cyan]python -c \"from pathlib import Path; from PhyAgentOS.runtime.watchdog.minecraft_action_runner import MinecraftActionRunner;")
    console.print(f"  r = MinecraftActionRunner(Path('{mc_workspace}'), {{'bridge_url': '{bridge_url}', 'verify_ssl': False}});")
    console.print("  r._ensure_target(); r.run_once(); r.stop()\"[/cyan]")
    console.print("\n[dim]或持续轮询:[/dim]")
    console.print("  [cyan]python -c \"from pathlib import Path; from PhyAgentOS.runtime.watchdog.minecraft_action_runner import MinecraftActionRunner;")
    console.print(f"  MinecraftActionRunner(Path('{mc_workspace}'), {{'bridge_url': '{bridge_url}', 'verify_ssl': False}}).run_forever()\"[/cyan]")


if __name__ == "__main__":
    app()

