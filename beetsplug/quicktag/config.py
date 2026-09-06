"""Validation for the quicktag plugin's ``categories`` configuration.

Category names become Textual widget IDs (``selection-<name>``) and are also
used to look up flexible/fixed attributes on beets ``Item`` objects, so a
badly formed config can crash the TUI well after startup with a confusing
traceback. :func:`validate_categories` checks the raw config mapping up
front and raises :class:`beets.ui.UserError` with a specific, actionable
message instead.
"""

import re

from beets import ui
from beets.dbcore.types import String
from beets.library import Item

# Textual widget IDs must match this pattern; category names are used
# directly as the suffix of a widget ID (``selection-<name>``).
_NAME_PATTERN = re.compile(r"^[A-Za-z_-][A-Za-z0-9_-]*$")

# Reserved: the plugin uses the "comments" field for free-text comments,
# so it cannot also be used as a quicktag category.
_RESERVED_NAMES = {"comments"}


def validate_categories(
    categories_config: dict[str, object],
) -> list[tuple[str, list[str]]]:
    """Validate the ``quicktag.categories`` config mapping.

    Returns the validated ``(name, options)`` pairs in the same shape
    ``QuickTagApp`` expects. Raises ``beets.ui.UserError`` naming the
    offending category and explaining what is wrong when:

    1. a category name is not identifier-safe
       (``^[A-Za-z_-][A-Za-z0-9_-]*$``);
    2. a category name is "comments", or collides with a fixed beets
       ``Item`` field that is not a string type (e.g. ``year``, ``bpm``,
       ``length``, ``id``, ``path``);
    3. a category's options are not a non-empty list/tuple of non-empty
       strings (a bare string such as ``happy`` is the common mistake);
    4. a category's options contain duplicates.
    """
    fixed_fields = Item._fields
    validated: list[tuple[str, list[str]]] = []

    for name, options in categories_config.items():
        if not _NAME_PATTERN.match(name):
            raise ui.UserError(
                f"quicktag: invalid category name '{name}': category names "
                "must contain only letters, digits, underscores and hyphens "
                "and not start with a digit."
            )

        if name in _RESERVED_NAMES:
            raise ui.UserError(
                f"quicktag: category name '{name}' is reserved for the "
                "built-in comments field; choose a different category name."
            )

        field_type = fixed_fields.get(name)
        if field_type is not None and not isinstance(field_type, String):
            raise ui.UserError(
                f"quicktag: category name '{name}' collides with the "
                f"built-in beets field '{name}' ({type(field_type).__name__}), "
                "which is not a text field; choose a different category name."
            )

        if isinstance(options, str):
            raise ui.UserError(
                f"quicktag: category '{name}' options must be a list of "
                f"strings, e.g. '{name}: [{options}, other_option]', not a "
                f"bare string '{options}'."
            )

        if not isinstance(options, list | tuple) or not options:
            raise ui.UserError(
                f"quicktag: category '{name}' options must be a non-empty "
                "list of strings."
            )

        if not all(isinstance(option, str) and option for option in options):
            raise ui.UserError(
                f"quicktag: category '{name}' options must all be non-empty strings."
            )

        options_list = list(options)
        if len(set(options_list)) != len(options_list):
            raise ui.UserError(
                f"quicktag: category '{name}' options contain duplicates."
            )

        validated.append((name, options_list))

    return validated
