# Ensemble — multi-provider control plane and peer protocol

**Date:** 2026-11-18
**Status:** approved; Phases 1–5 complete; live discovery, 13-role catalog,
Haiku/peer acceptance, and the adaptive goal pipeline verified

## Goal

Run Claude Code with a non-Anthropic model (DeepSeek) as the orchestrator, and
use other providers/models as read-only collaborators:

- **Orchestrator:** Claude Code, driven by DeepSeek through its
  Anthropic-compatible endpoint. The only agent that writes files or executes
  commands.
- **Reviewer:** opencode + `tencent/hy4` (via OpenRouter). Reviews briefs,
  diffs, and code read-only.
- **Test-runner:** opencode + `xiaomi/mimo-v2.6-flash` (via OpenRouter).
  Proposes verification plans and test commands read-only; the orchestrator
  executes them.

A GTK3 desktop app (Phase 3) manages providers, API keys, model catalogs, and
role assignments, then launches an orchestrator terminal.

## Decisions

1. **The GUI is a control plane, not the runtime.** All agent behavior stays in
   Claude Code and opencode. The app only stores config, assigns roles, and
   launches.
2. **Driver + tools, not a chat room.** Claude Code decides when to call peers
   through a small `ensemble-peer` CLI. No MCP broker, no GUI-owned agent loop.
3. **Peers are read-only advisors.** opencode agents deny `edit` and `shell`;
   only the orchestrator writes or executes. A git tree guard aborts a run if
   the working tree changes during a peer call.
4. **Keys live in the OS keyring.** libsecret via Python `keyring`. Keys never
   appear in config files, argv, logs, or generated configs.
5. **Peer invocations use an isolated opencode config** via
   `OPENCODE_CONFIG=~/.config/ensemble/opencode.json`. The user's global
   `~/.config/opencode/` is never modified by Phase 1.
6. **Provider protocol is typed.** `anthropic` providers can drive Claude Code;
   opencode peers accept either `anthropic` or `openai` wire protocols.
7. **Cost/latency-appropriate roles.** Hy4 review turns cost roughly cents;
   MiMo flash test plans cost fractions of a cent. Default budget cap $0.50 per
   run directory.
8. **No global opencode config merge.** Peer runs use `OPENCODE_CONFIG`; the
   user's `~/.config/opencode/` is left untouched. `ensemble opencode apply
   --print` supports manual reuse if wanted.

## Architecture

```
┌──────────────────────────────────────┐
│ Ensemble GUI — Python 3 + GTK3       │  Phase 3
│ providers · keys (keyring) · roles   │
└───────────────┬──────────────────────┘
                │ writes config + generates
                │ ~/.config/ensemble/{config.json,opencode.json}
                │ ~/.claude/skills/ensemble (Phase 2)
                │ launch.sh (no secrets)
┌───────────────▼──────────────────────┐
│ Claude Code on DeepSeek              │  only writer & executor
│   /ensemble brainstorm <task>        │
└────────┬────────────────────┬────────┘
         │ ensemble-peer ask  │ ensemble-peer ask
         ▼                    ▼
  opencode + Hy4        opencode + MiMo
  edit/shell denied     edit/shell denied
