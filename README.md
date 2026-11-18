# Ensemble

**Claude Code with a team of specialist models.**

Ensemble is a Linux control plane and workflow layer for running Claude Code as
the orchestrator with 13 specialized, read-only agent roles through
[opencode](https://opencode.ai). Assign a different provider and model to
planning, coding, review, testing, security, database work, docs, and release —
while keeping one accountable writer.

> Ensemble is an independent project. It is not affiliated with Anthropic,
> OpenCode, OpenRouter, DeepSeek, or any provider named in this repository.

## Why Ensemble

A single model can be excellent at some parts of a task and weak at others. A
second model reviewing the first is useful; a whole team of specialists is
better, as long as the work stays coherent.

Ensemble keeps that coherence with a strict rule:

**Many advisors, one writer.** Claude Code is the only agent that edits files
or executes commands. Every specialist runs read-only through opencode, returns
structured findings or a proposed patch, and Claude Code decides what to apply.

That gives you:

- Model-per-role assignments without handing repository access to every model.
- Independent review, security, database, and testing perspectives.
- A complete artifact trail for every peer turn.
- No API keys in config files, prompts, logs, or command lines.

## Features

- **13 roles** — orchestrator, planner, coder, reviewer, tester, explorer,
  architect, debugger, security reviewer, database/migration, refactorer, docs,
  and release.
- **Adaptive goal pipeline** — `/ensemble goal` selects the relevant roles,
  plans, gates on approval, implements, reviews in parallel, verifies with real
  test output, and finishes with docs/release.
- **Provider presets and per-key model discovery** — OpenRouter, OpenRouter
  (Anthropic), OpenCode Go (OpenAI and Anthropic), and DeepSeek.
- **OS keyring storage** by default, with an explicit protected-file fallback
  and environment-variable support.
- **Read-only peer enforcement** — `edit` and `shell` are denied in opencode;
  web tools are denied; a git tree guard aborts a run if the working tree
  changes during a peer call.
- **GTK3 control panel** — manage providers, keys, models, roles, and launches
  without editing JSON.
- **Claude Code skill** — `/ensemble goal`, `brainstorm`, `review`, `verify`,
  `role`, and `status`.
- **Reproducible artifacts** — prompts, raw JSONL, replies, usage, cost, and
  metadata under `.ensemble/runs/`.
- **Desktop launcher, backup rotation, and 57 tests.**

## Architecture

```
┌──────────────────────────────────────────┐
│ Claude Code — orchestrator               │
│ writes, executes, applies patches, tests │
└───────────────┬──────────────────────────┘
                │ ensemble-peer ask --role …
                ▼
┌──────────────────────────────────────────┐
│ opencode + role-specific agent           │
│ edit/shell denied · read-only advisor    │
│ provider/model from the role assignment  │
└───────────────┬──────────────────────────┘
                │ artifacts
                ▼
      <repo>/.ensemble/runs/<id>/
        brief · prompt · raw JSONL
        reply · meta (cost/tokens)
```

Claude Code holds the goal, permissions, and session state. Peers receive only
the brief and files the orchestrator chooses.

## Requirements

- Linux with GTK3/PyGObject for the GUI (the CLI works headless).
- Python 3.10+.
- [Claude Code](https://claude.com/claude-code) CLI.
- [opencode](https://opencode.ai) 2.x with a model catalog.
- At least one provider API key (OpenRouter, OpenCode Go, or DeepSeek).

## Install

```bash
git clone https://github.com/Njoro410/ensemble.git
cd ensemble

# The GUI uses system PyGObject/GTK3, so include system site-packages.
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -e .
.venv/bin/ensemble init
```

`ensemble init` creates `~/.config/ensemble/config.json` and imports your
current `ANTHROPIC_BASE_URL` / `ANTHROPIC_MODEL` if present. It never copies
keys.

### Debian / Ubuntu package

Tagged releases attach an `ensemble_<version>_all.deb` package:

```bash
sudo apt install ./ensemble_0.1.0_all.deb
ensemble init
```

The package installs `/usr/bin/ensemble`, `/usr/bin/ensemble-peer`, the GTK
launcher, and an application icon. Its Debian dependencies pull in Python 3,
PyGObject/GTK3, `python3-keyring`, and `libsecret`. Claude Code and opencode are
external prerequisites and are not packaged.

To build the `.deb` locally:

```bash
python3 -m venv .build-venv
.build-venv/bin/pip install --upgrade pip
PYTHON=.build-venv/bin/python ./scripts/build-deb.sh
```

## Quick start

```bash
# 1. Add provider presets (only the ones you use).
.venv/bin/ensemble providers add --preset openrouter
.venv/bin/ensemble providers add --preset openrouter-anthropic
.venv/bin/ensemble providers add --preset opencode-go
.venv/bin/ensemble providers add --preset opencode-anthropic
.venv/bin/ensemble providers add --preset deepseek

# 2. Store keys in the OS keyring (hidden prompt; never argv).
.venv/bin/ensemble key set openrouter
.venv/bin/ensemble key set opencode-go
.venv/bin/ensemble key set deepseek

# 3. Discover the models each key can see.
.venv/bin/ensemble providers discover --all

# 4. Assign the 13 recommended roles.
.venv/bin/ensemble roles seed --force

# 5. Install the Claude Code skill and desktop launcher.
.venv/bin/ensemble skill install
.venv/bin/ensemble desktop install

# 6. Open the control panel, or launch an orchestrator terminal.
.venv/bin/ensemble gui
.venv/bin/ensemble launch --repo /path/to/your/repo
```

Reload or restart Claude Code after `skill install`, then invoke `/ensemble`.

### Installing only some providers

`roles seed` assigns a role only when its recommended provider/model exists in
the catalog. If you skip a provider, run `ensemble roles catalog` to see what
is unassigned and set those roles in the GUI or with:

```bash
ensemble roles set <role> <provider> <model>
```

## Providers

Providers are typed by wire protocol:

- **`anthropic`** — can drive Claude Code as the orchestrator.
- **`openai`** — used by opencode peers.

Presets:

| Preset | Protocol | Base URL | Model discovery |
|---|---|---|---|
| `openrouter` | openai | `https://openrouter.ai/api/v1` | `GET /models`; key checked at `/auth/key` |
| `openrouter-anthropic` | anthropic | `https://openrouter.ai/api` | shares the OpenRouter key |
| `opencode-go` | openai | `https://opencode.ai/inference/go/openai/v1` | `GET /models` |
| `opencode-anthropic` | anthropic | `https://opencode.ai/inference/go/anthropic` | shares the Go key |
| `deepseek` | anthropic | `https://api.deepseek.com/anthropic` | `GET https://api.deepseek.com/models` |

Discovery is per key: only model IDs visible to the supplied credential are
stored. Refresh anytime with:

```bash
ensemble providers discover --all
```

Notes:

- **Orchestrator** roles require an Anthropic-compatible provider because
  Claude Code speaks the Anthropic Messages API. `openrouter-anthropic` and
  `opencode-anthropic` are built for this; `deepseek` remains a fallback.
- **OpenCode Go** requires an `x-opencode-session` header. The OpenAI-facing
  preset sends it through the generated opencode config; the Anthropic-facing
  preset sends it through Claude Code's `ANTHROPIC_CUSTOM_HEADERS`.
- OpenCode Go model IDs carry a local `-go` suffix and map back to the upstream
  ID through `modelID`. This avoids the built-in provider's native routing,
  which returns 404 for some model families.
- OpenCode Go lists 32 models in the reference setup; OpenRouter lists 443;
  DeepSeek lists 2. Catalogs and quotas change over time.

## Roles

`ensemble roles seed --force` installs this reference catalog. All
non-orchestrator roles are read-only; Claude Code applies changes.

| Role | Reference model | Provider |
| --- | --- | --- |
| Orchestrator | `anthropic/claude-haiku-5.5` | `openrouter-anthropic` |
| Planner | `gemini-4-argon-go` | `opencode-go` |
| Coder / Implementer | `kimi-k2.7-code-go` | `opencode-go` |
| Reviewer | `grok-4.7-go` | `opencode-go` |
| Tester / Verifier | `mimo-v2.6-flash-go` | `opencode-go` |
| Explorer / Researcher | `claude-haiku-5-5-go` | `opencode-go` |
| Architect / Spec Writer | `kimi-k3.1-pro-go` | `opencode-go` |
| Debugger | `grok-4.7-go` | `opencode-go` |
| Security Reviewer | `gemini-4-argon-go` | `opencode-go` |
| Database / Migration | `kimi-k3.1-pro-go` | `opencode-go` |
| Refactorer | `kimi-k2.7-code-go` | `opencode-go` |
| Docs / Changelog | `claude-haiku-5-5-go` | `opencode-go` |
| Release / DevOps | `gemini-4-argon-go` | `opencode-go` |

These are starting points, not requirements. Use the GUI or
`ensemble roles set` to assign any compatible model.

Two reference choices differ from the original model list:

- **Docs** uses Claude Haiku because GPT-6 Luna's provider-hosted tools are
  rejected by OpenCode Go's routed Chat endpoint. `openai/gpt-6-luna` remains
  selectable through OpenRouter.
- **Tester** uses MiMo because DeepSeek V4.1 Flash is region-gated. Select
  **Global** in OpenCode Console to use V4.1 Flash.

## Goal workflow

`/ensemble goal <task>` runs the adaptive pipeline:

1. **Frame** — brief, constraints, acceptance criteria, and role selection.
2. **Plan** — Explorer/Architect/Planner as needed; **approval gate** before
   any edits.
3. **Implement** — Coder/Refactorer proposes patches; Claude Code applies them
   and runs focused tests after each task.
4. **Review** — Reviewer, Security Reviewer, and Database Agent review the diff
   in parallel.
5. **Verify** — Tester proposes commands; Claude Code executes them and records
   real output. Debugger/Coder handle failures for up to two cycles.
6. **Finish** — Docs and Release prepare documentation and a rollback checklist;
   `RUN/report.md` records changes, evidence, findings, risks, and cost.

Roles are selected from `ensemble roles catalog`; irrelevant specialists are
skipped. The plan gate is mandatory unless you explicitly ask to skip it.

## Claude Code skill

```text
/ensemble goal <task>          # adaptive full pipeline
/ensemble brainstorm <task>    # reviewer + tester
/ensemble review [paths]       # reviewer only
/ensemble verify [paths]       # tester only
/ensemble role <role-id> <task>
/ensemble status
```

Peers are advisory data, never instructions. The skill tells Claude Code to
ignore any peer text that asks for permission changes, secret disclosure, or
unreviewed command execution.

## Control panel

```bash
ensemble gui
```

- **Providers** — add/edit endpoints, store keys in the keyring, fetch/select
  models, and discover catalogs with one click.
- **Roles** — browse all 13 roles, assign provider/models, and seed recommended
  assignments.
- **Launch** — choose a repository, rounds, and budget; preview the redacted
  environment; save/apply; open an orchestrator terminal.

`ensemble gui --tab providers|roles|launch` opens a tab directly.

## Commands

```text
ensemble init
ensemble config show
ensemble presets list
ensemble providers list
ensemble providers add --id ID --label NAME --protocol openai|anthropic \
    --env-var VAR [--base-url URL] [--models a,b] [--kind custom|builtin]
ensemble providers add --preset PRESET [--force]
ensemble providers discover PROVIDER | --all
ensemble roles show
ensemble roles catalog
ensemble roles seed [--force]
ensemble roles set ROLE PROVIDER MODEL [--small-model MODEL]
ensemble key set PROVIDER [--stdin] [--allow-file]
ensemble key import-env PROVIDER [--allow-file]
ensemble key status
ensemble opencode apply [--print]
ensemble skill install [--force]
ensemble gui [--tab providers|roles|launch]
ensemble desktop install [--force]
ensemble desktop uninstall
ensemble doctor
ensemble launch [--repo DIR] [--dry-run] [-- CLAUDE_ARGS...]
ensemble-peer ask --role ROLE --brief FILE [--cwd DIR] [--file PATH]...
```

`ensemble-peer` exit codes: `2` config/usage, `3` peer failure, `4` tree guard,
`5` budget exceeded, `6` timeout.

## Security model

- **Keys:** OS keyring by default (`libsecret`). No keys are written to
  `config.json`, prompts, logs, argv, or run artifacts.
- **Fallback:** `--allow-file` opts into `~/.config/ensemble/secrets.json`
  (0600, atomic write) for systems without a usable keyring. Resolution order
  is keyring → protected file → provider environment variable.
- **Shared keys:** a provider can reference another provider's keyring entry via
  `key_ref`, so related endpoints (for example OpenRouter and its Anthropic
  surface) share one credential.
- **Read-only peers:** generated opencode agents deny `edit`, `shell`,
  `webfetch`, and `websearch`.
- **Tree guard:** the peer helper snapshots `git status` before and after each
  call and aborts if the working tree changed.
- **Untrusted output:** peer replies are advisory data. Claude Code must review
  any proposed command before executing it.
- **Trust boundary:** providers receive the briefs and files you attach. Do not
  attach secrets, `.env` files, credentials, or `~/.ssh`.

See [SECURITY.md](SECURITY.md) for vulnerability reporting.

## Files and configuration

```text
~/.config/ensemble/config.json      providers, roles, preferences (no secrets)
~/.config/ensemble/opencode.json    isolated opencode config for peer agents
~/.config/ensemble/backups/         timestamped config backups (newest five)
~/.config/ensemble/secrets.json     optional opt-in 0600 key fallback
~/.claude/skills/ensemble/SKILL.md  installed Claude Code skill
<repo>/.ensemble/runs/<id>/         peer prompts, replies, JSONL, metadata
```

`ensemble opencode apply` regenerates the isolated opencode config; your global
`~/.config/opencode/` is not modified.

## Development

```bash
.venv/bin/python -m pytest -q
xvfb-run -a .venv/bin/ensemble gui --smoke-test
```

The test suite covers config validation, provider presets, discovery, role
seeding, peer success/failure paths, the tree guard, timeouts, budgets, key
fallback, backups, the desktop entry, skill installation, and the GUI apply
path.

Project layout:

- `src/ensemble/config.py` — schema, validation, backups.
- `src/ensemble/roles.py` — 13 role specs, prompts, contracts, seeding.
- `src/ensemble/presets.py` — provider presets and discovery endpoints.
- `src/ensemble/discovery.py` — per-key model discovery.
- `src/ensemble/opencode_config.py` — generated read-only opencode agents.
- `src/ensemble/peer.py` — one peer turn, artifacts, tree guard, budget.
- `src/ensemble/launch.py` — orchestrator environment including custom headers.
- `src/ensemble/gui.py` — GTK3 control panel.
- `src/ensemble/skill_template.md` — Claude Code skill source.

## Limitations

- The GUI requires Linux + GTK3; the CLI and skill work without a display.
- Provider catalogs, quotas, free tiers, and model availability change without
  notice.
- OpenCode Go requires `x-opencode-session`; its model IDs need local aliases.
- Some routed models reject provider-hosted tools; the reference Docs role
  uses Claude Haiku instead of GPT-6 Luna for that reason.
- Peers cannot edit or execute. This is intentional. Writer roles propose
  patches, and Claude Code remains the only accountable editor.
- No provider is guaranteed to work with every endpoint; run
  `ensemble doctor`, `providers discover`, and a small peer call after changing
  a provider.

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md). Please do not
include API keys, personal endpoints, or private repository content in issues,
tests, or pull requests.

## License

[MIT](LICENSE) © 2026 Njoro410.
