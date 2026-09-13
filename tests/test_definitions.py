"""Unit tests for the CategoryDefinitions model. No Textual, no beets library."""

from collections.abc import Callable, Mapping

import pytest
from beets.library import Item

from beetsplug.quicktag.definitions import (
    CategoryDefinitions,
    Scale,
    find_case_insensitive,
)

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
        exported = defs.to_mapping()["mood"]
        assert isinstance(exported, list)
        exported.append("x")
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


class TestPlanningAnEdit:
    """The app edits a copy first and swaps it in once the library agrees."""

    @pytest.fixture
    def defs(self) -> CategoryDefinitions:
        return CategoryDefinitions.from_config(
            {"mood": ["Hiphop", "Hip-Hop", "House"], "vibe": ["afro"]}
        )

    def test_copy_is_independent(self, defs: CategoryDefinitions) -> None:
        planned = defs.copy()
        planned.rename_option("mood", "House", "Techno")
        planned.remove_category("vibe")
        assert defs.options("mood") == ["Hiphop", "Hip-Hop", "House"]
        assert defs.categories == ["mood", "vibe"]
        assert planned.options("mood") == ["Hiphop", "Hip-Hop", "Techno"]
        assert planned.categories == ["mood"]

    def test_rename_option_returns_the_trimmed_value(
        self, defs: CategoryDefinitions
    ) -> None:
        assert defs.rename_option("mood", "House", "  Deep House ") == "Deep House"

    def test_rename_option_returns_the_same_value_for_a_no_op(
        self, defs: CategoryDefinitions
    ) -> None:
        assert defs.rename_option("mood", "House", "House") == "House"
        assert defs.options("mood") == ["Hiphop", "Hip-Hop", "House"]

    def test_rename_option_case_only_rename_of_itself_is_not_a_merge(
        self, defs: CategoryDefinitions
    ) -> None:
        assert defs.rename_option("mood", "House", "HOUSE") == "HOUSE"
        assert defs.options("mood") == ["Hiphop", "Hip-Hop", "HOUSE"]

    @pytest.mark.parametrize(
        ("old", "typed"), [("Hiphop", "hip-hop"), ("House", "HIPHOP")]
    )
    def test_merge_returns_the_stored_spelling(
        self, defs: CategoryDefinitions, old: str, typed: str
    ) -> None:
        """Whichever side of the dropped entry the target is on."""
        result = defs.rename_option("mood", old, typed)
        assert result in defs.options("mood")
        assert result.casefold() == typed.casefold()
        assert old not in defs.options("mood")

    def test_rename_category_returns_the_trimmed_name(
        self, defs: CategoryDefinitions
    ) -> None:
        assert defs.rename_category("mood", " feel ") == "feel"
        assert defs.categories == ["feel", "vibe"]

    def test_rename_category_refuses_a_fixed_text_field(
        self, defs: CategoryDefinitions
    ) -> None:
        with pytest.raises(ValueError, match="built-in beets field"):
            defs.rename_category("mood", "album")

    @pytest.mark.skipif(
        not CategoryDefinitions.is_list_field("genres"),
        reason="installed beets has no list-valued 'genres' field",
    )
    def test_rename_category_allows_the_supported_list_field(
        self, defs: CategoryDefinitions
    ) -> None:
        assert defs.rename_category("mood", "genres") == "genres"


class TestOwnsField:
    def test_flexible_attribute_is_owned(self) -> None:
        assert CategoryDefinitions.owns_field("mood") is True

    @pytest.mark.parametrize("name", ["album", "grouping", "albumartist"])
    def test_fixed_text_field_is_borrowed(self, name: str) -> None:
        assert CategoryDefinitions.owns_field(name) is False

    @pytest.mark.skipif(
        not CategoryDefinitions.is_list_field("genres"),
        reason="installed beets has no list-valued 'genres' field",
    )
    def test_supported_list_field_is_owned(self) -> None:
        assert CategoryDefinitions.owns_field("genres") is True


