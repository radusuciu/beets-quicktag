"""Unit tests for the CategoryDefinitions model. No Textual, no beets library."""

import pytest
from beets.library import Item

from beetsplug.quicktag.definitions import CategoryDefinitions

# Fixed list-valued fields other than ``genres`` in the installed beets.
OTHER_LIST_FIELDS = sorted(
    name
    for name in Item._fields
    if CategoryDefinitions.is_list_field(name) and name != "genres"
)


class TestStructure:
    def test_empty_by_default(self) -> None:
        defs = CategoryDefinitions()
        assert defs.categories == []

    def test_add_category_preserves_insertion_order(self) -> None:
        defs = CategoryDefinitions()
        defs.add_category("mood")
        defs.add_category("vibe")
        assert defs.categories == ["mood", "vibe"]
        assert defs.options("mood") == []

    def test_add_option_preserves_insertion_order(self) -> None:
        defs = CategoryDefinitions()
        defs.add_category("mood")
        defs.add_option("mood", "happy")
        defs.add_option("mood", "sad")
        assert defs.options("mood") == ["happy", "sad"]

    def test_options_returns_a_copy(self) -> None:
        defs = CategoryDefinitions()
        defs.add_category("mood")
        defs.add_option("mood", "happy")
        defs.options("mood").append("mutated")
        assert defs.options("mood") == ["happy"]

    def test_options_of_unknown_category_raises(self) -> None:
        defs = CategoryDefinitions()
        with pytest.raises(ValueError, match="No category named 'nope'"):
            defs.options("nope")


class TestCategoryNameRules:
    @pytest.mark.parametrize(
        "name", ["my mood", "genre.custom", "1genre", "mood!", "", "   "]
    )
    def test_rejects_bad_pattern(self, name: str) -> None:
        defs = CategoryDefinitions()
        with pytest.raises(ValueError, match="letters, digits, underscores"):
            defs.add_category(name)

    def test_trims_surrounding_whitespace(self) -> None:
        defs = CategoryDefinitions()
        assert defs.add_category("  mood ") == "mood"
        assert defs.categories == ["mood"]

    def test_rejects_reserved_comments(self) -> None:
        defs = CategoryDefinitions()
        with pytest.raises(ValueError, match="reserved"):
            defs.add_category("comments")

    def test_rejects_case_insensitive_duplicate(self) -> None:
        defs = CategoryDefinitions()
        defs.add_category("Mood")
        with pytest.raises(ValueError, match="already exists"):
            defs.add_category("mood")

    @pytest.mark.parametrize("name", ["year", "bpm", "album", "title", "path"])
    def test_interactive_add_refuses_any_fixed_field(self, name: str) -> None:
        """Typing a built-in field name in the TUI is refused."""
        defs = CategoryDefinitions()
        with pytest.raises(ValueError, match="built-in beets field"):
            defs.add_category(name)

    def test_interactive_add_allows_list_valued_fixed_field(self) -> None:
        """`genres` is list-valued in the installed beets and is allowed."""
        defs = CategoryDefinitions()
        if not CategoryDefinitions.is_list_field("genres"):
            pytest.skip("installed beets has no list-valued 'genres' field")
        assert defs.add_category("genres") == "genres"

    @pytest.mark.parametrize("name", OTHER_LIST_FIELDS)
    def test_interactive_add_refuses_other_list_valued_fields(self, name: str) -> None:
        """Only `genres` stands alone; the others are paired with companion
        fields (ids, sort names) that beets keeps in step."""
        defs = CategoryDefinitions()
        with pytest.raises(ValueError, match="built-in beets field"):
            defs.add_category(name)

    @pytest.mark.parametrize("name", ["filesize", "singleton"])
    def test_interactive_add_refuses_computed_field(self, name: str) -> None:
        defs = CategoryDefinitions()
        with pytest.raises(ValueError, match="computed"):
            defs.add_category(name)


class TestOptionRules:
    @pytest.fixture
    def defs(self) -> CategoryDefinitions:
        d = CategoryDefinitions()
        d.add_category("mood")
        d.add_option("mood", "happy")
        return d

    def test_trims_value(self, defs: CategoryDefinitions) -> None:
        assert defs.add_option("mood", "  sad ") == "sad"
        assert defs.options("mood") == ["happy", "sad"]

    @pytest.mark.parametrize("value", ["", "   "])
    def test_rejects_empty(self, defs: CategoryDefinitions, value: str) -> None:
        with pytest.raises(ValueError, match="cannot be empty"):
            defs.add_option("mood", value)

    def test_rejects_comma(self, defs: CategoryDefinitions) -> None:
        with pytest.raises(ValueError, match="cannot contain a comma"):
            defs.add_option("mood", "hip, hop")

    def test_rejects_case_insensitive_duplicate(
        self, defs: CategoryDefinitions
    ) -> None:
        with pytest.raises(ValueError, match="already has 'happy'"):
            defs.add_option("mood", "HAPPY")

    def test_rejects_list_field_delimiter(self) -> None:
        """A lone ``Drum; Bass`` comes back from the database as two values."""
        if not CategoryDefinitions.is_list_field("genres"):
            pytest.skip("installed beets has no list-valued 'genres' field")
        defs = CategoryDefinitions()
        defs.add_category("genres")
        with pytest.raises(ValueError, match="cannot contain '; '"):
            defs.add_option("genres", "Drum; Bass")
        defs.add_category("mood")
        assert defs.add_option("mood", "Drum; Bass") == "Drum; Bass"

    def test_rejects_unknown_category(self, defs: CategoryDefinitions) -> None:
        with pytest.raises(ValueError, match="No category named 'nope'"):
            defs.add_option("nope", "x")


