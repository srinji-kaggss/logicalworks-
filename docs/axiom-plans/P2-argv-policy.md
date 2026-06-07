# P2 - Test Matrix Argv Policy Gate

## Goal

Add a deterministic policy gate for `lgwks axiom test-matrix` argv commands.

## Why

The hardening pass removed shell strings from matrix files. The next gap is command intent: argv can still
invoke destructive tools. We need a local deterministic classifier before execution.

## Files

- Modify: `lgwks_axiom.py`
- Modify: `tests/test_axiom_cli.py`
- Modify: `docs/spec-axiom-test-matrix-2026-06-06.md`

## Policy v0

Allow by default:

- `python`, `python3`
- `uv`
- `pytest`
- `git status`, `git diff`, `git log`, `git rev-parse`, `git branch --show-current`

Block by default:

- `rm`, `mv`, `cp` with recursive flags, `chmod`, `chown`
- `git push`, `git reset`, `git checkout`, `git clean`, `git commit`, `git merge`, `git rebase`
- `curl`, `wget`, `ssh`, `scp`
- any command containing absolute paths outside repo when used as file args

Add override:

```bash
lgwks axiom test-matrix --allow-risky ...
```

Even with `--allow-risky`, record `"policy": {"risk": "risky", "allowed_by": "flag"}` in test evidence.

## Implementation Steps

1. Add `class CommandPolicyError(ValueError)`.
2. Add `classify_argv(argv: tuple[str, ...], repo: Path) -> dict`.
3. Validate each `TestSpec` before `_test_fact`.
4. Add `--allow-risky` to parser.
5. Persist policy result in each test fact.

## Acceptance Tests

- Matrix with `["rm", "-rf", "x"]` fails without `--allow-risky`.
- Matrix with `["python", "-m", "py_compile", "lgwks_axiom.py"]` passes.
- Risky override runs but records policy metadata.
- Manifest includes `--allow-risky`.

## Do Not Do

- Do not use AI/model classification.
- Do not inspect command strings with shell parsing; matrix uses argv.

