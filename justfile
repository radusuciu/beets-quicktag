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
