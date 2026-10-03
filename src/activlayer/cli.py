"""Rich command-line control plane for ActivLayer Community Edition."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

import httpx
import typer
from rich import box
from rich.console import Console
from rich.json import JSON
from rich.markup import escape
from rich.panel import Panel
from rich.prompt import Confirm
from rich.table import Table
from rich.tree import Tree

from . import __version__
from .agent import (
    AgentError,
    AgentRepository,
    AgentValidationError,
    parse_value,
    set_path,
    topological_order,
    validate_agent,
)
from .catalog import NODE_CATALOG, node_help
from .design_assistant import DesignAssistant, DesignAssistantError
from .graph_runtime import GraphRuntime
from .knowledge import SharedKnowledge
from .llm import PROVIDER_DEFAULTS, LLMError, client_from_workspace, detect_local_providers
from .memory import AgentMemory
from .runtime import ActivLayerError
from .spec import RunStatus
from .workspace import MAX_USERS, Workspace, WorkspaceError, slugify

console = Console()
error_console = Console(stderr=True)
app = typer.Typer(
    name="activlayer",
    help="Build and operate governed AI workers from your terminal.",
    no_args_is_help=True,
    invoke_without_command=True,
    rich_markup_mode="rich",
)
config_app = typer.Typer(help="Inspect and change environment configuration.")
user_app = typer.Typer(help=f"Manage the organization users (maximum {MAX_USERS}).")
llm_app = typer.Typer(help="Configure OpenAI-compatible local or remote model providers.")
connector_app = typer.Typer(help="Configure HTTP connectors used by integration nodes.")
extension_app = typer.Typer(help="Manage explicitly installed runtime extensions.")
agent_app = typer.Typer(help="Create, provision, inspect, edit, and publish Agent Workers.")
node_app = typer.Typer(help="Navigate and edit the nodes of an agent graph.")
run_app = typer.Typer(help="Start, inspect, approve, and resume durable runs.")
knowledge_app = typer.Typer(help="Manage the shared organization knowledge base.")
memory_app = typer.Typer(help="Inspect an individual worker's isolated memory.")
agent_app.add_typer(node_app, name="node")
app.add_typer(config_app, name="config")
app.add_typer(user_app, name="user")
app.add_typer(llm_app, name="llm")
app.add_typer(connector_app, name="connector")
app.add_typer(extension_app, name="extension")
app.add_typer(agent_app, name="agent")
app.add_typer(run_app, name="run")
app.add_typer(knowledge_app, name="knowledge")
app.add_typer(memory_app, name="memory")


def _die(message: str, code: int = 1) -> None:
    error_console.print(f"[bold red]Error:[/bold red] {message}")
    raise typer.Exit(code)


def _workspace(ctx: typer.Context) -> Workspace:
    home = (ctx.obj or {}).get("home")
    try:
        if home:
            root = Path(home).expanduser().resolve()
            if not (root / "config.json").exists():
                raise WorkspaceError(f"No ActivLayer environment at {root}")
            return Workspace(root)
        return Workspace.discover()
    except WorkspaceError as error:
        _die(str(error))
        raise


def _repo(ctx: typer.Context) -> AgentRepository:
    return AgentRepository(_workspace(ctx))


def _require_executable(workspace: Workspace, agent: dict[str, Any]) -> None:
    errors = AgentRepository(workspace).relationship_errors(agent, published_required=True)
    errors.extend(GraphRuntime(workspace).execution_errors(agent))
    if errors:
        raise AgentValidationError(errors)


def _json_input(value: str) -> dict[str, Any]:
    path = Path(value)
    try:
        payload = (
            json.loads(path.read_text(encoding="utf-8")) if path.exists() else json.loads(value)
        )
    except (OSError, json.JSONDecodeError) as error:
        _die(f"Input must be a JSON object or the path to a JSON file: {error}")
    if not isinstance(payload, dict):
        _die("Input JSON must be an object")
    return payload


def _table(title: str, columns: list[str]) -> Table:
    table = Table(title=title, box=box.ROUNDED, header_style="bold violet")
    for column in columns:
        table.add_column(column)
    return table


@app.callback()
def main(
    ctx: typer.Context,
    home: Annotated[
        Path | None,
        typer.Option("--home", envvar="ACTIVLAYER_HOME", help="Environment directory."),
    ] = None,
    version: Annotated[bool, typer.Option("--version", help="Show the installed version.")] = False,
) -> None:
    """ActivLayer Community Edition command-line control plane."""
    if version:
        console.print(f"ActivLayer Community Edition [bold]{__version__}[/bold]")
        raise typer.Exit()
    ctx.obj = {"home": home}


@app.command()
def init(
    organization: Annotated[str, typer.Option("--organization", "-o", prompt=True)],
    owner: Annotated[str | None, typer.Option("--owner", help="Initial owner email.")] = None,
    path: Annotated[Path, typer.Option("--path", help="Environment directory.")] = Path(
        ".activlayer"
    ),
    detect_llm: Annotated[
        bool,
        typer.Option(
            "--detect-llm/--no-detect-llm",
            help="Discover Ollama, vLLM, and llama.cpp on local standard ports.",
        ),
    ] = True,
) -> None:
    """Create a single-organization ActivLayer environment."""
    try:
        workspace = Workspace.initialize(path, organization, owner_email=owner)
    except (WorkspaceError, ValueError) as error:
        _die(str(error))
    detected: list[dict[str, Any]] = []
    if detect_llm:
        with console.status("[cyan]Discovering local model providers...[/cyan]"):
            detected = detect_local_providers()
        config = workspace.config
        for provider in detected:
            if not provider["models"]:
                continue
            config["providers"][provider["name"]] = {
                "type": provider["type"],
                "base_url": provider["base_url"],
                "model": provider["models"][0],
                "api_key_env": None,
                "timeout_seconds": 120,
            }
            if not config.get("active_provider"):
                config["active_provider"] = provider["name"]
        workspace.save_config(config)
    configured = [provider for provider in detected if provider["models"]]
    if configured:
        provider_text = "\n".join(
            f"  [green]✓[/green] {escape(provider['type'])} · {escape(provider['models'][0])}"
            for provider in configured
        )
        next_step = "Next: [cyan]activlayer agent new 'My Worker'[/cyan]"
    elif detected:
        provider_text = (
            "  [yellow]Detected a local server, but it has no models installed.[/yellow]"
        )
        next_step = "Next: install a model, then run [cyan]activlayer llm add --help[/cyan]"
    else:
        provider_text = "  [yellow]No local model provider detected.[/yellow]"
        next_step = "Next: [cyan]activlayer llm add local --type ollama --model <model>[/cyan]"
    console.print(
        Panel.fit(
            f"[bold green]Environment ready[/bold green]\n"
            f"Organization  [bold]{escape(organization)}[/bold]\n"
            f"Home          {escape(str(workspace.root))}\n\n"
            f"[bold]Local model discovery[/bold]\n{provider_text}\n\n"
            f"{next_step}",
            title="ActivLayer",
            border_style="violet",
        )
    )


@app.command()
def status(ctx: typer.Context) -> None:
    """Show an environment dashboard."""
    workspace = _workspace(ctx)
    config = workspace.config
    repo = AgentRepository(workspace)
    drafts = repo.list(published=False)
    published = repo.list(published=True)
    runs = GraphRuntime(workspace).store.list_runs(limit=200)
    statuses: dict[str, int] = {}
    for run in runs:
        statuses[run.status.value] = statuses.get(run.status.value, 0) + 1
    body = Table.grid(padding=(0, 2))
    body.add_column(style="bold cyan")
    body.add_column()
    body.add_row("Organization", config["organization"]["name"])
    body.add_row("Environment", str(workspace.root))
    body.add_row("Users", f"{len(workspace.users)} / {MAX_USERS}")
    body.add_row("LLM provider", config.get("active_provider") or "[yellow]not configured[/yellow]")
    body.add_row("Agents", f"{len(drafts)} draft · {len(published)} published")
    body.add_row(
        "Runs", " · ".join(f"{count} {name}" for name, count in statuses.items()) or "none"
    )
    console.print(Panel(body, title="[bold]ActivLayer Environment[/bold]", border_style="violet"))


@app.command()
def guide() -> None:
    """Show the recommended end-to-end workflow."""
    console.print(
        Panel(
            "[bold]1. Create an environment[/bold]\n"
            "   activlayer init --organization 'My Organization' --owner owner@example.com\n\n"
            "[bold]2. Confirm the discovered model server[/bold]\n"
            "   activlayer llm list\n"
            "   activlayer llm test\n"
            "   # If none was detected: activlayer llm add local --type ollama "
            "--model qwen3:8b\n\n"
            "[bold]3. Provision or design an agent[/bold]\n"
            "   activlayer agent provision worker.json --publish\n"
            "   activlayer agent node list worker-id\n"
            "   activlayer agent node set worker-id analyze "
            "data.config.prompt 'Analyze {input}'\n\n"
            "[bold]4. Run and inspect[/bold]\n"
            '   activlayer run start worker-id --input \'{"request": "..."}\'\n'
            "   activlayer run list\n"
            "   activlayer run show <run-id>\n\n"
            "Use [cyan]activlayer <group> --help[/cyan] for every command and option.",
            title="Community Edition workflow",
            border_style="cyan",
        )
    )


@app.command()
def doctor(ctx: typer.Context) -> None:
    """Check local configuration and provider connectivity."""
    workspace = _workspace(ctx)
    checks: list[tuple[str, bool, str]] = []
    checks.append(("Configuration", workspace.config_path.exists(), str(workspace.config_path)))
    checks.append(
        (
            "Secrets permissions",
            (workspace.root / "secrets.json").stat().st_mode & 0o077 == 0,
            "mode 600 expected",
        )
    )
    checks.append(
        ("User limit", len(workspace.users) <= MAX_USERS, f"{len(workspace.users)} / {MAX_USERS}")
    )
    provider = workspace.config.get("active_provider")
    if provider:
        try:
            models = client_from_workspace(workspace).models()
            checks.append(("LLM endpoint", True, f"{provider} · {len(models)} model(s)"))
        except (LLMError, WorkspaceError) as error:
            checks.append(("LLM endpoint", False, str(error)))
    else:
        checks.append(("LLM endpoint", False, "No active provider"))
    table = _table("Environment doctor", ["Check", "Status", "Detail"])
    for name, passed, detail in checks:
        table.add_row(name, "[green]PASS[/green]" if passed else "[red]FAIL[/red]", detail)
    console.print(table)
    if not all(item[1] for item in checks):
        raise typer.Exit(1)


@app.command()
def serve(
    ctx: typer.Context,
    host: Annotated[str, typer.Option("--host")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port", "-p")] = 8787,
    reload: Annotated[bool, typer.Option("--reload")] = False,
) -> None:
    """Run the self-hosted ActivLayer HTTP API."""
    import uvicorn

    from .api import create_app

    workspace = _workspace(ctx)
    console.print(
        Panel.fit(
            f"Environment  {workspace.root}\n"
            f"API          http://{host}:{port}\n"
            f"OpenAPI      http://{host}:{port}/docs",
            title="ActivLayer server",
            border_style="violet",
        )
    )
    if reload:
        error_console.print(
            "[yellow]--reload is unavailable with an injected workspace; "
            "starting normally.[/yellow]"
        )
    uvicorn.run(create_app(workspace), host=host, port=port)


@config_app.command("show")
def config_show(ctx: typer.Context) -> None:
    """Print configuration with secrets excluded."""
    console.print(JSON.from_data(_workspace(ctx).config))


@config_app.command("get")
def config_get(ctx: typer.Context, path: str) -> None:
    """Read a dotted configuration property."""
    value: Any = _workspace(ctx).config
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            _die(f"Unknown configuration property: {path}")
        value = value[part]
    console.print_json(data=value)


@config_app.command("set")
def config_set(ctx: typer.Context, path: str, value: str) -> None:
    """Set a dotted configuration property using a JSON or string value."""
    workspace = _workspace(ctx)
    if path.startswith("organization.max_users"):
        _die(f"The Community Edition user ceiling is fixed at {MAX_USERS}")
    config = workspace.config
    set_path(config, path, parse_value(value))
    workspace.save_config(config)
    console.print(f"[green]Updated[/green] {path}")


@user_app.command("list")
def user_list(ctx: typer.Context) -> None:
    """List organization users."""
    users = _workspace(ctx).users
    table = _table(f"Users · {len(users)}/{MAX_USERS}", ["ID", "Name", "Email", "Role", "Status"])
    for user in users:
        table.add_row(
            user["id"],
            user["name"],
            user["email"],
            user["role"],
            "active" if user["active"] else "disabled",
        )
    console.print(table)


@user_app.command("add")
def user_add(
    ctx: typer.Context,
    email: str,
    name: Annotated[str, typer.Option("--name", "-n")] = "User",
    role: Annotated[str, typer.Option("--role", help="owner, admin, or member")] = "member",
) -> None:
    """Add a user to the organization."""
    workspace = _workspace(ctx)
    users = workspace.users
    if len(users) >= MAX_USERS:
        _die(f"Community Edition supports at most {MAX_USERS} users")
    email = email.strip().lower()
    if any(user["email"] == email for user in users):
        _die(f"User already exists: {email}")
    if role not in {"owner", "admin", "member"}:
        _die("Role must be owner, admin, or member")
    users.append(
        {
            "id": os.urandom(8).hex(),
            "email": email,
            "name": name,
            "role": role,
            "active": True,
            "created_at": datetime.now(UTC).isoformat(),
        }
    )
    workspace.save_users(users)
    console.print(f"[green]Added[/green] {email} as {role}")


@user_app.command("remove")
def user_remove(
    ctx: typer.Context, email: str, yes: Annotated[bool, typer.Option("--yes", "-y")] = False
) -> None:
    """Remove an organization user."""
    workspace = _workspace(ctx)
    users = workspace.users
    match = next((user for user in users if user["email"] == email.strip().lower()), None)
    if not match:
        _die(f"Unknown user: {email}")
    if match["role"] == "owner" and sum(user["role"] == "owner" for user in users) == 1:
        _die("Cannot remove the only owner")
    if not yes and not Confirm.ask(f"Remove {email}?"):
        raise typer.Abort()
    workspace.save_users([user for user in users if user is not match])
    console.print(f"[green]Removed[/green] {email}")


@user_app.command("token")
def user_token(ctx: typer.Context, email: str) -> None:
    """Issue a new API token. The previous token stops working immediately."""
    workspace = _workspace(ctx)
    try:
        token = workspace.issue_token(email)
    except WorkspaceError as error:
        _die(str(error))
    console.print(
        Panel.fit(
            f"[bold]{token}[/bold]\n\n"
            "Store this token now; only its hash remains in the environment.",
            title=f"Access token · {email}",
            border_style="yellow",
        )
    )


@llm_app.command("add")
def llm_add(
    ctx: typer.Context,
    name: str,
    provider_type: Annotated[
        str, typer.Option("--type", help="ollama, vllm, llama-cpp, or openai-compatible")
    ] = "openai-compatible",
    model: Annotated[str, typer.Option("--model", "-m")] = "",
    base_url: Annotated[str | None, typer.Option("--base-url")] = None,
    api_key: Annotated[
        str | None, typer.Option("--api-key", help="Stored locally with mode 600.")
    ] = None,
    api_key_env: Annotated[
        str | None,
        typer.Option("--api-key-env", help="Read the key from this environment variable."),
    ] = None,
    timeout: Annotated[int, typer.Option("--timeout")] = 120,
    activate: Annotated[bool, typer.Option("--activate/--no-activate")] = True,
) -> None:
    """Add an OpenAI-compatible inference provider."""
    workspace = _workspace(ctx)
    if provider_type not in PROVIDER_DEFAULTS:
        _die(f"Unknown provider type: {provider_type}")
    if not model:
        _die("--model is required")
    config = workspace.config
    secret_name = api_key_env
    if api_key:
        secret_name = f"ACTIVLAYER_LLM_{slugify(name).replace('-', '_').upper()}_API_KEY"
        workspace.set_secret(secret_name, api_key)
    config["providers"][name] = {
        "type": provider_type,
        "base_url": (base_url or PROVIDER_DEFAULTS[provider_type]).rstrip("/"),
        "model": model,
        "api_key_env": secret_name,
        "timeout_seconds": timeout,
    }
    if activate or not config.get("active_provider"):
        config["active_provider"] = name
    workspace.save_config(config)
    console.print(f"[green]Configured[/green] {name} · {provider_type} · {model}")


@llm_app.command("list")
def llm_list(ctx: typer.Context) -> None:
    """List configured model providers."""
    config = _workspace(ctx).config
    table = _table("LLM providers", ["", "Name", "Type", "Model", "Endpoint"])
    for name, provider in config["providers"].items():
        table.add_row(
            "●" if name == config.get("active_provider") else "",
            name,
            provider["type"],
            provider["model"],
            provider["base_url"],
        )
    console.print(table)


@llm_app.command("use")
def llm_use(ctx: typer.Context, name: str) -> None:
    """Select the default model provider."""
    workspace = _workspace(ctx)
    config = workspace.config
    if name not in config["providers"]:
        _die(f"Unknown provider: {name}")
    config["active_provider"] = name
    workspace.save_config(config)
    console.print(f"[green]Active provider:[/green] {name}")


@llm_app.command("test")
def llm_test(
    ctx: typer.Context,
    name: str | None = None,
    prompt: Annotated[str | None, typer.Option("--prompt")] = None,
) -> None:
    """Check an endpoint and optionally send a chat completion."""
    workspace = _workspace(ctx)
    try:
        client = client_from_workspace(workspace, name)
        models = client.models()
        model_summary = ", ".join(models[:8]) or "none reported"
        console.print(f"[green]Connected[/green] · {len(models)} model(s): {model_summary}")
        if prompt:
            response = client.chat([{"role": "user", "content": prompt}], max_tokens=200)
            console.print(Panel(response.content, title=f"{response.model}", border_style="cyan"))
    except (LLMError, WorkspaceError) as error:
        _die(str(error))


@llm_app.command("remove")
def llm_remove(ctx: typer.Context, name: str) -> None:
    """Remove a provider configuration and its locally stored key."""
    workspace = _workspace(ctx)
    config = workspace.config
    provider = config["providers"].pop(name, None)
    if not provider:
        _die(f"Unknown provider: {name}")
    workspace.delete_secret(provider.get("api_key_env"))
    if config.get("active_provider") == name:
        config["active_provider"] = next(iter(config["providers"]), None)
    workspace.save_config(config)
    console.print(f"[green]Removed[/green] {name}")


@connector_app.command("add")
def connector_add(
    ctx: typer.Context,
    name: str,
    base_url: Annotated[str, typer.Option("--base-url")],
    api_key: Annotated[str | None, typer.Option("--api-key")] = None,
    api_key_env: Annotated[str | None, typer.Option("--api-key-env")] = None,
    auth_header: Annotated[str, typer.Option("--auth-header")] = "Authorization",
    auth_prefix: Annotated[str, typer.Option("--auth-prefix")] = "Bearer ",
) -> None:
    """Add an HTTP connector for integration nodes."""
    workspace = _workspace(ctx)
    secret_name = api_key_env
    if api_key:
        secret_name = f"ACTIVLAYER_CONNECTOR_{slugify(name).replace('-', '_').upper()}_API_KEY"
        workspace.set_secret(secret_name, api_key)
    config = workspace.config
    config["connectors"][name] = {
        "base_url": base_url.rstrip("/"),
        "api_key_env": secret_name,
        "auth_header": auth_header,
        "auth_prefix": auth_prefix,
    }
    workspace.save_config(config)
    console.print(f"[green]Configured connector[/green] {name}")


@connector_app.command("list")
def connector_list(ctx: typer.Context) -> None:
    """List configured HTTP connectors."""
    table = _table("Connectors", ["Name", "Base URL", "Authentication"])
    for name, connector in _workspace(ctx).config["connectors"].items():
        table.add_row(name, connector["base_url"], connector.get("api_key_env") or "none")
    console.print(table)


@connector_app.command("test")
def connector_test(
    ctx: typer.Context, name: str, path: Annotated[str, typer.Option("--path")] = "/"
) -> None:
    """Send a GET request to a connector."""
    workspace = _workspace(ctx)
    connector = workspace.config["connectors"].get(name)
    if not connector:
        _die(f"Unknown connector: {name}")
    headers: dict[str, str] = {}
    secret = workspace.resolve_secret(connector.get("api_key_env"))
    if secret:
        headers[connector.get("auth_header", "Authorization")] = (
            f"{connector.get('auth_prefix', 'Bearer ')}{secret}"
        )
    try:
        response = httpx.get(
            f"{connector['base_url']}/{path.lstrip('/')}", headers=headers, timeout=10
        )
        console.print(f"HTTP {response.status_code} · {response.elapsed.total_seconds():.3f}s")
        response.raise_for_status()
    except httpx.HTTPError as error:
        _die(str(error))


@extension_app.command("list")
def extension_list(ctx: typer.Context) -> None:
    """List extension modules loaded by the runtime."""
    modules = _workspace(ctx).config.get("extensions", [])
    table = _table("Extensions", ["Module"])
    for module in modules:
        table.add_row(module)
    console.print(table)


@extension_app.command("add")
def extension_add(ctx: typer.Context, module: str) -> None:
    """Enable an installed Python extension module."""
    workspace = _workspace(ctx)
    config = workspace.config
    if module not in config["extensions"]:
        config["extensions"].append(module)
        workspace.save_config(config)
    try:
        GraphRuntime(workspace)
    except (ImportError, RuntimeError) as error:
        config["extensions"].remove(module)
        workspace.save_config(config)
        _die(str(error))
    console.print(f"[green]Enabled extension[/green] {module}")


@extension_app.command("remove")
def extension_remove(ctx: typer.Context, module: str) -> None:
    """Disable a runtime extension module."""
    workspace = _workspace(ctx)
    config = workspace.config
    if module not in config["extensions"]:
        _die(f"Extension is not enabled: {module}")
    config["extensions"].remove(module)
    workspace.save_config(config)
    console.print(f"[green]Disabled extension[/green] {module}")


@agent_app.command("new")
def agent_new(
    ctx: typer.Context,
    name: str,
    agent_id: Annotated[str | None, typer.Option("--id")] = None,
    description: Annotated[str, typer.Option("--description")] = "",
    agent_type: Annotated[str, typer.Option("--type", help="worker or orchestrator")] = "worker",
) -> None:
    """Create a minimal editable agent graph."""
    try:
        agent = _repo(ctx).create(
            name, agent_id=agent_id, description=description, agent_type=agent_type
        )
        console.print(f"[green]Created draft[/green] {agent['id']}")
        console.print("Edit it with: [cyan]activlayer agent node add|set|connect[/cyan]")
    except AgentError as error:
        _die(str(error))


@agent_app.command("list")
def agent_list(
    ctx: typer.Context,
    published: Annotated[bool | None, typer.Option("--published/--drafts")] = None,
) -> None:
    """List draft and published agents."""
    agents = _repo(ctx).list(published=published)
    table = _table("Agents", ["ID", "Name", "Type", "Version", "State", "Nodes"])
    for agent in agents:
        table.add_row(
            agent["id"],
            agent["name"],
            agent.get("agent_type", "worker"),
            str(agent.get("version", "1")),
            agent["_source"],
            str(len(agent["graph"]["nodes"])),
        )
    console.print(table)


@agent_app.command("show")
def agent_show(
    ctx: typer.Context,
    agent_id: str,
    published: Annotated[bool, typer.Option("--published")] = False,
    raw: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Show agent metadata or its complete JSON."""
    try:
        agent = _repo(ctx).load(agent_id, published=published)
    except AgentError as error:
        _die(str(error))
    if raw:
        console.print(JSON.from_data(agent))
        return
    body = Table.grid(padding=(0, 2))
    for label, value in (
        ("ID", agent["id"]),
        ("Name", agent["name"]),
        ("Type", agent.get("agent_type", "worker")),
        ("Version", str(agent.get("version", "1"))),
        ("Status", agent.get("status", "draft")),
        ("Domain", agent.get("domain", "general")),
        ("Nodes", str(len(agent["graph"]["nodes"]))),
        ("Edges", str(len(agent["graph"]["edges"]))),
    ):
        body.add_row(f"[bold cyan]{label}[/bold cyan]", value)
    console.print(Panel(body, title=agent["name"], border_style="violet"))


