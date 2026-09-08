"""Read and write one category's values on a beets ``Item``.

Three storage shapes exist:

* flexible attribute: ``", "``-joined string; "empty" means the attribute
  is deleted;
* fixed scalar field (e.g. ``comments``): ``", "``-joined string; "empty"
  is ``""``;
* fixed list-valued field (e.g. ``genres``): a Python ``list[str]``;
  "empty" is ``[]``.

Nothing here calls ``item.store()``; callers decide when to persist.
"""

from __future__ import annotations

from beets.library import Item

from .definitions import CategoryDefinitions

SEPARATOR = ", "


def split_value(raw: object) -> list[str]:
    """Normalize any stored shape to a list of trimmed, non-empty strings."""
    if raw is None:
        return []
    if isinstance(raw, list | tuple):
        return [str(part).strip() for part in raw if str(part).strip()]
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", "ignore")
    return [part.strip() for part in str(raw).split(",") if part.strip()]


def read_item_values(item: Item, category: str) -> list[str]:
    """The values currently stored for ``category`` on ``item`` itself.

    ``Item.get`` falls back to the album by default; an album-level flexible
    attribute is not the track's value (and cannot be deleted from the track),
    so the fallback is skipped.
    """
    return split_value(item.get(category, None, with_album=False))


def encode_values(category: str, values: list[str]) -> str | list[str] | None:
    """Encode ``values`` for ``category``; ``None`` means delete the field."""
    if CategoryDefinitions.is_list_field(category):
        return list(values)
    if CategoryDefinitions.is_fixed_field(category):
        return SEPARATOR.join(values)
    return SEPARATOR.join(values) if values else None


def write_item_values(item: Item, category: str, values: list[str]) -> bool:
    """Store ``values`` on ``item`` in the right shape.

    Returns ``True`` when the item was modified. Existing and new values are
    compared as case-folded sets of tokens, so re-saving the same selection
    (including an empty one on an unset fixed field, or one that differs only
    by case) is a no-op and the stored spelling is kept until the selection
    changes.
    """
    stored = sorted(value.casefold() for value in read_item_values(item, category))
    if stored == sorted(value.casefold() for value in values):
        return False
    encoded = encode_values(category, values)
    if encoded is None:
        if category in item.keys(with_album=False):
            del item[category]
    else:
        item[category] = encoded
    return True
