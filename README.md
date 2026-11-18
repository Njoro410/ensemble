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
/ensemble goal <task>          # adaptive full pipeline
/ensemble brainstorm <task>
/ensemble review [paths]
/ensemble verify [paths]
/ensemble role <role-id> <task>
/ensemble status
```

`goal` is the team workflow: the orchestrator selects the relevant roles,
plans, implements through Coder proposals, runs parallel reviews, verifies with
real test output, and finishes with Docs/Release. Every peer stays read-only;
Claude Code applies every change.

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

OpenCode Go is configured as an explicit OpenAI-compatible provider because its
gateway requires an `x-opencode-session` header; the preset supplies
`x-opencode-session: ensemble`. Discovery sends `User-Agent: ensemble/0.1`
because Cloudflare rejects the default urllib signature.

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

`ensemble roles seed --force` installs this 13-role catalog. Every
non-orchestrator role is a **read-only advisor**; Claude Code remains the only
agent that writes files or executes commands.

| Role | Model | Provider |
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

The `-go` suffix is a local alias; the generated opencode config maps it back to
the upstream model via `modelID`, avoiding opencode's native model-family
routing. Two practical substitutions:

- **Docs** uses Claude Haiku because GPT-6 Luna's provider-hosted tools are
  rejected by the routed Go Chat endpoint. `openai/gpt-6-luna` is still
  selectable via OpenRouter.
- **Tester** uses MiMo because DeepSeek V4.1 Flash is region-gated by OpenCode
  Go (“Select Global” in the Console). Switch the role after changing region.

Peer calls pass `--standalone` to opencode so `OPENCODE_CONFIG` is honored
(verified on opencode 2.3.2; the background service ignores it). `--file`
paths resolve relative to `--cwd`.

## Status

Everything is implemented and verified with the stored keys:

- **13 roles** seeded; `/ensemble goal` runs the adaptive full pipeline
  (plan → approval gate → implement → parallel review → verify → docs/release).
- The orchestrator runs **Claude Haiku 5.5** through OpenRouter's Anthropic
  surface (`https://openrouter.ai/api`), and a non-interactive Claude Code
  launch returned `READY`.
- **OpenRouter** — 443 models; Hy4 review ($0.0048) and MiMo test plan
  ($0.0012) passed earlier.
- **OpenCode Go** — 32 models; real Planner (Gemini), Reviewer (Grok), Coder
  (Kimi), Docs (Haiku), and Tester (MiMo) turns passed read-only.
- **DeepSeek** — 2 models, available as an orchestrator fallback.

The GUI shows all providers with `keyring` status and model counts. To refresh
catalogs after a key change:

```bash
.venv/bin/ensemble providers discover --all
.venv/bin/ensemble roles seed --force
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
ensemble providers add --preset openrouter|openrouter-anthropic|opencode-go|deepseek [--force]
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

Exit codes for `ensemble-peer`: `2` config/usage, `3` peer failure, `4` tree
guard, `5` budget exceeded, `6` timeout.