```

Run artifacts live in `<repo>/.ensemble/runs/<UTC timestamp>-<slug>/`:
brief, each prompt/reply pair, raw JSONL, and metadata with model, duration,
cost, and tokens. This is the audit trail and the future GUI viewer's data
source.

## Configuration

`~/.config/ensemble/config.json` (0600, no secrets):

```json
{
  "version": 1,
  "providers": {
    "deepseek": {
      "label": "DeepSeek",
      "protocol": "anthropic",
      "base_url": "https://api.deepseek.com",
      "env_var": "DEEPSEEK_API_KEY",
      "kind": "custom",
      "models": ["deepseek-flash", "deepseek-v4-pro"]
    },
    "openrouter": {
      "label": "OpenRouter",
      "protocol": "openai",
      "base_url": "https://openrouter.ai/api/v1",
      "env_var": "OPENROUTER_API_KEY",
      "kind": "builtin",
      "models": ["tencent/hy4", "tencent/hy4-flash",
                 "xiaomi/mimo-v2.6-flash", "xiaomi/mimo-v2.5-pro"]
    }
  },
  "roles": {
    "orchestrator": {"provider": "deepseek", "model": "deepseek-flash"},
    "reviewer": {"provider": "openrouter", "model": "tencent/hy4"},
    "test_runner": {"provider": "openrouter",
                    "model": "xiaomi/mimo-v2.6-flash"}
  },
  "prefs": {
    "default_repo": null,
    "terminal": "gnome-terminal",
    "timeout_seconds": 180,
    "max_files": 20,
    "max_brief_bytes": 102400,
    "budget_usd": 0.5,
    "rounds": 2
  }
}
```

`ensemble init` imports the current `ANTHROPIC_BASE_URL` and `ANTHROPIC_MODEL`
when present. It does not copy keys; `ensemble key import-env <provider>` does
that explicitly.

### Generated opencode config

`ensemble opencode apply` writes `~/.config/ensemble/opencode.json`:

- `providers.<id>` for custom providers, with `env: [VAR]`, `package:
  "@opencode/ai/providers/openai-compatible"` (or `anthropic-compatible`),
  `settings.baseURL`, and a `models` map.
- Built-in providers such as `openrouter` are omitted so opencode's native
  catalog and variants keep working; the helper only supplies the env var.
- `agents.ensemble-reviewer` and `agents.ensemble-test-runner`, each with
  ordered permissions denying `edit` and `shell`, mode `primary`, and a role
  system prompt.

The peer helper passes `OPENCODE_CONFIG` to point at this file. It also passes
`--standalone`: on opencode 2.3.2 the background service ignores
`OPENCODE_CONFIG`, while a standalone run honors it (verified with
`opencode --standalone debug agents`).

### Provider presets and discovery

Four presets ship with documented endpoints:

| Preset | Protocol | Base URL | Models endpoint | Key check |
| --- | --- | --- | --- | --- |
| `openrouter` | openai | `https://openrouter.ai/api/v1` | `/models` | `/auth/key` |
| `openrouter-anthropic` | anthropic | `https://openrouter.ai/api` | `/v1/models` | `/auth/key` |
| `opencode-go` | openai | `https://opencode.ai/inference/go/openai/v1` | `/models` | models call requires key |
| `deepseek` | anthropic | `https://api.deepseek.com/anthropic` | `https://api.deepseek.com/models` | models call requires key |

OpenCode Go's gateway requires an `x-opencode-session` header on chat requests;
the preset is a custom OpenAI-compatible provider carrying that header. It uses
a distinct provider id (`opencode-go`) because the built-in `opencode` id
overrode custom model entries. Models carry a local `-go` suffix which the
generated config maps back through `modelID`; the alias prevents opencode from
applying its native model-family routing (which returned 404 for Gemini).
Discovery sends `User-Agent: ensemble/0.1`; Cloudflare returns error 1010 for
urllib's default signature.

`openrouter-anthropic` exposes OpenRouter's Anthropic Messages surface at
`https://openrouter.ai/api`; Claude Code appends `/v1/messages`. It shares the
OpenRouter key via `key_ref: openrouter`.

`ensemble presets list` shows them; `providers add --preset` fills the provider
record; `providers discover PROVIDER|--all` fetches the catalog with the stored
key and saves only the model IDs that key can see. The GUI exposes the same
flow through the preset picker, **Fetch models**, and **Discover models**.
DeepSeek remains a custom Anthropic-compatible provider for Claude Code.

### Secrets

- Keyring service `ensemble`, username = provider id, or the provider's
  `key_ref` when one provider shares another's key (for example
  `openrouter-anthropic` → `openrouter`).