@agent_app.command("set")
def agent_set(ctx: typer.Context, agent_id: str, property_path: str, value: str) -> None:
    """Set any top-level agent property by dotted path."""
    repo = _repo(ctx)
    try:
        agent = repo.load(agent_id)
        if property_path in {"id", "graph"} or property_path.startswith("graph."):
            _die("Use agent node commands to modify graph structure")
        set_path(agent, property_path, parse_value(value))
        repo.save(agent)
        console.print(f"[green]Updated[/green] {agent_id}.{property_path}")
    except AgentError as error:
        _die(str(error))


@agent_app.command("validate")
def agent_validate(
    ctx: typer.Context,
    agent_id: str,
    published: Annotated[bool, typer.Option("--published")] = False,
) -> None:
    """Validate graph structure and agent properties."""
    try:
        agent = _repo(ctx).load(agent_id, published=published)
    except AgentError as error:
        _die(str(error))
    errors = validate_agent(agent)
    errors.extend(_repo(ctx).relationship_errors(agent, published_required=published))
    errors.extend(GraphRuntime(_workspace(ctx)).execution_errors(agent))
    if errors:
        for error in errors:
            error_console.print(f"[red]●[/red] {error}")
        raise typer.Exit(1)
    order = " → ".join(topological_order(agent))
    console.print(f"[green]Valid[/green] · {len(agent['graph']['nodes'])} nodes · {order}")


