"""Library-wide migrations that keep tracks in step with the definitions.

No Textual here. Every mutating function scans and stores inside one
transaction and calls ``item.store()`` only (never ``item.write()``). An
exception rolls the whole migration back, so the library is never left
half-migrated.

Tokens are compared whole and case-insensitively, the same way the app maps a
track's ``HAPPY`` onto the option ``happy``; ``House`` never matches
``Deep House``.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager

from beets.library import Item, Library

from .definitions import find_case_insensitive
from .item_values import read_item_values, write_item_values

_SAVEPOINT = "quicktag_migration"


def _dedupe(values: list[str]) -> list[str]:
    """Drop case-insensitive duplicates, keeping the first spelling and order."""
    result: list[str] = []
    for value in values:
        if find_case_insensitive(result, value) is None:
            result.append(value)
    return result


def _has_value(item: Item, category: str, value: str) -> bool:
    """True when ``category`` on ``item`` holds ``value`` as a whole token.

    Filtered in Python so the comparison is exactly the app's casefold,
    whole-token match. A SQL/beets-query prefilter would narrow the scan on
    a different, ASCII-only notion of case-insensitivity and could reject
    rows this would accept.
    """
    return find_case_insensitive(read_item_values(item, category), value) is not None


@contextmanager
def _migration(lib: Library) -> Iterator[None]:
    """A transaction whose writes are undone if the body raises.

    beets commits a transaction even when its body raised, so the rollback
    has to be explicit. It is a savepoint rather than ``ROLLBACK``: sqlite
    opens the transaction lazily, so a plain rollback before the first write
    raises and masks the real error, and a savepoint leaves a caller's own
    uncommitted work intact.
    """
    with lib.transaction() as tx:
        tx.mutate(f"SAVEPOINT {_SAVEPOINT}")
        try:
            yield
        except BaseException:
            tx.mutate(f"ROLLBACK TO {_SAVEPOINT}")
            tx.mutate(f"RELEASE {_SAVEPOINT}")
            raise
        tx.mutate(f"RELEASE {_SAVEPOINT}")


def _migrate(lib: Library, mutate: Callable[[Item], bool]) -> int:
    """Store every track ``mutate`` reports as changed; return how many.

    The scan runs inside the transaction, so the rows are read under its
    lock rather than snapshotted before it.
    """
    changed = 0
    with _migration(lib):
        for item in lib.items():
            if mutate(item):
                item.store()
                changed += 1
    return changed


def count_tracks(lib: Library, category: str, value: str | None = None) -> int:
    """Tracks carrying ``value`` in ``category``, or any value when ``None``."""
    if value is None:
        return sum(1 for item in lib.items() if read_item_values(item, category))
    return sum(1 for item in lib.items() if _has_value(item, category, value))


def rename_option(lib: Library, category: str, old: str, new: str) -> int:
    """Replace ``old`` with ``new`` on every track.

    Renaming onto a value a track already has is a merge: duplicates collapse
    into the first occurrence, so order is preserved.
    """

    def mutate(item: Item) -> bool:
        values = _dedupe(read_item_values(item, category))
        index = find_case_insensitive(values, old)
        if index is None:
            return False
        values[index] = new
        return write_item_values(item, category, _dedupe(values))

    return _migrate(lib, mutate)


def remove_option(lib: Library, category: str, value: str) -> int:
    """Drop ``value`` from every track; the last value blanks or deletes the field."""

    def mutate(item: Item) -> bool:
        values = _dedupe(read_item_values(item, category))
        index = find_case_insensitive(values, value)
        if index is None:
            return False
        del values[index]
        return write_item_values(item, category, values)

    return _migrate(lib, mutate)


def rename_category(lib: Library, old: str, new: str) -> int:
    """Move every track's ``old`` values into ``new`` and clear ``old``.

    ``new`` is written in its own shape (so a string field can become a list
    field) and merged with anything the track already had there. A no-op
    (exact string equality only) when ``old`` and ``new`` are the same
    category, so confirming a rename without editing the name never clears
    the field it would otherwise merge into itself.
    """
    if old == new:
        return 0

    def mutate(item: Item) -> bool:
        moved = read_item_values(item, old)
        if not moved:
            return False
        write_item_values(item, new, _dedupe(read_item_values(item, new) + moved))
        write_item_values(item, old, [])
        return True

    return _migrate(lib, mutate)


def remove_category(lib: Library, name: str) -> int:
    """Clear ``name`` on every track that has a value for it."""
    return _migrate(lib, lambda item: write_item_values(item, name, []))