- Resolution order: keyring, then the provider's configured env var.
- `ensemble key set` reads via getpass or stdin; never accepts a key argument.
- Launch exports keys in-process; no launcher file or secret is written.
- Opt-in protected-file fallback: `--allow-file` stores keys in
  `~/.config/ensemble/secrets.json` (0600, atomic write) when the keyring cannot
  be used. Resolution order is keyring → protected file → env. The file is
  plaintext, so it is never used automatically.

## Collaboration protocol

Claude Code skill (Phase 2) exposes:

- `/ensemble goal <task>` — adaptive full pipeline through the role catalog.
- `/ensemble brainstorm <task>` — brief → reviewer → test-runner → synthesis;
  optional second round where the reviewer sees the revision.
- `/ensemble review [paths]` — reviewer only.
- `/ensemble verify` — test-run plan only.
- `/ensemble role <role-id> <task>` — any peer role.
- `/ensemble status` — show roles, models, and recent run artifacts.

`ensemble skill install` writes `~/.claude/skills/ensemble/SKILL.md` with the
absolute paths of the installed `ensemble` and `ensemble-peer` binaries, then
the session is restarted to load `/ensemble`.

Peer output contract:

- Reviewer: **Findings / Risks / Questions / Recommended options**, with
  `file:line` citations.
- Test-runner: **Test plan / Commands (not executed) / Expected outcomes /
  Coverage gaps**.

Guardrails: at most 20 attachments and ~100 KB brief per call; default budget
$0.50 per run dir; 180s per peer call; `--file` paths resolve relative to
`--cwd`; peer output is advisory data and must not be executed verbatim.

`ensemble-peer` writes `NN-role.prompt.md`, `NN-role.raw.jsonl`, `NN-role.md`,
and `NN-role.meta.json`; it exits `2` on config/usage errors, `3` on peer
failure, `4` on tree-guard violation, `5` on budget, `6` on timeout.

## 13-role catalog

`ensemble roles seed --force` assigns the catalog below. All non-orchestrator
roles are read-only advisors; Claude Code is the only writer/executor. Coder,
Refactorer, and Docs propose patches; Tester and Debugger propose commands.

| Role | Recommended model | Assigned provider |
| --- | --- | --- |
| Orchestrator | `anthropic/claude-haiku-5.5` | `openrouter-anthropic` |
| Planner | `gemini-4-argon` | `opencode-go` (`gemini-4-argon-go`) |
| Coder / Implementer | `kimi-k2.7-code` | `opencode-go` |
| Reviewer | `grok-4.7` | `opencode-go` |
| Tester / Verifier | `deepseek-v4.1-flash` | `opencode-go` (`mimo-v2.6-flash-go` fallback) |
| Explorer / Researcher | `claude-haiku-5-5` | `opencode-go` |
| Architect / Spec Writer | `kimi-k3.1-pro` | `opencode-go` |
| Debugger | `grok-4.7` | `opencode-go` |
| Security Reviewer | `gemini-4-argon` | `opencode-go` |
| Database / Migration | `kimi-k3.1-pro` | `opencode-go` |
| Refactorer | `kimi-k2.7-code` | `opencode-go` |
| Docs / Changelog | `gpt-6-luna` | `opencode-go` (`claude-haiku-5-5-go` fallback) |
| Release / DevOps | `gemini-4-argon` | `opencode-go` |

Two substitutions are deliberate: OpenCode Go routes GPT-6 Luna with a
provider-hosted tool that the routed Chat endpoint rejects, so Docs uses Claude
Haiku (OpenRouter GPT-6 Luna remains selectable); DeepSeek V4.1 Flash is
region-gated until the Console is set to Global, so Tester uses MiMo.

## Goal pipeline (Phase 5)

`/ensemble goal <task>` makes the 13 roles cooperate on one goal:

1. **Frame** — write the brief and acceptance criteria; use `roles catalog` to
   select roles and record the rationale.
2. **Plan** — Explorer/Architect/Planner, then a **plan-approval gate** before
   any edits.
3. **Implement** — Coder/Refactorer proposes patches; Claude Code applies them
   and runs focused tests after each task.