@agent_app.command("import")
def agent_import(
    ctx: typer.Context, file: Path, replace: Annotated[bool, typer.Option("--replace")] = False
) -> None:
    """Import Studio-compatible agent JSON as a draft."""
    try:
        agent = _repo(ctx).import_file(file, replace=replace)
        console.print(
            f"[green]Imported draft[/green] {agent['id']} · {len(agent['graph']['nodes'])} nodes"
        )
    except (AgentError, AgentValidationError) as error:
        _die(str(error))


@agent_app.command("export")
def agent_export(
    ctx: typer.Context,
    agent_id: str,
    output: Annotated[Path, typer.Option("--output", "-o")],
    published: Annotated[bool, typer.Option("--published")] = False,
) -> None:
    """Export an agent to portable Studio-compatible JSON."""
    try:
        agent = _repo(ctx).load(agent_id, published=published)
        output.write_text(json.dumps(agent, indent=2) + "\n", encoding="utf-8")
        console.print(f"[green]Exported[/green] {output}")
    except (AgentError, OSError) as error:
        _die(str(error))


@agent_app.command("provision")
def agent_provision(
    ctx: typer.Context,
    file: Path,
    replace: Annotated[bool, typer.Option("--replace")] = False,
    publish: Annotated[bool, typer.Option("--publish")] = False,
) -> None:
    """Validate and install an agent JSON package, optionally publishing it."""
    repo = _repo(ctx)
    try:
        agent = repo.import_file(file, replace=replace)
        if publish:
            _require_executable(_workspace(ctx), agent)
            agent = repo.publish(agent["id"])
        state = agent.get("status", "draft")
        version = agent.get("version", "1")
        console.print(f"[green]Provisioned[/green] {agent['id']} · {state} · version {version}")
    except (AgentError, AgentValidationError) as error:
        _die(str(error))


