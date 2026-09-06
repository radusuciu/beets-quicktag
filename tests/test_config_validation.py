"""Unit tests for quicktag category configuration validation.

These are pure unit tests around `validate_categories` -- no Textual app,
no beets library fixtures needed.
"""

import pytest
from beets.ui import UserError

from beetsplug.quicktag.config import validate_categories


def test_happy_path_returns_validated_list() -> None:
    """A well-formed config is returned as a list of (name, options) pairs."""
    categories_config: dict[str, object] = {
        "mood": ["happy", "sad", "energetic", "calm"],
        "genre_custom": ["electronic", "ambient"],
    }

    result = validate_categories(categories_config)

    assert result == [
        ("mood", ["happy", "sad", "energetic", "calm"]),
        ("genre_custom", ["electronic", "ambient"]),
    ]


def test_options_tuple_is_converted_to_list() -> None:
    """Options given as a tuple are accepted and normalized to a list."""
    categories_config: dict[str, object] = {"mood": ("happy", "sad")}

    result = validate_categories(categories_config)

    assert result == [("mood", ["happy", "sad"])]


@pytest.mark.parametrize(
    "name",
    ["my mood", "genre.custom", "1genre", "mood!", "genre custom"],
)
def test_rejects_non_identifier_category_name(name: str) -> None:
    """Category names with spaces, dots, or a leading digit are rejected."""
    categories_config: dict[str, object] = {name: ["a", "b"]}

    with pytest.raises(UserError, match="letters, digits, underscores"):
        validate_categories(categories_config)


@pytest.mark.parametrize("name", ["year", "bpm", "length", "id", "path"])
def test_rejects_non_string_fixed_field_collision(name: str) -> None:
    """Names that collide with a non-string fixed beets Item field fail."""
    categories_config: dict[str, object] = {name: ["a", "b"]}

    with pytest.raises(UserError, match=f"'{name}'"):
        validate_categories(categories_config)


def test_rejects_comments_category_name() -> None:
    """'comments' is reserved for the plugin's built-in comments field."""
    categories_config: dict[str, object] = {"comments": ["a", "b"]}

    with pytest.raises(UserError, match="reserved"):
        validate_categories(categories_config)


def test_accepts_string_typed_fixed_field_name() -> None:
    """A category name matching a string-typed fixed field is accepted.

    Note: `genre` (singular) is not actually a fixed `Item` field in beets
    2.7.1 -- only the plural, non-string `genres` (DelimitedString) is.
    `album` is used here as a genuine string-typed fixed field
    (`beets.dbcore.types.String`) to exercise that branch.
    """
    categories_config: dict[str, object] = {"album": ["rock", "jazz"]}

    result = validate_categories(categories_config)

    assert result == [("album", ["rock", "jazz"])]


def test_accepts_genre_name_not_a_fixed_field() -> None:
    """'genre' is not a fixed Item field, so it is accepted as a category."""
    categories_config: dict[str, object] = {"genre": ["rock", "jazz"]}

    result = validate_categories(categories_config)

    assert result == [("genre", ["rock", "jazz"])]


def test_rejects_bare_string_options() -> None:
    """A bare string like 'happy' (the common mistake) is rejected."""
    categories_config: dict[str, object] = {"mood": "happy"}

    with pytest.raises(UserError, match="bare string"):
        validate_categories(categories_config)


def test_rejects_empty_options_list() -> None:
    """An empty options list is rejected."""
    categories_config: dict[str, object] = {"mood": []}

    with pytest.raises(UserError, match="non-empty"):
        validate_categories(categories_config)


def test_rejects_non_list_options() -> None:
    """Options that are neither a string, list, nor tuple are rejected."""
    categories_config: dict[str, object] = {"mood": 42}

    with pytest.raises(UserError, match="non-empty"):
        validate_categories(categories_config)


def test_rejects_options_with_empty_string_entry() -> None:
    """An options list containing an empty string entry is rejected."""
    categories_config: dict[str, object] = {"mood": ["happy", ""]}

    with pytest.raises(UserError, match="non-empty strings"):
        validate_categories(categories_config)


def test_rejects_duplicate_options() -> None:
    """Duplicate entries in an options list are rejected."""
    categories_config: dict[str, object] = {"mood": ["happy", "sad", "happy"]}

    with pytest.raises(UserError, match="duplicates"):
        validate_categories(categories_config)
