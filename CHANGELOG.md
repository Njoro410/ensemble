# Changelog

All notable changes to Ensemble are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- GitHub Actions CI: Python 3.10–3.12 tests, GTK3/Xvfb GUI tests, and `.deb`
  builds with artifacts plus tagged-release assets.
- `scripts/build-deb.sh` and Debian packaging metadata for an installable
  `ensemble_<version>_all.deb`.

## [0.1.0] - 2026-11-18

### Added

- Provider presets for OpenRouter, OpenRouter (Anthropic), OpenCode Go
  (OpenAI and Anthropic), and DeepSeek.
- Per-key model discovery, including OpenRouter key verification and OpenCode
  Go session headers.
- OS keyring storage with `key_ref` sharing, an opt-in 0600 protected-file
  fallback, environment fallbacks, and backup rotation.
- A 13-role catalog with per-role prompts, output contracts, recommended model
  assignments, and a `roles catalog` command.
- Read-only peer turns through opencode with `edit`, `shell`, `webfetch`, and
  `websearch` denied, a git tree guard, budgets, timeouts, and JSONL/meta
  artifacts.
- The `/ensemble` Claude Code skill with `goal`, `brainstorm`, `review`,
  `verify`, `role`, and `status` modes.
- Adaptive goal pipeline: role selection, plan approval gate, implementation
  through Coder proposals, parallel reviews, test-evidence verification, and
  Docs/Release handoff.
- GTK3 control panel for providers, keys, models, roles, and launching.
- Desktop launcher and icon, offline documentation, and 57 tests.

### Notes

- OpenCode Go model IDs use a local `-go` alias mapped through `modelID` to
  avoid native provider routing.
- The reference Docs role uses Claude Haiku because GPT-6 Luna's provider-hosted
  tools are rejected by OpenCode Go's routed Chat endpoint.
- The reference Tester role uses MiMo because DeepSeek V4.1 Flash is
  region-gated in OpenCode Go.