@agent_app.command("publish")
def agent_publish(ctx: typer.Context, agent_id: str) -> None:
    """Publish an immutable execution snapshot of a draft."""
    try:
        repo = _repo(ctx)
        agent = repo.load(agent_id)
        _require_executable(_workspace(ctx), agent)
        agent = repo.publish(agent_id)
        console.print(f"[green]Published[/green] {agent_id} · version {agent.get('version')}")
    except (AgentError, AgentValidationError) as error:
        _die(str(error))


@agent_app.command("graph")
def agent_graph(
    ctx: typer.Context,
    agent_id: str,
    published: Annotated[bool, typer.Option("--published")] = False,
) -> None:
    """Render the agent execution order and connections."""
    try:
        agent = _repo(ctx).load(agent_id, published=published)
        order = topological_order(agent)
    except (AgentError, AgentValidationError) as error:
        _die(str(error))
    nodes = {node["id"]: node for node in agent["graph"]["nodes"]}
    tree = Tree(f"[bold violet]{agent['name']}[/bold violet]  [dim]{agent['id']}[/dim]")
    for index, node_id in enumerate(order, 1):
        node = nodes[node_id]
        label = node.get("data", {}).get("label", "")
        branch = tree.add(
            f"[cyan]{index:02}[/cyan] [bold]{node_id}[/bold] · {node['type']} · {label}"
        )
        targets = [
            edge["target"] for edge in agent["graph"]["edges"] if edge.get("source") == node_id
        ]
        if targets:
            branch.add(f"[dim]connects to: {', '.join(targets)}[/dim]")
    console.print(tree)