class TestFindOption:
    @pytest.fixture
    def defs(self) -> CategoryDefinitions:
        d = CategoryDefinitions()
        d.add_category("mood")
        d.add_option("mood", "happy")
        d.add_option("mood", "Jazzy")
        return d

    def test_finds_exact_value(self, defs: CategoryDefinitions) -> None:
        assert defs.find_option("mood", "happy") == "happy"

    @pytest.mark.parametrize("value", ["HAPPY", "Happy", "hApPy"])
    def test_finds_case_variant_and_returns_the_stored_spelling(
        self, defs: CategoryDefinitions, value: str
    ) -> None:
        assert defs.find_option("mood", value) == "happy"

    def test_keeps_the_stored_capitalization(self, defs: CategoryDefinitions) -> None:
        assert defs.find_option("mood", "jazzy") == "Jazzy"

    def test_ignores_surrounding_whitespace(self, defs: CategoryDefinitions) -> None:
        assert defs.find_option("mood", "  happy ") == "happy"

    def test_returns_none_for_unknown_value(self, defs: CategoryDefinitions) -> None:
        assert defs.find_option("mood", "calm") is None

    def test_unknown_category_raises(self, defs: CategoryDefinitions) -> None:
        with pytest.raises(ValueError, match="No category named 'nope'"):
            defs.find_option("nope", "happy")


class TestRenameAndRemove:
    @pytest.fixture
    def defs(self) -> CategoryDefinitions:
        d = CategoryDefinitions()
        d.add_category("mood")
        d.add_option("mood", "happy")
        d.add_option("mood", "sad")
        d.add_category("vibe")
        d.add_option("vibe", "afro")
        return d

    def test_rename_category_keeps_position_and_options(
        self, defs: CategoryDefinitions
    ) -> None:
        defs.rename_category("mood", "feeling")
        assert defs.categories == ["feeling", "vibe"]
        assert defs.options("feeling") == ["happy", "sad"]

    def test_rename_category_validates_new_name(
        self, defs: CategoryDefinitions
    ) -> None:
        with pytest.raises(ValueError, match="already exists"):
            defs.rename_category("mood", "VIBE")
        with pytest.raises(ValueError, match="letters, digits"):
            defs.rename_category("mood", "bad name")

    def test_rename_category_to_same_name_different_case_is_allowed(
        self, defs: CategoryDefinitions
    ) -> None:
        defs.rename_category("mood", "Mood")
        assert defs.categories == ["Mood", "vibe"]

    def test_remove_category(self, defs: CategoryDefinitions) -> None:
        defs.remove_category("mood")
        assert defs.categories == ["vibe"]

    def test_remove_unknown_category_raises(self, defs: CategoryDefinitions) -> None:
        with pytest.raises(ValueError, match="No category named 'nope'"):
            defs.remove_category("nope")

    def test_rename_option_keeps_position(self, defs: CategoryDefinitions) -> None:
        defs.rename_option("mood", "happy", "joyful")
        assert defs.options("mood") == ["joyful", "sad"]

    def test_rename_option_onto_existing_merges(
        self, defs: CategoryDefinitions
    ) -> None:
        """Merge: the old value disappears, the target keeps its position."""
        defs.rename_option("mood", "happy", "SAD")
        assert defs.options("mood") == ["sad"]

    def test_rename_option_validates_value(self, defs: CategoryDefinitions) -> None:
        with pytest.raises(ValueError, match="cannot contain a comma"):
            defs.rename_option("mood", "happy", "a,b")

    def test_rename_unknown_option_raises(self, defs: CategoryDefinitions) -> None:
        with pytest.raises(ValueError, match="has no option 'nope'"):
            defs.rename_option("mood", "nope", "x")

    def test_remove_option(self, defs: CategoryDefinitions) -> None:
        defs.remove_option("mood", "happy")
        assert defs.options("mood") == ["sad"]

    def test_remove_unknown_option_raises(self, defs: CategoryDefinitions) -> None:
        with pytest.raises(ValueError, match="has no option 'nope'"):
            defs.remove_option("mood", "nope")


