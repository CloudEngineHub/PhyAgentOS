"""Minecraft game agent CLI commands."""

from __future__ import annotations

import asyncio
import json
import os
import time

import typer
from rich.console import Console

console = Console()

minecraft_app = typer.Typer(help="Minecraft game agent demo")

_MC_SYSTEM_PROMPT = (
    "你是 Minecraft 机器人控制器。将用户指令转为 JSON 动作列表。\n"
    "可用动作: move/look/jump/sneak/sprint/chat/collect/"
    "dig/place/attack/interact/use/select_slot/drop/equip/craft.\n"
    "move 参数: {forward: N} — N 步沿面朝方向前进（负值后退），或 {target: \"player\"/\"pig\"/...} 追踪实体\n"
    "look 参数: {yaw, pitch} — 角度制。0=南 90=西 180=北 -90=东\n"
    "jump 参数: {}\n"
    "chat 参数: {message}\n"
    "dig 参数: {x, y, z} — 需要绝对坐标。不知道坐标时不要用 dig\n"
    "place 参数: {x, y, z, face} — face: 0=下 1=上 2=北 3=南 4=西 5=东\n"
    "select_slot 参数: {slot: 0-8}\n"
    "collect 参数: {block_type, count} — 自动寻找并采集。采集方块请用 collect，不要用 dig\n"
    "只返回 JSON 数组。示例:\n"
    '[{"type":"chat","params":{"message":"收到"}},'
    '{"type":"collect","params":{"block_type":"oak_log","count":5}}]\n'
    "后退3步: [{\"type\":\"move\",\"params\":{\"forward\":-3}}]\n"
    "右转走3步: [{\"type\":\"look\",\"params\":{\"yaw\":-90}},"
    '{"type":"move","params":{"forward":3}}]\n'
    "赴约: [{\"type\":\"move\",\"params\":{\"target\":\"player\"}},"
    '{"type":"chat","params":{"message":"我来了"}}]'
)


@minecraft_app.command("say")
def minecraft_say(
    instruction: str = typer.Argument(help="自然语言指令，如 '挖5个橡木'"),
    bridge_url: str = typer.Option(
        "https://carucated-kattie-cryptogamic.ngrok-free.dev",
        "--url", "-u", help="Bridge HTTP API URL",
    ),
):
    """用自然语言控制 Minecraft bot"""
    from PhyAgentOS.cli.commands import _load_runtime_config, _make_provider  # noqa: E402

    config = _load_runtime_config()
    provider = _make_provider(config)

    console.print("[dim]Paos 思考中...[/dim]")

    async def _ask():
        resp = await provider.chat_with_retry(messages=[
            {"role": "system", "content": _MC_SYSTEM_PROMPT},
            {"role": "user", "content": instruction},
        ])
        return resp.content.strip()

    raw = asyncio.run(_ask())

    try:
        if "```" in raw:
            plan_raw = raw.split("```")[1]
            if plan_raw.startswith("json"):
                plan_raw = plan_raw[4:]
            plan = json.loads(plan_raw)
        else:
            plan = json.loads(raw)
        if not isinstance(plan, list):
            raise ValueError("not a list")
    except Exception:
        console.print(f"[red]LLM 返回格式错误: {raw[:200]}[/red]")
        raise typer.Exit(1)

    console.print(f"[dim]-> 生成 {len(plan)} 步动作[/dim]")
    for i, a in enumerate(plan):
        console.print(f"  {i+1}. {a['type']}: {a.get('params', {})}")

    from PhyAgentOS.runtime.schemas import SessionSpec, AdapterPlan
    from PhyAgentOS.runtime.skills.game.minecraft_skill_runtime import MinecraftSkillRuntime
    from PhyAgentOS.runtime.adapters.minecraft.minecraft_adapter import MinecraftTargetAdapter
    from PhyAgentOS.runtime.targets.game.minecraft_target import MinecraftTarget

    target = MinecraftTarget({"bridge_url": bridge_url, "verify_ssl": False})
    session = SessionSpec(
        session_id=f"sess_cli_{os.urandom(3).hex()}",
        target_ref="target://minecraft_java_env",
        skill_ref="skill://minecraft_navigate",
        task_description=instruction,
        execution={"max_steps": len(plan) + 5},
        runtime_hints={"perception_queries": plan},
    )

    console.print()
    result = MinecraftSkillRuntime().run(
        session, target, MinecraftTargetAdapter(),
        None, [], None,
        AdapterPlan(target_adapter="target_adapter://minecraft_adapter"),
    )
    console.print(f"\n[green]完成: {result.num_steps} 步, status={result.status}[/green]")