@node_app.command("list")
def node_list(ctx: typer.Context, agent_id: str) -> None:
    """List every node in a draft graph."""
    try:
        agent = _repo(ctx).load(agent_id)
    except AgentError as error:
        _die(str(error))
    table = _table(f"Nodes · {agent_id}", ["Order", "ID", "Type", "Label", "Disabled"])
    order = topological_order(agent)
    for node in sorted(agent["graph"]["nodes"], key=lambda item: order.index(item["id"])):
        table.add_row(
            str(order.index(node["id"]) + 1),
            node["id"],
            node["type"],
            node.get("data", {}).get("label", ""),
            str(bool(node.get("data", {}).get("disabled"))),
        )
    console.print(table)


@node_app.command("types")
def node_types(category: Annotated[str | None, typer.Option("--category")] = None) -> None:
    """Browse built-in node types and their purpose."""
    table = _table("Built-in node types", ["Type", "Category", "Purpose"])
    for name, definition in NODE_CATALOG.items():
        if category and definition["category"] != category:
            continue
        table.add_row(name, definition["category"], definition["description"])
    console.print(table)


@node_app.command("explain")
def node_explain(node_type: str) -> None:
    """Show instructions and example configuration for a node type."""
    definition = node_help(node_type)
    if definition is None:
        _die(f"No built-in documentation for node type: {node_type}")
    console.print(
        Panel(
            f"[bold]{definition['description']}[/bold]\n\n"
            f"Category: [cyan]{definition['category']}[/cyan]\n\n"
            "Example config:\n"
            f"{json.dumps(definition['config'], indent=2)}",
            title=node_type,
            border_style="violet",
        )
    )


