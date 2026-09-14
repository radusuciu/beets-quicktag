# Run `just` with no arguments to list recipes.

default:
    @just --list

# Lint and check formatting (same commands as CI)
lint:
    uv run ruff check .
    uv run ruff format --check .

# Auto-fix lint errors and reformat
fix:
    uv run ruff check --fix .
    uv run ruff format .

# Type check with ty
typecheck:
    uv run ty check

# Run the test suite; extra args go to pytest (e.g. `just test -k playback`)
test *ARGS:
    # empty BEETSDIR so tests never read the real beets config
    BEETSDIR="$(mktemp -d)" uv run pytest {{ARGS}}

# Run everything CI runs
check: lint typecheck test

# Start a release: run the Release PR workflow on GitHub and wait for it (BUMP: auto, patch, minor or major)
release BUMP="auto":
    #!/usr/bin/env bash
    set -euo pipefail
    gh workflow run release-pr.yml --ref main -f bump={{BUMP}}
    sleep 5
    run=$(gh run list --workflow release-pr.yml --limit 1 --json databaseId --jq '.[0].databaseId')
    gh run watch "$run" --exit-status
    echo "Open the pull request from the link in the run summary:"
    gh run view "$run" --json url --jq .url
