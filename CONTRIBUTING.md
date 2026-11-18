# Contributing to Ensemble

Thanks for taking an interest. Ensemble is an early-stage project; focused bug
reports, documentation fixes, and small, well-tested changes are the easiest to
review.

## Ground rules

- **Never commit secrets.** No API keys, `.env` files, credentials, private
  endpoints, or personal paths. Use environment variables or the OS keyring.
- **Keep peers read-only.** Do not weaken the generated opencode permissions
  (`edit`, `shell`, `webfetch`, `websearch` denied) or bypass the git tree
  guard. The single-writer model is a core safety property.
- **Keep the CLI and GUI in sync.** A config change should be usable from both.
- **Add tests** for behavior changes. Run the suite before opening a PR.
- **Treat peer output as untrusted.** Do not add features that execute peer
  suggestions without review.

## Development setup

```bash
git clone https://github.com/Njoro410/ensemble.git
cd ensemble
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -e .
.venv/bin/ensemble init
```

The venv must include system site packages for PyGObject/GTK3. The CLI works
without a display; the GUI needs an X11 or Wayland session.

## Tests

```bash
.venv/bin/python -m pytest -q
xvfb-run -a .venv/bin/ensemble gui --smoke-test
```

Tests must not make real provider calls or require real API keys. Use the
synthetic keys and local HTTP fixtures already in the suite.

## Project map

| Path | Responsibility |
|---|---|
| `src/ensemble/config.py` | Config schema, validation, backups |
| `src/ensemble/roles.py` | 13 role specs, prompts, contracts, seeding |
| `src/ensemble/presets.py` | Provider presets and endpoints |
| `src/ensemble/discovery.py` | Per-key model discovery |
| `src/ensemble/opencode_config.py` | Generated read-only opencode agents |
| `src/ensemble/peer.py` | One peer turn, artifacts, tree guard, budget |
| `src/ensemble/launch.py` | Claude Code environment, custom headers |
| `src/ensemble/gui.py` | GTK3 control panel |
| `src/ensemble/skill_template.md` | Claude Code skill source |
| `tests/` | Unit and integration tests |

## Pull requests

1. Fork the repository and create a branch.
2. Make the change with tests and documentation updates.
3. Run `.venv/bin/python -m pytest -q`.
4. Describe the behavior change, the motivation, and any provider-specific
   caveats. Include the commands you ran.
5. Keep pull requests focused; unrelated refactors belong in a separate PR.

## Commit style

Conventional-style subjects are appreciated but not required, for example:

```text
Fix tree guard on untracked files
Add planner role contract
Document OpenCode Go aliases
```

## License

By contributing, you agree that your contributions are licensed under the
project's [MIT License](LICENSE).
