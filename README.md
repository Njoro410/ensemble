# Ensemble

A control plane for running Claude Code as an orchestrator with other models as
read-only advisors (reviewer, test-runner) through opencode.

**Phase 1 (this scaffold):** config + keyring + provider generation + the
`ensemble-peer` helper. The GTK control panel is Phase 3.
Design: [docs/plans/2026-11-18-ensemble-multi-provider-design.md](docs/plans/2026-11-18-ensemble-multi-provider-design.md).

## Quick start

```bash
cd ~/projects/ensemble

# The GUI needs system PyGObject/GTK3, so include system site-packages.
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -e .

# Create ~/.config/ensemble/config.json, importing your current
# ANTHROPIC_BASE_URL / ANTHROPIC_MODEL if present.
.venv/bin/ensemble init

# Store keys in the OS keyring (never in config files or argv).
.venv/bin/ensemble key import-env deepseek     # from $DEEPSEEK_API_KEY
.venv/bin/ensemble key set openrouter          # prompts, input hidden

# Generate the isolated opencode config used by peer calls.
.venv/bin/ensemble opencode apply

# Check everything.
.venv/bin/ensemble doctor

# Install the Claude Code skill (writes ~/.claude/skills/ensemble/SKILL.md).
.venv/bin/ensemble skill install

# Add an application-menu launcher and icon.
.venv/bin/ensemble desktop install
```

## Claude Code skill

Restart or reload Claude Code after installing, then:

```
/ensemble brainstorm <task>
/ensemble review [paths]
/ensemble verify [paths]
/ensemble status
```

The installed skill embeds absolute paths to this venv's `ensemble` and
`ensemble-peer`, so it works without PATH changes.

## Control panel

```bash
.venv/bin/ensemble gui
```

Three tabs:

- **Providers** — add/edit endpoints, store keys in the OS keyring, fetch and
  select models, test connections.
- **Roles** — assign orchestrator/reviewer/test-runner providers and models.
- **Launch** — choose the repo, rounds, budget; preview the redacted
  environment; save & apply; open an orchestrator terminal.

`ensemble gui --tab providers|roles|launch` opens a specific tab directly.

## Key storage and backups

Keys go to the OS keyring by default. On headless or locked-keyring systems,
`ensemble key set PROVIDER --allow-file` opts into a plaintext
`~/.config/ensemble/secrets.json` (0600, atomic write). Resolution order is
keyring → protected file → the provider's env var. Nothing is ever written to
config files or command lines.

Generated `config.json` and `opencode.json` are backed up to
`~/.config/ensemble/backups/` whenever their content changes; the newest five
per file are kept.

## Provider presets and model discovery

Three documented presets are built in: **OpenRouter**, **OpenCode Go**, and
**DeepSeek**.

```bash
ensemble presets list
ensemble providers add --preset opencode
ensemble key set opencode
ensemble providers discover --all
```

Discovery uses each provider's documented endpoint:

| Provider | Models endpoint | Key check |
| --- | --- | --- |
| OpenRouter | `https://openrouter.ai/api/v1/models` | `/api/v1/auth/key` |
| OpenCode Go | `https://opencode.ai/inference/go/openai/v1/models` | models call requires the key |
| DeepSeek | `https://api.deepseek.com/models` | models call requires the key |

The GUI does the same: **Add provider → choose a preset → paste the key →
Fetch models**, or select a provider and click **Discover models**. Only models
visible to the supplied key are stored, and the role model dropdowns update
from that list.

## Desktop launcher

`ensemble desktop install` writes
`~/.local/share/applications/ensemble.desktop` plus a hicolor icon, so Ensemble
appears in the Cinnamon application menu. Remove it with
`ensemble desktop uninstall`.

## Run a peer call

```bash
.venv/bin/ensemble-peer ask \
  --role reviewer \
  --cwd ~/src/some-repo \
  --brief /tmp/brief.md \
  --file src/app.py
```

Artifacts are written to `~/src/some-repo/.ensemble/runs/<timestamp>/`:
`NN-role.prompt.md`, `NN-role.raw.jsonl`, `NN-role.md`, `NN-role.meta.json`.

Peers run through opencode with the generated `ensemble-reviewer` or
`ensemble-test-runner` agent, which denies `edit` and `shell`. A git tree guard
also aborts the run if the working tree changes during a peer call.

## Roles

| role | default provider | default model | who drives it |
| --- | --- | --- | --- |
| orchestrator | deepseek | deepseek-flash | Claude Code (Anthropic API) |
| reviewer | openrouter | tencent/hy4 | opencode, read-only |
| test_runner | openrouter | xiaomi/mimo-v2.6-flash | opencode, read-only |

Peer calls pass `--standalone` to opencode so `OPENCODE_CONFIG` is honored
(verified on opencode 2.3.2; the background service ignores it). `--file`
paths resolve relative to `--cwd`.

## Status

All four phases are implemented: config/keyring, read-only peer runner, the
`/ensemble` skill, the GTK control panel, desktop packaging, protected-file
fallback, backup rotation, and provider presets with per-key model discovery.
A real read-only reviewer call through opencode + DeepSeek was verified (reply,
cost/token metadata, run artifacts, tree guard), and the GUI was smoke-tested
under Xvfb. Enter the provider keys through the masked GUI field or the hidden
`ensemble key set` prompt, then run discovery. The Hy4/MiMo contract test needs
an OpenRouter key:

```bash
.venv/bin/ensemble key set openrouter
.venv/bin/ensemble doctor
```

## Commands

```
ensemble init
ensemble config show
ensemble presets list
ensemble providers list
ensemble providers add --id ID --label NAME --protocol openai|anthropic \
    --env-var VAR [--base-url URL] [--models a,b] [--kind custom|builtin]
ensemble providers add --preset openrouter|opencode|deepseek [--force]
ensemble providers discover PROVIDER | --all
ensemble roles show
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

Exit codes for `ensemble-peer`: `2` config/usage, `3` peer failure, `4` tree
guard, `5` budget exceeded, `6` timeout.
