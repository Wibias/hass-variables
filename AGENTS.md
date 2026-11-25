# AGENTS

## Purpose

- Provide clear, repo-specific instructions for autonomous agents working in this repository.

## General Guidelines

- Follow Home Assistant developer docs: https://developers.home-assistant.io/docs/.
- Be concise and explain coding steps briefly when making code changes; include code snippets and tests where relevant.
- For non-trivial edits, provide a short plan. For small, low-risk edits, implement and include a one-line summary.
- Focus on a single conceptual change at a time when public APIs or multiple modules are affected.
- Maintain project style and Python 3.14+ compatibility. Target latest Home Assistant core.
- Treat the `homeassistant` value in `hacs.json` as the minimum supported Home Assistant version. HA-facing changes must work from that minimum through the Home Assistant version used for validation; verify the relevant version boundaries rather than assuming the latest API exists everywhere in that range.
- When an API or behavior differs within the supported range, ask the user to choose before implementing: add a narrow, capability-gated compatibility shim, or raise the `hacs.json` minimum version. Do not make that compatibility-policy decision autonomously.
- If deviating from these guidelines, explicitly state which guideline is deviated from and why.

## Agent permissions and venv policy

- Agents may create and use a repository-local venv at `./.venv`. Use `./.venv/bin/python`, `./.venv/bin/pytest`, and `./.venv/bin/prek` for local commands unless using the main checkout venv for a git worktree with no dependency changes.
- The project uses `pyproject.toml` dependency groups (`ha`, `lint`, `pytest`, `dev`). Installing packages from repo manifests into `./.venv` is allowed for running tests or local tooling.

## Folder structure (repo-specific)

- `custom_components/variable`: integration code.
- `tests`: pytest test suite and fixtures.
- `README.md`: primary documentation.
- `.github/workflows`: GitHub Workflows
- `.github/scripts`: scripts for GitHub Workflows

## Project structure expectations

- Keep code modular: separate files for entity types, services, and utilities.
- Store constants in `const.py` and use a `config_flow.py` for configuration flows.

## Coding standards

- Add typing annotations to all functions and classes (including return types).
- Add or update docstrings for all files, classes and methods, including private methods and nested methods. Method docstrings must follow the Google Style.
- Preserve existing comments and keep imports at the top of files.
- Do not use `assert` or `cast` in main code.
- Follow existing repository style; run `prek`.
- Python 3.14 syntax is allowed, including PEP 695 type parameters and PEP 758 grouped exception handlers already used in the codebase.

## Local tooling note

- Use the repo's `prek` and `pytest` commands through the venv selected by the agent permissions and venv policy above.
- By default, run the full pytest suite. If running targeted tests, explain why.

## Error handling & logging

- Use Home Assistant's logging framework.
- Catch specific exceptions (do not catch Exception directly).
- Add robust error handling and clear debug/info logs.
- If tests fail due to missing dev dependencies, either install them into `./.venv` (if allowed) or report exact `pip install` commands.

## Testing

- Use `pytest` and Home Assistant pytest helpers (e.g., `MockConfigEntry`).
- Add typed, well-documented tests in `tests/` and use fixtures in `conftest.py`.
- Use `importlib` only in workflow script tests; minimize `cast` and `Any` unless the test boundary requires them.
- One test module per integration source file; achieve high coverage (target >= 80%).
- Parameterize tests when appropriate; avoid duplicate test functions.

## PR & branch behavior

- Create branches or PRs only when explicitly requested. Do not open PRs autonomously.

## Network access

- Run read-only lookups that inform the task without asking: GitHub, Home Assistant docs and core source, and PyPI.
- Ask first for package installs beyond the repo manifests and for any write to an external service that this file does not already authorize.

## CI/CD

- Use GitHub Actions for CI/CD where applicable.

## Conventions for changes and documentation

- When editing code, prefer fixing root causes over surface patches.
- Keep changes minimal and consistent with the codebase style.
- Add tests for any changed behavior and update documentation if needed.
