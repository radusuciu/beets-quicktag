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

# Start a release: run the Release PR workflow on GitHub and open its pull request (BUMP: auto, patch, minor or major)
release BUMP="auto":
    #!/usr/bin/env bash
    set -euo pipefail
    gh workflow run release-pr.yml --ref main -f bump={{BUMP}}
    sleep 5
    run=$(gh run list --workflow release-pr.yml --limit 1 --json databaseId --jq '.[0].databaseId')
    gh run watch "$run" --exit-status
    branch=$(git ls-remote --heads origin 'release-v*' | sed 's|.*refs/heads/||' | sort -V | tail -1)
    version=${branch#release-v}
    git fetch -q origin "$branch"
    # the release notes are the first section of the regenerated changelog
    notes=$(git show "origin/$branch:CHANGELOG.md" | awk '/^## \[/ { n++ } n == 1' | tail -n +2)
    gh pr create --base main --head "$branch" --title "chore(release): prepare for v$version" --body "$notes"
