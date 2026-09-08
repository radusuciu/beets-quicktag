"""Library-wide migrations that keep tracks in step with the definitions.

No Textual here. Every mutating function runs inside one ``lib.transaction()``
and calls ``item.store()`` only (never ``item.write()``). An exception rolls
the whole migration back, so the library is never left half-migrated.

Tokens are compared whole and case-insensitively, the same way the app maps a
track's ``HAPPY`` onto the option ``happy``; ``House`` never matches
``Deep House``.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager

from beets.library import Item, Library

from .item_values import read_item_values, write_item_values


def _same(a: str, b: str) -> bool:
    return a.casefold() == b.casefold()


def _dedupe(values: list[str]) -> list[str]:
    """Drop case-insensitive duplicates, keeping the first spelling and order."""
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.casefold()
        if key not in seen:
            seen.add(key)
            result.append(value)
    return result


def _items_with_value(lib: Library, category: str, value: str) -> Iterator[Item]:
    """Tracks whose ``category`` holds ``value`` as a whole token.

    Filtered in Python (like ``_items_with_any_value``) so the comparison is
    exactly ``_same``'s casefold, whole-token match. A SQL/beets-query
    prefilter would narrow the scan on a different, ASCII-only notion of
    case-insensitivity and could reject rows ``_same`` would accept.

    A generator, so counting the matches never materialises them; the
    migrations consume it inside their transaction.
    """
    return (
        item
        for item in lib.items()
        if any(_same(token, value) for token in read_item_values(item, category))
    )


def _items_with_any_value(lib: Library, category: str) -> Iterator[Item]:
    return (item for item in lib.items() if read_item_values(item, category))


@contextmanager
def _migration(lib: Library) -> Iterator[None]:
    """A root transaction that is rolled back if the body raises.

    beets commits a transaction even when its body raised, so the rollback
    has to be explicit.
    """
    with lib.transaction() as tx:
        try:
            yield
        except BaseException:
            tx.mutate("ROLLBACK")
            raise


def _rewrite(
    lib: Library,
    items: Iterable[Item],
    category: str,
    rewrite: Callable[[list[str]], list[str]],
) -> int:
    """Store ``rewrite(current values)`` on each item; return how many changed."""
    changed = 0
    with _migration(lib):
        for item in items:
            values = rewrite(read_item_values(item, category))
            if write_item_values(item, category, values):
                item.store()
                changed += 1
    return changed


def count_tracks(lib: Library, category: str, value: str | None = None) -> int:
    """Tracks carrying ``value`` in ``category``, or any value when ``None``."""
    if value is None:
        return sum(1 for _ in _items_with_any_value(lib, category))
    return sum(1 for _ in _items_with_value(lib, category, value))


def rename_option(lib: Library, category: str, old: str, new: str) -> int:
    """Replace ``old`` with ``new`` on every track.

    Renaming onto a value a track already has is a merge: duplicates collapse
    into the first occurrence, so order is preserved.
    """
    return _rewrite(
        lib,
        _items_with_value(lib, category, old),
        category,
        lambda values: _dedupe([new if _same(v, old) else v for v in values]),
    )


def remove_option(lib: Library, category: str, value: str) -> int:
    """Drop ``value`` from every track; the last value blanks or deletes the field."""
    return _rewrite(
        lib,
        _items_with_value(lib, category, value),
        category,
        lambda values: [v for v in values if not _same(v, value)],
    )


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
    changed = 0
    with _migration(lib):
        for item in _items_with_any_value(lib, old):
            merged = _dedupe(read_item_values(item, new) + read_item_values(item, old))
            write_item_values(item, new, merged)
            write_item_values(item, old, [])
            item.store()
            changed += 1
    return changed


def remove_category(lib: Library, name: str) -> int:
    """Clear ``name`` on every track that has a value for it."""
    return _rewrite(lib, _items_with_any_value(lib, name), name, lambda values: [])