@node_app.command("show")
def node_show(ctx: typer.Context, agent_id: str, node_id: str) -> None:
    """Show a node's complete editable JSON."""
    repo = _repo(ctx)
    try:
        console.print(JSON.from_data(repo.get_node(repo.load(agent_id), node_id)))
    except AgentError as error:
        _die(str(error))


@node_app.command("add")
def node_add(
    ctx: typer.Context,
    agent_id: str,
    node_id: str,
    node_type: Annotated[str, typer.Option("--type", "-t")],
    label: Annotated[str | None, typer.Option("--label")] = None,
    config: Annotated[str, typer.Option("--config", help="JSON object.")] = "{}",
) -> None:
    """Add a node to a draft graph."""
    try:
        parsed = json.loads(config)
        if not isinstance(parsed, dict):
            _die("--config must be a JSON object")
        _repo(ctx).add_node(agent_id, node_id, node_type, label=label, config=parsed)
        console.print(f"[green]Added node[/green] {node_id} · {node_type}")
    except (AgentError, json.JSONDecodeError) as error:
        _die(str(error))


@node_app.command("set")
def node_set(
    ctx: typer.Context, agent_id: str, node_id: str, property_path: str, value: str
) -> None:
    """Set any node property, including data.config fields, by dotted path."""
    try:
        _repo(ctx).set_node(agent_id, node_id, property_path, parse_value(value))
        console.print(f"[green]Updated[/green] {node_id}.{property_path}")
    except AgentError as error:
        _die(str(error))


