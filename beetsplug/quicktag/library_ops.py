"""Library-wide migrations that keep tracks in step with the definitions.

No Textual here. Every mutating function runs inside one ``lib.transaction()``
and calls ``item.store()`` only (never ``item.write()``). An exception rolls
the whole migration back, so the library is never left half-migrated.

Tokens are compared whole and case-insensitively, the same way the app maps a
track's ``HAPPY`` onto the option ``happy``; ``House`` never matches
``Deep House``.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager

from beets.dbcore.query import SubstringQuery
from beets.library import Item, Library

from .definitions import CategoryDefinitions
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


def _items_with_value(lib: Library, category: str, value: str) -> list[Item]:
    """Tracks whose ``category`` holds ``value`` as a whole token.

    The substring query narrows the scan (in SQL for fixed columns, in Python
    for flexible attributes, which have no column); the token check then
    rejects partial matches.
    """
    query = SubstringQuery(
        category, value, fast=CategoryDefinitions.is_fixed_field(category)
    )
    return [
        item
        for item in lib.items(query)
        if any(_same(token, value) for token in read_item_values(item, category))
    ]


def _items_with_any_value(lib: Library, category: str) -> list[Item]:
    return [item for item in lib.items() if read_item_values(item, category)]


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
    items: list[Item],
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
        return len(_items_with_any_value(lib, category))
    return len(_items_with_value(lib, category, value))


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
    field) and merged with anything the track already had there.
    """
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