class TestFromConfig:
    def test_round_trips_mapping_in_order(self) -> None:
        mapping: dict[object, object] = {
            "mood": ["happy", "sad"],
            "vibe": ("afro", "asian"),
            "fresh": [],
        }
        defs = CategoryDefinitions.from_config(mapping)
        assert defs.categories == ["mood", "vibe", "fresh"]
        assert defs.to_mapping() == {
            "mood": ["happy", "sad"],
            "vibe": ["afro", "asian"],
            "fresh": [],
        }

    def test_to_mapping_returns_copies(self) -> None:
        defs = CategoryDefinitions.from_config({"mood": ["happy"]})
        defs.to_mapping()["mood"].append("x")
        assert defs.options("mood") == ["happy"]

    @pytest.mark.parametrize("name", [2020, True])
    def test_rejects_non_string_category_name(self, name: object) -> None:
        """YAML parses ``2020:`` and ``yes:`` as int/bool keys."""
        with pytest.raises(ValueError, match="letters, digits, underscores"):
            CategoryDefinitions.from_config({name: ["a"]})

    def test_rejects_bad_pattern(self) -> None:
        with pytest.raises(ValueError, match="letters, digits, underscores"):
            CategoryDefinitions.from_config({"my mood": ["a"]})

    def test_rejects_reserved_comments(self) -> None:
        with pytest.raises(ValueError, match="reserved"):
            CategoryDefinitions.from_config({"comments": ["a"]})

    @pytest.mark.parametrize("name", ["year", "bpm", "length", "id", "path"])
    def test_rejects_non_text_fixed_field(self, name: str) -> None:
        with pytest.raises(ValueError, match=f"'{name}'"):
            CategoryDefinitions.from_config({name: ["a"]})

    def test_allows_text_fixed_field_with_warning(self) -> None:
        defs = CategoryDefinitions.from_config({"album": ["rock"]})
        assert defs.categories == ["album"]
        warnings = defs.fixed_field_warnings()
        assert len(warnings) == 1
        assert "album" in warnings[0]
        assert "built-in beets field" in warnings[0]
        # "may": beets only writes tags for fields it considers changed.
        assert "'beet write' may write them" in warnings[0]

    def test_allows_list_fixed_field_without_warning(self) -> None:
        if not CategoryDefinitions.is_list_field("genres"):
            pytest.skip("installed beets has no list-valued 'genres' field")
        defs = CategoryDefinitions.from_config({"genres": ["House"]})
        assert defs.fixed_field_warnings() == []

    @pytest.mark.parametrize("name", OTHER_LIST_FIELDS)
    def test_rejects_other_list_fixed_fields(self, name: str) -> None:
        with pytest.raises(ValueError, match=f"'{name}'"):
            CategoryDefinitions.from_config({name: ["a"]})

    @pytest.mark.parametrize("name", ["filesize", "singleton"])
    def test_rejects_computed_field(self, name: str) -> None:
        with pytest.raises(ValueError, match="computed"):
            CategoryDefinitions.from_config({name: ["a"]})

    def test_rejects_list_field_delimiter_in_option(self) -> None:
        if not CategoryDefinitions.is_list_field("genres"):
            pytest.skip("installed beets has no list-valued 'genres' field")
        with pytest.raises(ValueError, match="cannot contain '; '"):
            CategoryDefinitions.from_config({"genres": ["Drum; Bass"]})

    def test_bare_key_means_no_options(self) -> None:
        """``energy:`` with nothing after it loads as ``None``, and the app
        itself writes ``energy: []`` for the same state."""
        defs = CategoryDefinitions.from_config({"energy": None})
        assert defs.options("energy") == []

    def test_no_warning_for_flexible_attributes(self) -> None:
        defs = CategoryDefinitions.from_config({"mood": ["a"], "genre": ["b"]})
        assert defs.fixed_field_warnings() == []

    def test_rejects_bare_string_options(self) -> None:
        with pytest.raises(ValueError, match="bare string"):
            CategoryDefinitions.from_config({"mood": "happy"})

    def test_rejects_non_list_options(self) -> None:
        with pytest.raises(ValueError, match="must be a list of strings"):
            CategoryDefinitions.from_config({"mood": 42})

    def test_rejects_non_string_option_entry(self) -> None:
        with pytest.raises(ValueError, match="must all be strings"):
            CategoryDefinitions.from_config({"mood": ["happy", 3]})

    def test_rejects_empty_option_entry(self) -> None:
        with pytest.raises(ValueError, match="cannot be empty"):
            CategoryDefinitions.from_config({"mood": ["happy", ""]})

    def test_rejects_option_with_comma(self) -> None:
        with pytest.raises(ValueError, match="cannot contain a comma"):
            CategoryDefinitions.from_config({"mood": ["a, b"]})

    def test_rejects_duplicate_options_case_insensitively(self) -> None:
        with pytest.raises(ValueError, match="already has 'happy'"):
            CategoryDefinitions.from_config({"mood": ["happy", "Happy"]})

    def test_rejects_duplicate_category_case_insensitively(self) -> None:
        # dict keys are case-sensitive, so YAML can hand us both.
        with pytest.raises(ValueError, match="already exists"):
            CategoryDefinitions.from_config({"mood": ["a"], "Mood": ["b"]})