@node_app.command("remove")
def node_remove(
    ctx: typer.Context,
    agent_id: str,
    node_id: str,
    yes: Annotated[bool, typer.Option("--yes", "-y")] = False,
) -> None:
    """Remove a node and all of its edges."""
    if not yes and not Confirm.ask(f"Remove node {node_id} and its edges?"):
        raise typer.Abort()
    try:
        _repo(ctx).remove_node(agent_id, node_id)
        console.print(f"[green]Removed node[/green] {node_id}")
    except AgentError as error:
        _die(str(error))


@node_app.command("connect")
def node_connect(
    ctx: typer.Context,
    agent_id: str,
    source: str,
    target: str,
    edge_id: Annotated[str | None, typer.Option("--id")] = None,
) -> None:
    """Connect two nodes with a directed edge."""
    try:
        _repo(ctx).connect(agent_id, source, target, edge_id=edge_id)
        console.print(f"[green]Connected[/green] {source} → {target}")
    except AgentError as error:
        _die(str(error))


@node_app.command("disconnect")
def node_disconnect(ctx: typer.Context, agent_id: str, edge_id: str) -> None:
    """Remove a graph edge by id."""
    try:
        _repo(ctx).disconnect(agent_id, edge_id)
        console.print(f"[green]Disconnected[/green] {edge_id}")
    except AgentError as error:
        _die(str(error))


@agent_app.command("workers")
def agent_workers(
    ctx: typer.Context,
    agent_id: str,
    workers: Annotated[list[str] | None, typer.Argument(help="Worker IDs to manage.")] = None,
) -> None:
    """Show or replace an orchestrator's managed worker list."""
    repo = _repo(ctx)
    try:
        agent = repo.load(agent_id)
        if agent.get("agent_type", "worker") != "orchestrator":
            _die(f"{agent_id} is not an orchestrator")
        if workers is not None:
            agent["managed_workers"] = list(workers)
            errors = repo.relationship_errors(agent)
            if errors:
                raise AgentValidationError(errors)
            repo.save(agent)
            console.print(f"[green]Updated[/green] {agent_id} · {len(workers)} worker(s)")
        else:
            for worker in agent.get("managed_workers", []):
                console.print(worker)
    except (AgentError, AgentValidationError) as error:
        _die(str(error))


@app.command("chat")
def design_chat(
    ctx: typer.Context,
    message: Annotated[str | None, typer.Argument(help="Plain-language design request.")] = None,
    provider: Annotated[str | None, typer.Option("--provider")] = None,
    apply: Annotated[
        bool, typer.Option("--apply", help="Apply after showing the validated plan.")
    ] = False,
) -> None:
    """Plan safe agent-design changes from plain language and optionally apply them."""
    if message is None:
        message = typer.prompt("What would you like to change in the agent design?")
    assistant = DesignAssistant(_workspace(ctx))
    try:
        plan = assistant.plan(message, provider=provider)
        console.print(Panel(plan.summary, title="Validated design plan", border_style="violet"))
        table = _table("Proposed operations", ["#", "Operation", "Agent", "Details"])
        for index, operation in enumerate(plan.operations, start=1):
            details = {
                key: value for key, value in operation.items() if key not in {"op", "agent_id"}
            }
            table.add_row(
                str(index),
                str(operation["op"]),
                str(operation.get("agent_id") or operation.get("id", "")),
                json.dumps(details, ensure_ascii=False),
            )
        console.print(table)
        should_apply = apply or Confirm.ask("Apply this validated plan?", default=False)
        if not should_apply:
            console.print("[yellow]No changes applied[/yellow]")
            return
        backup = assistant.apply(plan)
        console.print(f"[green]Applied[/green] · backup: {backup}")
    except (DesignAssistantError, LLMError, WorkspaceError) as error:
        _die(str(error))


@knowledge_app.command("collection-create")
def knowledge_collection_create(
    ctx: typer.Context,
    name: str,
    description: Annotated[str, typer.Option("--description")] = "",
) -> None:
    """Create a shared knowledge collection."""
    collection_id = SharedKnowledge(_workspace(ctx)).create_collection(name, description)
    console.print(f"[green]Created collection[/green] {collection_id}")


@knowledge_app.command("collection-list")
def knowledge_collection_list(ctx: typer.Context) -> None:
    """List shared knowledge collections."""
    table = _table("Knowledge collections", ["ID", "Name", "Documents", "Description"])
    for item in SharedKnowledge(_workspace(ctx)).collections():
        table.add_row(item["id"], item["name"], str(item["documents"]), item["description"])
    console.print(table)


@knowledge_app.command("add")
def knowledge_add(
    ctx: typer.Context,
    collection: str,
    title: Annotated[str, typer.Option("--title")],
    text: Annotated[str | None, typer.Option("--text")] = None,
    file: Annotated[Path | None, typer.Option("--file")] = None,
) -> None:
    """Add text or a UTF-8 file to a shared knowledge collection."""
    if (text is None) == (file is None):
        _die("Provide exactly one of --text or --file")
    try:
        content = file.read_text(encoding="utf-8") if file else str(text)
        document_id = SharedKnowledge(_workspace(ctx)).add(collection, title, content)
        console.print(f"[green]Added document[/green] {document_id}")
    except (OSError, KeyError) as error:
        _die(str(error))


