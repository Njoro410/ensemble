"""Command-line control plane for Ensemble."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from .config import (
    ConfigError,
    Provider,
    RoleAssignment,
    config_dir,
    config_path,
    default_config,
    load_config,
    save_config,
)
from .opencode_config import (
    ROLE_AGENTS,
    build_opencode_config,
    opencode_config_path,
    write_opencode_config,
)
from .secrets import (
    SecretError,
    import_from_env,
    keyring_available,
    keyring_description,
    resolve_secret,
    set_secret,
)


def cmd_init(args: argparse.Namespace) -> int:
    path = config_path()
    if path.exists() and not args.force:
        print(f"Config already exists: {path}")
        print("Use 'ensemble init --force' to overwrite.")
        return 0
    config = default_config()
    save_config(config)
    orchestrator = config.roles["orchestrator"]
    reviewer = config.roles["reviewer"]
    test_runner = config.roles["test_runner"]
    print(f"Wrote {path}")
    print(f"  orchestrator: {orchestrator.provider}/{orchestrator.model}")
    print(f"  reviewer:     {reviewer.provider}/{reviewer.model}")
    print(f"  test_runner:  {test_runner.provider}/{test_runner.model}")
    print()
    print("Next steps:")
    print("  ensemble key import-env deepseek    # if $DEEPSEEK_API_KEY is set")
    print("  ensemble key set openrouter")
    print("  ensemble opencode apply")
    return 0


def cmd_config_show(args: argparse.Namespace) -> int:
    print(json.dumps(load_config().to_dict(), indent=2))
    return 0


def cmd_config_path(args: argparse.Namespace) -> int:
    print(config_path())
    return 0


def cmd_providers_list(args: argparse.Namespace) -> int:
    config = load_config()
    print(f"{'ID':<16} {'PROTOCOL':<10} {'KIND':<8} {'MODELS':>6}  ENV_VAR")
    for provider_id in sorted(config.providers):
        provider = config.providers[provider_id]
        print(
            f"{provider_id:<16} {provider.protocol:<10} {provider.kind:<8} "
            f"{len(provider.models):>6}  {provider.env_var}"
        )
    return 0


def cmd_providers_add(args: argparse.Namespace) -> int:
    config = load_config()
    if args.id in config.providers and not args.force:
        raise ConfigError(
            f"Provider {args.id!r} already exists (use --force to replace)"
        )
    models = [item.strip() for item in args.models.split(",") if item.strip()]
    provider = Provider(
        id=args.id,
        label=args.label or args.id,
        protocol=args.protocol,
        env_var=args.env_var,
        base_url=args.base_url,
        kind=args.kind,
        package=args.package,
        auth_style=args.auth_style,
        models=models,
    )
    config.providers[args.id] = provider
    save_config(config)
    print(f"Added provider {args.id} ({provider.protocol}, {provider.kind}).")
    return 0


def cmd_roles_show(args: argparse.Namespace) -> int:
    config = load_config()
    for role, assignment in config.roles.items():
        small = f" (small: {assignment.small_model})" if assignment.small_model else ""
        print(f"{role:<12} -> {assignment.provider}/{assignment.model}{small}")
    return 0


def cmd_roles_set(args: argparse.Namespace) -> int:
    config = load_config()
    if args.role not in config.roles:
        raise ConfigError(
            f"Unknown role {args.role!r}. Roles: "
            + ", ".join(sorted(config.roles))
        )
    if args.provider not in config.providers:
        raise ConfigError(f"Unknown provider {args.provider!r}")
    if (
        args.role == "orchestrator"
        and config.providers[args.provider].protocol != "anthropic"
    ):
        raise ConfigError(
            "The orchestrator role needs an Anthropic-compatible provider"
        )
    config.roles[args.role] = RoleAssignment(
        provider=args.provider,
        model=args.model,
        small_model=args.small_model,
    )
    save_config(config)
    print(f"Set {args.role} -> {args.provider}/{args.model}")
    return 0


def cmd_key_set(args: argparse.Namespace) -> int:
    config = load_config()
    provider = config.providers.get(args.provider)
    if provider is None:
        raise ConfigError(f"Unknown provider {args.provider!r}")
    if args.stdin:
        secret = sys.stdin.readline().rstrip("\n")
    else:
        secret = getpass.getpass(f"API key for {provider.id} (hidden): ")
    set_secret(provider, secret)
    print(f"Stored the key for {provider.id} in the OS keyring.")
    return 0


def cmd_key_import_env(args: argparse.Namespace) -> int:
    config = load_config()
    provider = config.providers.get(args.provider)
    if provider is None:
        raise ConfigError(f"Unknown provider {args.provider!r}")
    variable = import_from_env(provider)
    print(f"Imported ${variable} into the OS keyring for {provider.id}.")
    return 0


def cmd_key_status(args: argparse.Namespace) -> int:
    config = load_config()
    for provider_id in sorted(config.providers):
        provider = config.providers[provider_id]
        secret, source = resolve_secret(provider)
        print(f"{provider_id:<16} {source if secret else 'missing'}")
    return 0


def cmd_opencode_apply(args: argparse.Namespace) -> int:
    config = load_config()
    target = write_opencode_config(config)
    custom = sorted(
        provider.id
        for provider in config.providers.values()
        if provider.kind == "custom"
    )
    agents = ", ".join(agent for agent, _ in ROLE_AGENTS.values())
    print(f"Wrote {target}")
    print(f"  custom providers: {', '.join(custom) if custom else '(none)'}")
    print(f"  agents: {agents}")
    if args.print_config:
        print(json.dumps(build_opencode_config(config), indent=2))
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    problems: list[str] = []
    warnings: list[str] = []

    print("Ensemble doctor")
    print(f"  config path: {config_path()}")
    try:
        config = load_config()
        print("  [ok] config valid")
    except ConfigError as exc:
        print(f"  [fail] config: {exc}")
        return 1

    opencode_bin = os.environ.get("ENSEMBLE_OPENCODE_BIN") or shutil.which(
        "opencode"
    )
    if opencode_bin:
        try:
            result = subprocess.run(
                [opencode_bin, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            version = (result.stdout or result.stderr).splitlines()
            print(
                f"  [ok] opencode: {version[0].strip() if version else 'unknown'}"
                f" ({opencode_bin})"
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            print(f"  [warn] opencode version check failed: {exc}")
            warnings.append("opencode-version")
    else:
        print("  [fail] opencode not found on PATH")
        problems.append("opencode")

    generated = opencode_config_path()
    if generated.exists():
        try:
            data = json.loads(generated.read_text(encoding="utf-8"))
            missing = [
                agent
                for agent, _ in ROLE_AGENTS.values()
                if agent not in (data.get("agents") or {})
            ]
            if missing:
                print(f"  [fail] generated config missing agents: {missing}")
                problems.append("agents")
            else:
                print(f"  [ok] generated opencode config: {generated}")
        except (OSError, json.JSONDecodeError) as exc:
            print(f"  [fail] generated config unreadable: {exc}")
            problems.append("opencode-config")
    else:
        print("  [warn] generated config missing (run 'ensemble opencode apply')")
        warnings.append("opencode-config")

    print(
        f"  keyring: {keyring_description()} "
        f"({'available' if keyring_available() else 'unavailable'})"
    )

    for provider_id in sorted(config.providers):
        provider = config.providers[provider_id]
        secret, source = resolve_secret(provider)
        if secret:
            print(f"  [ok] key {provider_id}: {source}")
        else:
            print(
                f"  [warn] key {provider_id}: missing "
                f"(ensemble key set {provider_id} or export ${provider.env_var})"
            )
            warnings.append(f"key:{provider_id}")

    orchestrator = config.roles["orchestrator"]
    reviewer = config.roles["reviewer"]
    test_runner = config.roles["test_runner"]
    print(
        "  roles: "
        f"orchestrator={orchestrator.provider}/{orchestrator.model}, "
        f"reviewer={reviewer.provider}/{reviewer.model}, "
        f"test_runner={test_runner.provider}/{test_runner.model}"
    )
    if warnings:
        print(f"  warnings: {len(warnings)}")
    return 1 if problems else 0


def cmd_launch(args: argparse.Namespace) -> int:
    config = load_config()
    assignment = config.roles["orchestrator"]
    provider = config.providers[assignment.provider]

    secret, source = resolve_secret(provider)
    if not secret:
        ambient = os.environ.get("ANTHROPIC_AUTH_TOKEN") or os.environ.get(
            "ANTHROPIC_API_KEY"
        )
        if ambient:
            secret, source = ambient, "ambient"
    if not secret:
        raise ConfigError(
            f"No API key for orchestrator provider {provider.id!r}. Run "
            f"'ensemble key set {provider.id}' or export ${provider.env_var}."
        )

    repo = Path(
        args.repo or config.prefs.default_repo or os.getcwd()
    ).expanduser().resolve()
    if not repo.is_dir():
        raise ConfigError(f"--repo is not a directory: {repo}")

    env = os.environ.copy()
    if provider.base_url:
        env["ANTHROPIC_BASE_URL"] = provider.base_url
    if provider.auth_style == "x-api-key":
        env["ANTHROPIC_API_KEY"] = secret
        env.pop("ANTHROPIC_AUTH_TOKEN", None)
        auth_var = "ANTHROPIC_API_KEY"
    else:
        env["ANTHROPIC_AUTH_TOKEN"] = secret
        env.pop("ANTHROPIC_API_KEY", None)
        auth_var = "ANTHROPIC_AUTH_TOKEN"

    model = assignment.model
    env["ANTHROPIC_MODEL"] = model
    env["ANTHROPIC_DEFAULT_OPUS_MODEL"] = model
    env["ANTHROPIC_DEFAULT_SONNET_MODEL"] = model
    env["ANTHROPIC_DEFAULT_HAIKU_MODEL"] = assignment.small_model or model
    env["ENSEMBLE_CONFIG_DIR"] = str(config_dir())

    claude_args = list(args.claude_args)
    if claude_args and claude_args[0] == "--":
        claude_args = claude_args[1:]

    if args.dry_run:
        print(f"repo: {repo}")
        print(f"key source: {source}")
        for name in (
            "ANTHROPIC_BASE_URL",
            "ANTHROPIC_MODEL",
            "ANTHROPIC_DEFAULT_OPUS_MODEL",
            "ANTHROPIC_DEFAULT_SONNET_MODEL",
            "ANTHROPIC_DEFAULT_HAIKU_MODEL",
        ):
            if name in env:
                print(f"{name}={env[name]}")
        print(f"{auth_var}=<redacted>")
        print("claude " + " ".join(shlex.quote(arg) for arg in claude_args))
        return 0

    claude = shutil.which("claude")
    if not claude:
        raise ConfigError("claude not found on PATH")
    os.chdir(repo)
    os.execvpe(claude, [claude, *claude_args], env)
    return 0  # unreachable


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ensemble",
        description="Control plane for multi-provider agent ensembles.",
    )
    parser.add_argument(
        "--version", action="version", version="ensemble 0.1.0"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="Create the default config")
    init.add_argument("--force", action="store_true")
    init.set_defaults(func=cmd_init)

    config_parser = sub.add_parser("config", help="Inspect configuration")
    config_sub = config_parser.add_subparsers(
        dest="config_command", required=True
    )
    config_show = config_sub.add_parser("show")
    config_show.set_defaults(func=cmd_config_show)
    config_path_parser = config_sub.add_parser("path")
    config_path_parser.set_defaults(func=cmd_config_path)

    providers = sub.add_parser("providers", help="Manage providers")
    providers_sub = providers.add_subparsers(
        dest="providers_command", required=True
    )
    providers_list = providers_sub.add_parser("list")
    providers_list.set_defaults(func=cmd_providers_list)
    providers_add = providers_sub.add_parser("add")
    providers_add.add_argument("--id", required=True)
    providers_add.add_argument("--label", default=None)
    providers_add.add_argument(
        "--protocol", required=True, choices=["anthropic", "openai"]
    )
    providers_add.add_argument("--env-var", required=True)
    providers_add.add_argument("--base-url", default="")
    providers_add.add_argument(
        "--kind", default="custom", choices=["custom", "builtin"]
    )
    providers_add.add_argument("--package", default="")
    providers_add.add_argument(
        "--auth-style", default="bearer", choices=["bearer", "x-api-key"]
    )
    providers_add.add_argument(
        "--models", default="", help="comma-separated model ids"
    )
    providers_add.add_argument("--force", action="store_true")
    providers_add.set_defaults(func=cmd_providers_add)

    roles = sub.add_parser("roles", help="Show or assign roles")
    roles_sub = roles.add_subparsers(dest="roles_command", required=True)
    roles_show = roles_sub.add_parser("show")
    roles_show.set_defaults(func=cmd_roles_show)
    roles_set = roles_sub.add_parser("set")
    roles_set.add_argument("role")
    roles_set.add_argument("provider")
    roles_set.add_argument("model")
    roles_set.add_argument("--small-model", default=None)
    roles_set.set_defaults(func=cmd_roles_set)

    key = sub.add_parser("key", help="Manage API keys in the OS keyring")
    key_sub = key.add_subparsers(dest="key_command", required=True)
    key_set = key_sub.add_parser("set")
    key_set.add_argument("provider")
    key_set.add_argument("--stdin", action="store_true")
    key_set.set_defaults(func=cmd_key_set)
    key_import = key_sub.add_parser("import-env")
    key_import.add_argument("provider")
    key_import.set_defaults(func=cmd_key_import_env)
    key_status = key_sub.add_parser("status")
    key_status.set_defaults(func=cmd_key_status)

    opencode = sub.add_parser("opencode", help="Manage generated opencode config")
    opencode_sub = opencode.add_subparsers(
        dest="opencode_command", required=True
    )
    opencode_apply = opencode_sub.add_parser("apply")
    opencode_apply.add_argument("--print", dest="print_config", action="store_true")
    opencode_apply.set_defaults(func=cmd_opencode_apply)

    doctor = sub.add_parser("doctor", help="Check configuration and keys")
    doctor.set_defaults(func=cmd_doctor)

    launch = sub.add_parser(
        "launch", help="Launch Claude Code with the orchestrator provider"
    )
    launch.add_argument("--repo", default=None)
    launch.add_argument("--dry-run", action="store_true")
    launch.add_argument("claude_args", nargs=argparse.REMAINDER)
    launch.set_defaults(func=cmd_launch)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (ConfigError, SecretError) as exc:
        print(f"ensemble: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