class TestFindCaseInsensitive:
    def test_returns_the_first_match_ignoring_case_and_whitespace(self) -> None:
        assert find_case_insensitive(["a", "B", "b"], " b ") == 1

    def test_returns_none_without_a_match(self) -> None:
        assert find_case_insensitive(["a"], "zzz") is None

    def test_folds_non_ascii(self) -> None:
        assert find_case_insensitive(["CAFÉ"], "café") == 0


class TestSortedOptions:
    """``sort_options=True`` keeps every option list sorted ignoring case.

    Category order is never touched: only the values inside each sort.
    """

    def test_off_by_default(self) -> None:
        defs = CategoryDefinitions.from_config({"mood": ["sad", "happy"]})
        assert defs.options("mood") == ["sad", "happy"]

    def test_from_config_sorts_options_but_not_categories(self) -> None:
        defs = CategoryDefinitions.from_config(
            {"vibe": ["Zen", "afro"], "mood": ["sad", "Happy", "calm"]},
            sort_options=True,
        )
        assert defs.categories == ["vibe", "mood"]
        assert defs.options("vibe") == ["afro", "Zen"]
        assert defs.options("mood") == ["calm", "Happy", "sad"]

    def test_add_option_inserts_in_sorted_position(self) -> None:
        defs = CategoryDefinitions(sort_options=True)
        defs.add_category("mood")
        defs.add_option("mood", "sad")
        defs.add_option("mood", "Happy")
        assert defs.add_option("mood", "  calm ") == "calm"
        assert defs.options("mood") == ["calm", "Happy", "sad"]

    def test_rename_option_moves_it_to_its_sorted_position(self) -> None:
        defs = CategoryDefinitions.from_config(
            {"mood": ["calm", "happy", "sad"]}, sort_options=True
        )
        assert defs.rename_option("mood", "calm", "Zen") == "Zen"
        assert defs.options("mood") == ["happy", "sad", "Zen"]

    def test_rename_option_merge_keeps_the_existing_spelling(self) -> None:
        defs = CategoryDefinitions.from_config(
            {"mood": ["calm", "Hip-Hop", "hiphop"]}, sort_options=True
        )
        assert defs.rename_option("mood", "hiphop", "hip-hop") == "Hip-Hop"
        assert defs.options("mood") == ["calm", "Hip-Hop"]

    def test_copy_keeps_sorting(self) -> None:
        defs = CategoryDefinitions.from_config({"mood": ["sad"]}, sort_options=True)
        clone = defs.copy()
        clone.add_option("mood", "happy")
        assert clone.options("mood") == ["happy", "sad"]

    def test_to_mapping_is_sorted(self) -> None:
        defs = CategoryDefinitions.from_config(
            {"mood": ["sad", "happy"]}, sort_options=True
        )
        assert defs.to_mapping() == {"mood": ["happy", "sad"]}


class TestScale:
    def test_parse_range(self) -> None:
        assert Scale.parse("1..5") == Scale(1, 5)
        assert Scale.parse(" 0 .. 10 ") == Scale(0, 10)

    @pytest.mark.parametrize("text", ["", "happy", "1-5", "1..", "1..5..9", "a..b"])
    def test_parse_returns_none_for_non_ranges(self, text: str) -> None:
        assert Scale.parse(text) is None

    @pytest.mark.parametrize("text", ["1..11", "5..5", "5..1", "0..0"])
    def test_parse_refuses_ranges_outside_the_limits(self, text: str) -> None:
        with pytest.raises(ValueError, match="0 <= low < high <= 10"):
            Scale.parse(text)

    def test_spec_and_steps(self) -> None:
        scale = Scale(1, 5)
        assert scale.spec() == "1..5"
        assert list(scale.steps()) == [1, 2, 3, 4, 5]

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("3", 3),
            (" 5 ", 5),
            ("1", 1),
            ("0", None),
            ("6", None),
            ("high", None),
            ("", None),
            (None, None),
            ("3.0", None),
        ],
    )
    def test_parse_value(self, text: str | None, expected: int | None) -> None:
        assert Scale(1, 5).parse_value(text) == expected