@knowledge_app.command("search")
def knowledge_search(
    ctx: typer.Context,
    query: str,
    collection: Annotated[list[str] | None, typer.Option("--collection", "-c")] = None,
    limit: Annotated[int, typer.Option("--limit")] = 5,
) -> None:
    """Search the shared knowledge base."""
    console.print_json(
        data=SharedKnowledge(_workspace(ctx)).search(query, collections=collection, limit=limit)
    )


@memory_app.command("list")
def memory_list(
    ctx: typer.Context,
    worker_id: str,
    scope: Annotated[str, typer.Option("--scope")] = "global",
    limit: Annotated[int, typer.Option("--limit")] = 10,
) -> None:
    """Recall entries from one worker's isolated memory database."""
    agent = _repo(ctx).load(worker_id)
    if agent.get("agent_type", "worker") != "worker":
        _die("Memory belongs to workers, not orchestrators")
    console.print_json(data=AgentMemory(_workspace(ctx), worker_id).recall(scope, limit=limit))


@memory_app.command("search")
def memory_search(
    ctx: typer.Context,
    worker_id: str,
    query: str,
    scope: Annotated[str | None, typer.Option("--scope")] = None,
    limit: Annotated[int, typer.Option("--limit")] = 10,
) -> None:
    """Search one worker's isolated memory database."""
    agent = _repo(ctx).load(worker_id)
    if agent.get("agent_type", "worker") != "worker":
        _die("Memory belongs to workers, not orchestrators")
    console.print_json(
        data=AgentMemory(_workspace(ctx), worker_id).search(query, scope=scope, limit=limit)
    )


@run_app.command("start")
def run_start(
    ctx: typer.Context,
    agent_id: str,
    input_value: Annotated[str, typer.Option("--input", "-i", help="JSON object or file path.")],
    permission: Annotated[list[str] | None, typer.Option("--permission", "-p")] = None,
    actor: Annotated[str | None, typer.Option("--actor")] = None,
    draft: Annotated[
        bool, typer.Option("--draft", help="Run the draft instead of the published version.")
    ] = False,
) -> None:
    """Start and advance a durable Agent Worker run."""
    workspace = _workspace(ctx)
    try:
        agent = AgentRepository(workspace).load(agent_id, published=not draft)
        run = GraphRuntime(workspace).start(
            agent, _json_input(input_value), permissions=set(permission or []), actor=actor
        )
    except (AgentError, AgentValidationError, ActivLayerError) as error:
        _die(str(error))
    color = (
        "yellow"
        if run.status == RunStatus.WAITING_APPROVAL
        else "green"
        if run.status == RunStatus.SUCCEEDED
        else "red"
    )
    summary = (
        f"Run       [bold]{run.id}[/bold]\n"
        f"Agent     {run.worker}@{run.worker_version}\n"
        f"Status    [{color}]{run.status.value}[/{color}]\n"
        f"Progress  {run.current_step}/{len(run.state['order'])}"
    )
    console.print(Panel.fit(summary, title="Agent Worker run", border_style=color))


@run_app.command("list")
def run_list(
    ctx: typer.Context,
    agent_id: Annotated[str | None, typer.Option("--agent")] = None,
    limit: Annotated[int, typer.Option("--limit")] = 25,
) -> None:
    """List recent durable runs."""
    runs = GraphRuntime(_workspace(ctx)).store.list_runs(limit=limit, worker=agent_id)
    table = _table("Runs", ["ID", "Agent", "Version", "Status", "Step", "Error"])
    for run in runs:
        table.add_row(
            run.id,
            run.worker,
            run.worker_version,
            run.status.value,
            str(run.current_step),
            run.error or "",
        )
    console.print(table)


@run_app.command("show")
def run_show(
    ctx: typer.Context, run_id: str, events: Annotated[bool, typer.Option("--events")] = False
) -> None:
    """Inspect run state, trace, and optional event history."""
    runtime = GraphRuntime(_workspace(ctx))
    try:
        run = runtime.store.get_run(run_id)
    except KeyError as error:
        _die(str(error))
    console.print(
        JSON.from_data(
            {
                "id": run.id,
                "agent": run.worker,
                "version": run.worker_version,
                "status": run.status.value,
                "current_step": run.current_step,
                "error": run.error,
                "input": run.state.get("input"),
                "outputs": run.state.get("outputs"),
                "trace": run.state.get("trace"),
            }
        )
    )
    if events:
        console.print(JSON.from_data(runtime.store.events(run.id)))


@run_app.command("resume")
def run_resume(ctx: typer.Context, run_id: str) -> None:
    """Resume a pending or failed run from its durable cursor."""
    try:
        run = GraphRuntime(_workspace(ctx)).execute(run_id)
        console.print(f"Run [bold]{run.id}[/bold] · {run.status.value} · step {run.current_step}")
    except (KeyError, ActivLayerError) as error:
        _die(str(error))


@run_app.command("approve")
def run_approve(
    ctx: typer.Context,
    run_id: str,
    actor: Annotated[str, typer.Option("--actor", prompt=True)],
    reason: Annotated[str, typer.Option("--reason")] = "Approved",
) -> None:
    """Approve the current checkpoint and continue the run."""
    try:
        run = GraphRuntime(_workspace(ctx)).approve(run_id, actor=actor, reason=reason)
        console.print(f"[green]Approved[/green] · run {run.id} is {run.status.value}")
    except (KeyError, ActivLayerError) as error:
        _die(str(error))


def entrypoint() -> None:
    app()


if __name__ == "__main__":
    entrypoint()
