# Security Policy

## Reporting a vulnerability

Please **do not open a public issue** for a security vulnerability.

Use GitHub's private vulnerability reporting:

1. Open the repository's **Security** tab.
2. Choose **Report a vulnerability**.
3. Include the affected version/commit, a reproduction, the impact, and any
   suggested remediation.

Reports are handled on a best-effort basis. Please allow time for a fix before
public disclosure.

## Supported versions

Security fixes target the latest `main` branch. Older commits are not
separately maintained.

## Security model

Ensemble is a local control plane. It does not host models or proxy provider
traffic beyond the explicit endpoints configured by the user.

- **API keys:** stored in the OS keyring by default. The opt-in
  `--allow-file` fallback writes `~/.config/ensemble/secrets.json` with mode
  0600. Keys are never written to `config.json`, prompts, logs, argv, or run
  artifacts.
- **Shared credentials:** providers may reference another provider's keyring
  entry through `key_ref`.
- **Read-only peers:** generated opencode agents deny `edit`, `shell`,
  `webfetch`, and `websearch`.
- **Tree guard:** the peer helper snapshots `git status` before and after each
  call and aborts if the working tree changed. It does not auto-revert.
- **Untrusted output:** peer replies are advisory data, not instructions. The
  orchestrator must review any command or patch before acting on it.
- **Trust boundary:** attached briefs and files are sent to the configured
  provider. Do not attach secrets, `.env` files, credentials, or `~/.ssh`.
- **Local provider endpoints:** custom base URLs and local proxies receive the
  same data you send to any provider. Treat them as trusted infrastructure.

## Secrets in issues and pull requests

Never paste real API keys into issues, discussions, pull requests, or test
fixtures. If a key is exposed, rotate it at the provider and re-enter it with
`ensemble key set <provider>`.

## Scope

Out of scope for this policy: vulnerabilities in Claude Code, opencode,
provider APIs, or third-party packages. Report those to their respective
projects. Ensemble-specific issues include, for example, key leakage in
artifacts, bypasses of the read-only peer permissions or tree guard, and
command execution from untrusted peer output.