@minecraft_app.command("listen")
def minecraft_listen(
    bridge_url: str = typer.Option(
        "https://carucated-kattie-cryptogamic.ngrok-free.dev",
        "--url", "-u", help="Bridge HTTP API URL",
    ),
    poll_interval: float = typer.Option(
        3.0, "--interval", "-i", help="轮询间隔（秒）",
    ),
    prefix: str = typer.Option(
        "paos", "--prefix", "-p", help="游戏内指令前缀",
    ),
):
    """监听 Minecraft 聊天，自动响应带前缀的消息"""
    from PhyAgentOS.cli.commands import _load_runtime_config, _make_provider  # noqa: E402

    config = _load_runtime_config()
    provider = _make_provider(config)

    from PhyAgentOS.runtime.schemas import SessionSpec, AdapterPlan
    from PhyAgentOS.runtime.skills.game.minecraft_skill_runtime import MinecraftSkillRuntime
    from PhyAgentOS.runtime.adapters.minecraft.minecraft_adapter import MinecraftTargetAdapter
    from PhyAgentOS.runtime.targets.game.minecraft_target import MinecraftTarget
    from PhyAgentOS.runtime.watchdog.errors import TargetConnectionError

    target = MinecraftTarget({"bridge_url": bridge_url, "verify_ssl": False})
    try:
        target.build()
    except TargetConnectionError as e:
        console.print(f"[red]连接失败: {e}[/red]")
        raise typer.Exit(1)

    console.print(f"[green]✓[/green] 已连接 bridge，监听游戏聊天中... (前缀: {prefix}, 间隔: {poll_interval}s)")
    console.print("[dim]在游戏里说 'paos 挖5个橡木' 即可触发[/dim]")
    console.print("[dim]Ctrl+C 停止[/dim]\n")

    seen: set[str] = set()
    first_poll = True

    try:
        while True:
            obs = target.observe()
            chats = obs.get("last_chats", [])
            if not isinstance(chats, list):
                time.sleep(poll_interval)
                continue

            if first_poll:
                first_poll = False
                for c in chats:
                    if isinstance(c, dict):
                        key = f"{c.get('username','')}:{c.get('message','')}:{c.get('time',0)}"
                        seen.add(key)
                console.print("[dim]已跳过历史消息，等待新指令...[/dim]")
                time.sleep(poll_interval)
                continue

            for c in chats:
                if not isinstance(c, dict):
                    continue
                username = c.get("username", "")
                message = c.get("message", "")
                chat_time = c.get("time", 0)
                key = f"{username}:{message}:{chat_time}"
                if key in seen:
                    continue
                seen.add(key)

                if str(username).lower() == "paos":
                    continue

                stripped = message.strip()
                if not stripped.lower().startswith(prefix.lower()):
                    continue

                instruction = stripped[len(prefix):].strip()
                if not instruction:
                    continue

                console.print(f"[游戏] <{username}> {message}")

                async def _ask():
                    resp = await provider.chat_with_retry(messages=[
                        {"role": "system", "content": _MC_SYSTEM_PROMPT},
                        {"role": "user", "content": instruction},
                    ])
                    return resp.content.strip()

                try:
                    raw = asyncio.run(_ask())
                except Exception:
                    console.print("[red]LLM 调用失败[/red]")
                    continue

                try:
                    if "```" in raw:
                        plan_raw = raw.split("```")[1]
                        if plan_raw.startswith("json"):
                            plan_raw = plan_raw[4:]
                        plan = json.loads(plan_raw)
                    else:
                        plan = json.loads(raw)
                    if not isinstance(plan, list):
                        raise ValueError("not a list")
                except Exception:
                    console.print(f"[red]LLM 返回格式错误: {raw[:200]}[/red]")
                    continue

                console.print(f"  → 生成 {len(plan)} 步动作")
                for i, a in enumerate(plan):
                    console.print(f"    {i+1}. {a['type']}: {a.get('params', {})}")

                session = SessionSpec(
                    session_id=f"sess_chat_{os.urandom(3).hex()}",
                    target_ref="target://minecraft_java_env",
                    skill_ref="skill://minecraft_navigate",
                    task_description=instruction,
                    execution={"max_steps": len(plan) + 5},
                    runtime_hints={"perception_queries": plan},
                )
                try:
                    result = MinecraftSkillRuntime().run(
                        session, target, MinecraftTargetAdapter(),
                        None, [], None,
                        AdapterPlan(target_adapter="target_adapter://minecraft_adapter"),
                    )
                    console.print(f"  [green]完成: {result.num_steps} 步, status={result.status}[/green]")
                except Exception as e:
                    console.print(f"  [red]执行异常: {e}[/red]")

            time.sleep(poll_interval)
    except KeyboardInterrupt:
        target.close()
        console.print("\n已停止")


@minecraft_app.command("tp")
def minecraft_tp(
    x: float = typer.Argument(help="X 坐标"),
    y: float = typer.Argument(help="Y 坐标"),
    z: float = typer.Argument(help="Z 坐标"),
    bridge_url: str = typer.Option(
        "https://carucated-kattie-cryptogamic.ngrok-free.dev",
        "--url", "-u", help="Bridge HTTP API URL",
    ),
):
    """传送 bot 到指定坐标"""
    from PhyAgentOS.runtime.targets.game.minecraft_target import MinecraftTarget
    from PhyAgentOS.runtime.watchdog.errors import TargetConnectionError

    target = MinecraftTarget({"bridge_url": bridge_url, "verify_ssl": False})
    try:
        target.build()
    except TargetConnectionError as e:
        console.print(f"[red]连接失败: {e}[/red]")
        raise typer.Exit(1)

    target.step({"type": "move", "params": {"dx": x, "dy": y, "dz": z, "absolute": True}})
    console.print(f"[green]✓[/green] bot 已传送到 ({x}, {y}, {z})")
    target.close()
