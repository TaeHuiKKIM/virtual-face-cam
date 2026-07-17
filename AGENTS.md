# AGENTS.md

## Repository Expectations

- Before development, create or update `docs/` with planning notes, implementation decisions, troubleshooting, or verification evidence when the change is meaningful.
- Keep `README.md` current whenever setup, behavior, commands, outputs, or workflow expectations change.
- Prefer existing project patterns over new abstractions.
- Run the most relevant build, lint, test, or manual verification before reporting completion.
- When handing work between machines, prefer branches and draft pull requests over uncommitted local-only changes.

## Security

- Never stage or commit `.env` files, API keys, tokens, credentials, private certificates, or secret-bearing logs.
- Do not include secrets even when explicitly asked to push all files.
- Keep secrets in local environment variables, ignored files, or the platform's secret manager.
- Before commits, inspect staged diffs for secret-looking values.

## Git Safety

- Do not reset, checkout away, or delete user work unless explicitly asked for that exact operation.
- Stage only files that belong to the requested change.
- If another branch or pull request is active, keep agent setup changes isolated in their own branch.

## Agent Workflow

- For broad autonomous work, use `$agentic-ship` when available.
- For reusable Codex setup, prefer repo-local `AGENTS.md`, focused `.agents/skills`, project `.codex/config.toml`, optional hooks/rules, and docs/README updates.
- If additional agent instruction files such as `CLAUDE.md` exist, preserve their intent and avoid conflicting guidance.