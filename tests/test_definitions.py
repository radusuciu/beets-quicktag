"""Unit tests for the CategoryDefinitions model. No Textual, no beets library."""

import pytest

from beetsplug.quicktag.definitions import CategoryDefinitions


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
        """Typing a built-in field name in the TUI is refused (§3.1)."""
        defs = CategoryDefinitions()
        with pytest.raises(ValueError, match="built-in beets field"):
            defs.add_category(name)

    def test_interactive_add_allows_list_valued_fixed_field(self) -> None:
        """`genres` is list-valued in the installed beets and is allowed."""
        defs = CategoryDefinitions()
        if not CategoryDefinitions.is_list_field("genres"):
            pytest.skip("installed beets has no list-valued 'genres' field")
        assert defs.add_category("genres") == "genres"


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

    def test_rejects_unknown_category(self, defs: CategoryDefinitions) -> None:
        with pytest.raises(ValueError, match="No category named 'nope'"):
            defs.add_option("nope", "x")


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