class TestScaleCategories:
    def test_from_config_accepts_a_range_string(self) -> None:
        defs = CategoryDefinitions.from_config(
            {"mood": ["happy"], "energy": "1..5", "vibe": ["dark"]}
        )
        assert defs.categories == ["mood", "energy", "vibe"]
        assert defs.scale("energy") == Scale(1, 5)
        assert defs.is_scale("energy")
        assert defs.scale("mood") is None
        assert not defs.is_scale("mood")

    def test_options_of_a_scale_is_an_error(self) -> None:
        defs = CategoryDefinitions.from_config({"energy": "1..5"})
        with pytest.raises(ValueError, match="'energy' is a scale"):
            defs.options("energy")

    @pytest.mark.parametrize(
        "call",
        [
            lambda d: d.add_option("energy", "x"),
            lambda d: d.rename_option("energy", "1", "2"),
            lambda d: d.remove_option("energy", "1"),
        ],
    )
    def test_option_edits_on_a_scale_are_errors(
        self, call: Callable[[CategoryDefinitions], object]
    ) -> None:
        defs = CategoryDefinitions.from_config({"energy": "1..5"})
        with pytest.raises(ValueError, match="'energy' is a scale"):
            call(defs)

    def test_other_strings_are_still_refused_and_show_both_shapes(self) -> None:
        with pytest.raises(
            ValueError, match=r"mood: \[happy, other_option\].*mood: 1\.\.5"
        ):
            CategoryDefinitions.from_config({"mood": "happy"})

    def test_range_outside_limits_names_the_category(self) -> None:
        with pytest.raises(
            ValueError, match="Category 'energy'.*0 <= low < high <= 10"
        ):
            CategoryDefinitions.from_config({"energy": "1..20"})

    @pytest.mark.parametrize("name", ["bpm", "album", "genres"])
    def test_scale_refuses_every_fixed_field(self, name: str) -> None:
        with pytest.raises(ValueError, match="built-in beets field"):
            CategoryDefinitions.from_config({name: "1..5"})

    def test_to_mapping_round_trips(self) -> None:
        mapping: Mapping[object, object] = {"mood": ["happy", "sad"], "energy": "1..5"}
        defs = CategoryDefinitions.from_config(mapping)
        assert defs.to_mapping() == mapping
        again = CategoryDefinitions.from_config({**defs.to_mapping()})
        assert again.scale("energy") == Scale(1, 5)

    def test_copy_keeps_the_scale_and_is_independent(self) -> None:
        defs = CategoryDefinitions.from_config({"energy": "1..5", "mood": ["a"]})
        clone = defs.copy()
        assert clone.scale("energy") == Scale(1, 5)
        clone.add_option("mood", "b")
        assert defs.options("mood") == ["a"]

    def test_rename_category_keeps_the_scale(self) -> None:
        defs = CategoryDefinitions.from_config({"energy": "1..5"})
        assert defs.rename_category("energy", "power") == "power"
        assert defs.categories == ["power"]
        assert defs.scale("power") == Scale(1, 5)

    def test_rename_scale_onto_a_list_field_is_refused(self) -> None:
        defs = CategoryDefinitions.from_config({"energy": "1..5"})
        with pytest.raises(ValueError, match="built-in beets field"):
            defs.rename_category("energy", "genres")

    def test_remove_category_drops_a_scale(self) -> None:
        defs = CategoryDefinitions.from_config({"energy": "1..5", "mood": ["a"]})
        defs.remove_category("energy")
        assert defs.categories == ["mood"]

    def test_sort_options_ignores_scales(self) -> None:
        defs = CategoryDefinitions.from_config(
            {"energy": "1..5", "mood": ["b", "a"]}, sort_options=True
        )
        assert defs.options("mood") == ["a", "b"]
        assert defs.scale("energy") == Scale(1, 5)

    def test_fixed_field_warnings_skip_scales(self) -> None:
        defs = CategoryDefinitions.from_config({"energy": "1..5", "album": ["x"]})
        assert len(defs.fixed_field_warnings()) == 1