4. **Review** — Reviewer, Security Reviewer, and Database Agent run in parallel
   on the diff; Claude Code fixes blocking findings.
5. **Verify** — Tester proposes commands; Claude Code executes them and records
   real output. Debugger/Coder handle failures for up to two cycles.
6. **Finish** — Docs and Release prepare documentation and a rollback checklist;
   `RUN/report.md` records changes, real test evidence, findings, risks, and
   peer cost.

Role selection is adaptive: Planner/Reviewer/Tester are always included;
Explorer, Architect, Security, Database, Debugger, Coder/Refactorer, Docs, and
Release are added only when the task shape requires them. All peers remain
read-only; Claude Code is the sole writer and executor.

## GUI (Phase 3)

Three GTK3 tabs:

- **Providers:** list with protocol badge, model count, key status. Add/Edit
  dialog with masked key field, keyring save, Test Connection + `/models`
  discovery, manual model list fallback.
- **Roles:** dropdowns for orchestrator/reviewer/test-runner, filtered by
  protocol; optional small/fast model mapping for Claude Code.
- **Launch:** repo picker, rounds (1–3), budget cap, redacted env preview,
  Save & Apply, Open Orchestrator.

Launch spawns `gnome-terminal --working-directory <repo> -- bash -lc
'<python> -m ensemble.cli launch --repo <repo>'`. `ensemble launch` builds the
orchestrator environment, resolves the key from the keyring in-process, and
`exec`s `claude`; no launcher file or secret is written. `ensemble gui --tab
providers|roles|launch` opens a specific tab.

`ensemble desktop install` writes
`~/.local/share/applications/ensemble.desktop` and a hicolor icon. Generated
`config.json` and `opencode.json` files are copied to
`~/.config/ensemble/backups/` when their content changes, keeping the newest
five per file.

## Failure handling

- Missing key / locked keyring: abort with provider name; suggest env var.
- Bad provider/model: Test Connection shows HTTP status; peer exits `3`.
- opencode missing/outdated: helper checks before running.
- Timeout: process group killed; exit `6`.
- Tree-guard violation: abort, keep before/after status and diff; never
  auto-revert.
- Malformed config: refuse to overwrite; keep timestamped backup on apply.
- Budget exceeded: no further turn starts; report spend by role.
- 429/5xx: one retry honoring `Retry-After` (Phase 2).

## Testing

- Unit: config schema/validation, role/protocol compatibility, opencode config
  generation, secret redaction, cost math.
- Integration: fake `opencode` executable emitting JSONL; covers extraction,
  env injection, run artifacts, tree guard, timeout, budget, and missing key.
- Contract (opt-in): real Hy4 review and MiMo test plan against a throwaway
  repo with real keys.
- GUI: module import test, Xvfb smoke test, and an Xvfb Save & Apply test that
  writes config, opencode config, and the skill.

## Build phases

1. **Core CLI (Phase 1, done):** config, keyring, opencode config generation,
   `ensemble-peer`, `ensemble launch`. Verified end to end with a real DeepSeek
   peer call (reply, cost/token metadata, artifacts, tree guard). The Hy4/MiMo
   contract test awaits `OPENROUTER_API_KEY`.
2. **Skill (Phase 2, done):** `/ensemble` modes, logging, tree guard
   integration, budget enforcement. The install command renders the skill with
   absolute binary paths.
3. **GUI (Phase 3, done):** GTK3 control panel, first-run import, Apply +
   Launch. Verified with Xvfb screenshots and a Save & Apply integration test.
4. **Polish (Phase 4, done):** `.desktop` entry + icon, opt-in protected-file
   fallback, backup rotation, and docs. Global opencode merge intentionally
   omitted in favor of `OPENCODE_CONFIG` isolation.
5. **Goal pipeline (Phase 5, done):** `/ensemble goal` adaptive role selection,
   plan approval gate, parallel reviews, test-evidence loop, Docs/Release
   handoff, and `roles catalog`.

## Model notes (as of 2026-11-18)

OpenRouter IDs confirmed from its public model catalog:

- `tencent/hy4` — 1,048,576 context; $0.417/M input, $1.2505/M output.
- `tencent/hy4-flash` — $0.035/M input, $0.1405/M output.
- `xiaomi/mimo-v2.6-flash` — 1,050,000 context; $0.14/M input, $0.28/M output.

DeepSeek's current IDs, as exposed by opencode 2.3.2, are
`deepseek/deepseek-flash` and `deepseek/deepseek-v4-pro`. The legacy
`deepseek-chat` / `deepseek-reasoner` IDs are not available there.

Observed at setup time (2026-11-18): OpenRouter listed 443 models;
OpenCode Go listed 32, including `hy4`, `hy4-preview`, `mimo-v2.6-flash`,
`mimo-v2.6-pro`, `deepseek-v4.1-flash`, `deepseek-v4-pro`, `glm-5.3`,
`kimi-k3`, and `claude-haiku-5-5`; DeepSeek listed 2.

### Acceptance results (2026-11-18)

- Claude Code on **Claude Haiku 5.5** through OpenRouter's Anthropic surface:
  non-interactive launch returned `READY`, exit 0.
- Hy4 reviewer through OpenRouter: 5,651 input / 699 output tokens, $0.004757,
  27.8s; found the injected bug and followed the output contract.
- MiMo test plan through OpenRouter: 5,753 input / 1,298 output tokens,
  $0.001181, 25.7s.
- MiMo reviewer through OpenCode Go: 4,887 input / 383 output tokens, 21.4s;
  Go subscription reported cost 0; repo stayed unchanged.
- Real role turns through OpenCode Go: Planner (`gemini-4-argon-go`), Reviewer
  (`grok-4.7-go`), Coder (`kimi-k2.7-code-go`), Docs
  (`claude-haiku-5-5-go`), and Tester (`mimo-v2.6-flash-go`) all returned
  contract-compliant read-only replies.
- All keys resolve from the OS keyring; the working tree guard passed on every
  call.

Hy4 is Tencent's 770B-total / 49B-active flagship announced 2026-11-04, with
strong agentic-coding scores but a high hallucination rate on knowledge it does
not have (89% on AA-Omniscience). That makes it suitable as a critic and
option-generator, not as a source of truth; the orchestrator must verify claims.

## Risks

- opencode v2 config/agent schema is new and may change; the generator is
  isolated in one module and verified with `opencode --standalone debug agents`.
- `OPENCODE_CONFIG` is honored only with `--standalone` on opencode 2.3.2; the
  helper always passes it.
- Keyring requires an unlocked Secret Service session; headless/CI users must
  use env vars.
- The GUI venv must be created with `--system-site-packages` so PyGObject/GTK3
  are importable; pip-installed packages still take precedence.
- The protected-file fallback is plaintext; it is opt-in per key and 0600, but
  users with a working keyring should not need it.
- Peer context is bounded by attached files; the orchestrator must curate them.
- Two CLIs with different permission models: keep the driver-only rule strict.

## Sources

- Tencent Hy4 announcement: https://www.tencent.com/tencent-launches-hy4-joining-the-ranks-of-the-worlds-leading-open-source-ai-models/
- Hy4 coverage: https://www.heise.de/en/news/Tencent-Hy4-New-AI-model-joins-China-s-top-tier-11513717.html
- OpenRouter model catalog: https://openrouter.ai/api/v1/models
- OpenRouter API overview: https://openrouter.ai/docs/api-reference/overview
- Claude Code gateway protocol: https://code.claude.com/docs/llm-gateway-protocol
- OpenCode Go specifics: https://opencode.ai/v2/docs/console/go/
- opencode providers docs: https://opencode.ai/docs/providers/
- opencode agents docs: https://opencode.ai/docs/agents/
- OpenCode Console harnesses: https://opencode.ai/docs/console/harnesses/
- OpenCode Go specifics: https://opencode.ai/v2/docs/console/go/
- DeepSeek list-models API: https://api-docs.deepseek.com/api/list-models/
