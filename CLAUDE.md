# Dotfiles - Agent Guidelines

Personal dotfiles for macOS, also mounted into a Linux dev container. **This repo is public** - never commit secrets, tokens, internal hostnames, or employer/customer detail.

## Portability: assume the oldest interpreter

`#!/usr/bin/env python3` resolves against the *caller's* PATH, which is usually not the shell you tested in:

| Caller | `python3` resolves to |
|---|---|
| Interactive shell | homebrew / active venv - current |
| `cron/` (its PATH has no `/opt/homebrew/bin`) | `/usr/bin/python3` on Apple Silicon - **macOS ships 3.9** |
| `bin/tests` with `isolate_path=True` | `/usr/bin/python3` - that fixture *replaces* PATH, so the active venv is gone |

So Python in `bin/` targets **3.9**, whatever you happen to run locally:

- `from __future__ import annotations` in any file using `X | Y` annotations. Below 3.10 they are evaluated at runtime and raise `TypeError: unsupported operand type(s) for |: 'type' and 'NoneType'`.
- No `match`, no 3.10+ stdlib (`pairwise`, `zip(strict=)`, `tomllib`, `datetime.UTC`, `StrEnum`, `ExceptionGroup`).
- `bin/tests/test_interpreter_compatibility.py` enforces both. Fix the file it names; never silence it.

Shell scripts carry the same hazard from the other direction: macOS ships BSD coreutils, the container GNU. Prefer POSIX, and check `stat`, `sed -i`, `date` and `readlink` flags on both.

## Tests

`pytest bin/tests` must pass on **macOS and Linux**. GitHub Actions runs Linux only, so a green pipeline says nothing about the Mac - interpreter and coreutils both differ. Run it locally on macOS before trusting a change.

- Test names start with `should_`, read as a sentence describing what is proven, and follow AAA.
- **Never assert against a clock captured at import.** Relative-time output (`just now`, `1m ago`) drifts with suite duration: a 16 s local run and a 114 s CI run disagree, and the failure reads like a logic bug. Freeze the clock in the fixture.
- Loading a script via `module_from_spec`: set `sys.modules[spec.name] = mod` *before* `exec_module`. `dataclasses` resolves string annotations through `sys.modules[cls.__module__]` and raises `AttributeError` on `None`.
- `load_script` for pure functions (fast, precise), `run_cli` for wiring - exit codes, argparse errors, files actually created or deleted.
- Deleting a script deletes its tests in the same change.

## Code

- **Comments default to zero.** Write one only for a hack, an upstream-bug workaround, or a *why* that no name can carry. Never restate what the code or the commit message already says. If deleting it costs the reader nothing, delete it.
- SOLID, DRY, YAGNI, KISS. Named constants over magic numbers. Functions ~20 lines, 2-3 nesting levels.
- Delete dead code in the same change that orphans it, its tests included.
- New bin script: lowercase-hyphenated name, no extension, `chmod +x`, `shellcheck` clean.
- `set -uo pipefail` in standalone shell scripts - never in one designed to be `source`d, since strict mode leaks into the caller's interactive shell.
- Secrets come from `envify` / `keyguard` only. Never hardcoded, never written to disk, never echoed.

## Writing style

Short dashes (`-`), never em dashes. No filler, no shouting, no AI-tells. Commit subjects are imperative, uppercase first word, <= 72 chars, and explain *why* in the body when the diff does not.

## Before committing

1. `pytest bin/tests` green - on macOS, not only in the container
2. `shellcheck` clean on every touched shell file
3. Touched bin script runs end to end (`--help` at minimum)
4. Stage specific files by name, never `git add -A`
