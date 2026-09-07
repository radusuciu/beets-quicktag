"""The in-memory model of quicktag categories and their options.

Category names become Textual widget ids (``selection-<name>``) and beets
field names; option values are joined with ``", "`` when stored as strings.
Every mutating method validates its input and raises :class:`ValueError`
with a message suitable for showing directly to the user.
"""

from __future__ import annotations

import re

from beets.dbcore.types import String
from beets.library import Item

# Textual widget ids must match this; category names are used as id suffixes.
NAME_PATTERN = re.compile(r"^[A-Za-z_-][A-Za-z0-9_-]*$")

# The plugin uses ``comments`` for the free-text comments field.
RESERVED_NAMES = frozenset({"comments"})


class CategoryDefinitions:
    """Ordered mapping of category name -> ordered list of option values."""

    def __init__(self) -> None:
        self._categories: dict[str, list[str]] = {}

    # ---- read access -----------------------------------------------------

    @property
    def categories(self) -> list[str]:
        """Category names in display order (a copy)."""
        return list(self._categories)

    def options(self, category: str) -> list[str]:
        """Option values of ``category`` in display order (a copy)."""
        return list(self._require_category(category))

    # ---- field kind detection (runtime, never hardcoded) ------------------

    @staticmethod
    def is_fixed_field(name: str) -> bool:
        """True when ``name`` is a fixed column on beets ``Item``."""
        return name in Item._fields

    @staticmethod
    def is_list_field(name: str) -> bool:
        """True when ``name`` is a fixed field whose Python value is a list."""
        field_type = Item._fields.get(name)
        return field_type is not None and field_type.model_type is list

    @staticmethod
    def is_text_field(name: str) -> bool:
        """True when ``name`` is a fixed field that stores a plain string."""
        field_type = Item._fields.get(name)
        return isinstance(field_type, String) and field_type.model_type is str

    # ---- category mutations -----------------------------------------------

    def add_category(self, name: str) -> str:
        """Append a new empty category. Returns the normalized name."""
        name = self._validate_new_name(name, current=None, loaded=False)
        self._categories[name] = []
        return name

    def rename_category(self, old: str, new: str) -> None:
        """Rename ``old`` to ``new`` keeping its position and options."""
        self._require_category(old)
        new = self._validate_new_name(new, current=old, loaded=False)
        self._categories = {
            (new if key == old else key): value
            for key, value in self._categories.items()
        }

    def remove_category(self, name: str) -> None:
        self._require_category(name)
        del self._categories[name]

    # ---- option mutations -------------------------------------------------

    def add_option(self, category: str, value: str) -> str:
        """Append ``value`` to ``category``. Returns the normalized value."""
        options = self._require_category(category)
        value = self._validate_option(category, value, options)
        options.append(value)
        return value

    def rename_option(self, category: str, old: str, new: str) -> None:
        """Rename ``old`` to ``new`` in place.

        Renaming onto an existing option (case-insensitively) is a merge: the
        old entry is dropped and the existing entry keeps its position.
        """
        options = self._require_category(category)
        index = self._require_option(category, options, old)
        new = self._validate_option_shape(new)
        target = self._find_case_insensitive(options, new)
        if target is not None and target != index:
            del options[index]
            return
        options[index] = new

    def remove_option(self, category: str, value: str) -> None:
        options = self._require_category(category)
        del options[self._require_option(category, options, value)]

    # ---- helpers ------------------------------------------------------------

    def _require_category(self, category: str) -> list[str]:
        try:
            return self._categories[category]
        except KeyError:
            raise ValueError(f"No category named '{category}'.") from None

    @staticmethod
    def _require_option(category: str, options: list[str], value: str) -> int:
        try:
            return options.index(value)
        except ValueError:
            raise ValueError(
                f"Category '{category}' has no option '{value}'."
            ) from None

    @staticmethod
    def _find_case_insensitive(values: list[str], needle: str) -> int | None:
        folded = needle.casefold()
        for index, value in enumerate(values):
            if value.casefold() == folded:
                return index
        return None

    def _validate_new_name(
        self, name: str, *, current: str | None, loaded: bool
    ) -> str:
        """Validate a category name being added (or renamed to).

        ``current`` is the category being renamed, so a case-only rename of
        itself is not a duplicate. ``loaded`` relaxes the fixed-field rule for
        names coming from the config or the definitions file (see
        ``from_config`` in the next task).
        """
        name = name.strip()
        if not NAME_PATTERN.fullmatch(name):
            raise ValueError(
                f"Invalid category name {name!r}: use only letters, digits, "
                "underscores and hyphens, and do not start with a digit."
            )
        if name in RESERVED_NAMES:
            raise ValueError(f"'{name}' is reserved for the built-in comments field.")
        existing = [key for key in self._categories if key != current]
        if self._find_case_insensitive(existing, name) is not None:
            raise ValueError(f"A category named '{name}' already exists.")
        if self.is_fixed_field(name) and not self.is_list_field(name):
            if not loaded:
                raise ValueError(
                    f"'{name}' is a built-in beets field; choose another name."
                )
            if not self.is_text_field(name):
                raise ValueError(
                    f"Category name '{name}' collides with the built-in beets "
                    f"field '{name}', which is not a text field; choose a "
                    "different category name."
                )
        return name

    @staticmethod
    def _validate_option_shape(value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("An option cannot be empty.")
        if "," in value:
            raise ValueError("An option cannot contain a comma.")
        return value

    def _validate_option(self, category: str, value: str, options: list[str]) -> str:
        value = self._validate_option_shape(value)
        existing_index = self._find_case_insensitive(options, value)
        if existing_index is not None:
            existing_value = options[existing_index]
            raise ValueError(f"Category '{category}' already has '{existing_value}'.")
        return value
