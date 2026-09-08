"""Library-wide migrations for renamed and deleted options and categories."""

import uuid
from collections.abc import Generator
from pathlib import Path

import pytest
from beets.library import Item, Library

from beetsplug.quicktag.library_ops import (
    count_tracks,
    remove_category,
    remove_option,
    rename_category,
    rename_option,
)
from conftest import LIST_FIELD, needs_list_field


@pytest.fixture
def lib(tmp_path: Path) -> Generator[Library, None, None]:
    """An empty scratch library. ``store()`` never touches audio files."""
    library = Library(str(tmp_path / "library.db"))
    yield library
    library._close()


def add_track(lib: Library, **fields: object) -> int:
    """Add one track carrying ``fields`` and return its id."""
    item = Item(path=f"/music/{uuid.uuid4().hex}.mp3", title="t", artist="a", album="b")
    lib.add(item)
    for name, value in fields.items():
        item[name] = value
    item.store()
    return item.id


def value_of(lib: Library, item_id: int, field: str) -> object:
    return lib.get_item(item_id).get(field)


class TestCountTracks:
    def test_counts_whole_tokens_case_insensitively(self, lib: Library) -> None:
        add_track(lib, mood="House, Techno")
        add_track(lib, mood="Deep House")
        add_track(lib, mood="house")
        assert count_tracks(lib, "mood", "House") == 2

    def test_counts_tracks_with_any_value(self, lib: Library) -> None:
        add_track(lib, mood="a")
        add_track(lib, mood="b, c")
        add_track(lib)
        assert count_tracks(lib, "mood") == 2

    def test_zero_when_nothing_matches(self, lib: Library) -> None:
        add_track(lib, mood="a")
        assert count_tracks(lib, "mood", "zzz") == 0
        assert count_tracks(lib, "vibe") == 0

    def test_counts_fixed_scalar_field(self, lib: Library) -> None:
        add_track(lib, composer="X, Y")
        add_track(lib, composer="")
        assert count_tracks(lib, "composer", "Y") == 1
        assert count_tracks(lib, "composer") == 1

    @needs_list_field
    def test_counts_list_field_tokens(self, lib: Library) -> None:
        add_track(lib, genres=["House", "Deep House"])
        add_track(lib, genres=["Deep House"])
        assert count_tracks(lib, LIST_FIELD, "House") == 1
        assert count_tracks(lib, LIST_FIELD) == 2

    def test_counts_flexible_attribute_non_ascii_case_insensitively(
        self, lib: Library
    ) -> None:
        add_track(lib, mood="CAFÉ")
        assert count_tracks(lib, "mood", "café") == 1

    @needs_list_field
    def test_counts_list_field_non_ascii_case_insensitively(self, lib: Library) -> None:
        add_track(lib, genres=["CAFÉ"])
        assert count_tracks(lib, LIST_FIELD, "café") == 1

    def test_ignores_values_inherited_from_the_album(self, lib: Library) -> None:
        """An album-level attribute is not the track's own value."""
        item_id = add_track(lib)
        album = lib.add_album([lib.get_item(item_id)])
        album["mood"] = "happy"
        album.store(inherit=False)
        assert lib.get_item(item_id).get("mood") == "happy"
        assert count_tracks(lib, "mood", "happy") == 0
        assert count_tracks(lib, "mood") == 0


class TestRenameOption:
    def test_renames_whole_token_in_place(self, lib: Library) -> None:
        a = add_track(lib, mood="Hiphop, House")
        b = add_track(lib, mood="Deep Hiphop")
        assert rename_option(lib, "mood", "Hiphop", "Hip-Hop") == 1
        assert value_of(lib, a, "mood") == "Hip-Hop, House"
        assert value_of(lib, b, "mood") == "Deep Hiphop"

    def test_matches_case_insensitively(self, lib: Library) -> None:
        a = add_track(lib, mood="HIPHOP")
        rename_option(lib, "mood", "Hiphop", "Hip-Hop")
        assert value_of(lib, a, "mood") == "Hip-Hop"

    def test_merge_dedupes_keeping_first_position(self, lib: Library) -> None:
        a = add_track(lib, mood="Hiphop, House, Hip-Hop")
        rename_option(lib, "mood", "Hiphop", "Hip-Hop")
        assert value_of(lib, a, "mood") == "Hip-Hop, House"

    def test_returns_number_of_changed_tracks(self, lib: Library) -> None:
        add_track(lib, mood="Hiphop")
        add_track(lib, mood="Hiphop, x")
        add_track(lib, mood="other")
        assert rename_option(lib, "mood", "Hiphop", "Hip-Hop") == 2

    def test_fixed_scalar_field(self, lib: Library) -> None:
        a = add_track(lib, composer="Hiphop, House")
        rename_option(lib, "composer", "Hiphop", "Hip-Hop")
        assert value_of(lib, a, "composer") == "Hip-Hop, House"

    @needs_list_field
    def test_list_field_stays_a_list(self, lib: Library) -> None:
        a = add_track(lib, genres=["Hiphop", "House"])
        rename_option(lib, LIST_FIELD, "Hiphop", "Hip-Hop")
        assert lib.get_item(a)[LIST_FIELD] == ["Hip-Hop", "House"]

    def test_renames_flexible_attribute_non_ascii_case_insensitively(
        self, lib: Library
    ) -> None:
        a = add_track(lib, mood="CAFÉ")
        assert rename_option(lib, "mood", "café", "Cafe") == 1
        assert value_of(lib, a, "mood") == "Cafe"

    @needs_list_field
    def test_renames_list_field_non_ascii_case_insensitively(
        self, lib: Library
    ) -> None:
        a = add_track(lib, genres=["CAFÉ"])
        assert rename_option(lib, LIST_FIELD, "café", "Cafe") == 1
        assert lib.get_item(a)[LIST_FIELD] == ["Cafe"]

    def test_failure_rolls_back_every_track(
        self, lib: Library, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """beets commits a transaction even if its body raises; we must not."""
        a = add_track(lib, mood="Hiphop")
        b = add_track(lib, mood="Hiphop")
        original_store = Item.store
        stores: list[int] = []

        def flaky_store(self: Item, *args: object, **kwargs: object) -> None:
            stores.append(self.id)
            if len(stores) == 2:
                raise RuntimeError("disk on fire")
            original_store(self, *args, **kwargs)

        monkeypatch.setattr(Item, "store", flaky_store)
        with pytest.raises(RuntimeError, match="disk on fire"):
            rename_option(lib, "mood", "Hiphop", "Hip-Hop")
        monkeypatch.undo()
        assert value_of(lib, a, "mood") == "Hiphop"
        assert value_of(lib, b, "mood") == "Hiphop"

    def test_failure_before_the_first_store_keeps_its_own_error(
        self, lib: Library, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """sqlite opens the transaction lazily; a rollback before the first
        write must not replace the real error with "no transaction is active"."""
        a = add_track(lib, mood="Hiphop")

        def broken_store(self: Item, *args: object, **kwargs: object) -> None:
            raise RuntimeError("disk on fire")

        monkeypatch.setattr(Item, "store", broken_store)
        with pytest.raises(RuntimeError, match="disk on fire"):
            rename_option(lib, "mood", "Hiphop", "Hip-Hop")
        monkeypatch.undo()
        assert value_of(lib, a, "mood") == "Hiphop"

    def test_failure_leaves_an_enclosing_transaction_intact(
        self, lib: Library, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        a = add_track(lib, mood="Hiphop")
        b = add_track(lib, vibe="x")
        original_store = Item.store

        def flaky_store(self: Item, *args: object, **kwargs: object) -> None:
            if self.id == a:
                raise RuntimeError("disk on fire")
            original_store(self, *args, **kwargs)

        with lib.transaction():
            outer = lib.get_item(b)
            outer["vibe"] = "y"
            outer.store()
            monkeypatch.setattr(Item, "store", flaky_store)
            with pytest.raises(RuntimeError, match="disk on fire"):
                rename_option(lib, "mood", "Hiphop", "Hip-Hop")
            monkeypatch.undo()
        assert value_of(lib, a, "mood") == "Hiphop"
        assert value_of(lib, b, "vibe") == "y"

    def test_removes_stored_duplicates_of_the_renamed_token(self, lib: Library) -> None:
        a = add_track(lib, mood="Hiphop, HIPHOP, House")
        assert rename_option(lib, "mood", "hiphop", "Hip-Hop") == 1
        assert value_of(lib, a, "mood") == "Hip-Hop, House"

    def test_scans_the_library_inside_the_transaction(
        self, lib: Library, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A snapshot taken before the lock could overwrite a concurrent write."""
        add_track(lib, mood="Hiphop")
        original_items = Library.items
        in_transaction: list[bool] = []

        def recording_items(self: Library, *args: object) -> object:
            in_transaction.append(self._connection().in_transaction)
            return original_items(self, *args)

        monkeypatch.setattr(Library, "items", recording_items)
        rename_option(lib, "mood", "Hiphop", "Hip-Hop")
        assert in_transaction == [True]


class TestRemoveOption:
    def test_removes_token_and_keeps_the_rest(self, lib: Library) -> None:
        a = add_track(lib, mood="Hiphop, House")
        assert remove_option(lib, "mood", "Hiphop") == 1
        assert value_of(lib, a, "mood") == "House"

    def test_last_value_deletes_flexible_attribute(self, lib: Library) -> None:
        a = add_track(lib, mood="Hiphop")
        remove_option(lib, "mood", "hiphop")
        assert value_of(lib, a, "mood") is None
        assert "mood" not in lib.get_item(a)

    def test_last_value_blanks_fixed_field(self, lib: Library) -> None:
        a = add_track(lib, composer="Hiphop")
        remove_option(lib, "composer", "Hiphop")
        assert value_of(lib, a, "composer") == ""

    @needs_list_field
    def test_last_value_empties_list_field(self, lib: Library) -> None:
        a = add_track(lib, genres=["Hiphop"])
        remove_option(lib, LIST_FIELD, "Hiphop")
        assert lib.get_item(a)[LIST_FIELD] == []

    def test_leaves_similar_tokens_alone(self, lib: Library) -> None:
        a = add_track(lib, mood="Deep Hiphop")
        assert remove_option(lib, "mood", "Hiphop") == 0
        assert value_of(lib, a, "mood") == "Deep Hiphop"


class TestRenameCategory:
    def test_moves_values_and_deletes_old_flexible_attribute(
        self, lib: Library
    ) -> None:
        a = add_track(lib, mood="a, b")
        untouched = add_track(lib, vibe="x")
        assert rename_category(lib, "mood", "vibe") == 1
        assert value_of(lib, a, "vibe") == "a, b"
        assert "mood" not in lib.get_item(a)
        assert value_of(lib, untouched, "vibe") == "x"

    def test_merges_with_values_already_in_the_new_field(self, lib: Library) -> None:
        a = add_track(lib, mood="a, b", vibe="b, c")
        rename_category(lib, "mood", "vibe")
        assert value_of(lib, a, "vibe") == "b, c, a"

    def test_blanks_an_old_fixed_field(self, lib: Library) -> None:
        a = add_track(lib, composer="a")
        rename_category(lib, "composer", "mood")
        assert value_of(lib, a, "mood") == "a"
        assert value_of(lib, a, "composer") == ""

    @needs_list_field
    def test_string_to_list_field_changes_shape(self, lib: Library) -> None:
        a = add_track(lib, genre="House, Techno")
        rename_category(lib, "genre", LIST_FIELD)
        assert lib.get_item(a)[LIST_FIELD] == ["House", "Techno"]
        assert not lib.get_item(a).get("genre")

    def test_failure_rolls_back_every_track(
        self, lib: Library, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        a = add_track(lib, mood="Hiphop")
        b = add_track(lib, mood="House")
        original_store = Item.store
        stores: list[int] = []

        def flaky_store(self: Item, *args: object, **kwargs: object) -> None:
            stores.append(self.id)
            if len(stores) == 2:
                raise RuntimeError("disk on fire")
            original_store(self, *args, **kwargs)

        monkeypatch.setattr(Item, "store", flaky_store)
        with pytest.raises(RuntimeError, match="disk on fire"):
            rename_category(lib, "mood", "vibe")
        monkeypatch.undo()
        assert value_of(lib, a, "mood") == "Hiphop"
        assert value_of(lib, b, "mood") == "House"
        assert value_of(lib, a, "vibe") is None
        assert value_of(lib, b, "vibe") is None

    def test_counts_only_tracks_that_had_a_value(self, lib: Library) -> None:
        add_track(lib, mood="a")
        add_track(lib, vibe="x")
        add_track(lib)
        assert rename_category(lib, "mood", "vibe") == 1

    def test_same_name_is_a_no_op(self, lib: Library) -> None:
        a = add_track(lib, mood="a, b")
        assert rename_category(lib, "mood", "mood") == 0
        assert value_of(lib, a, "mood") == "a, b"


class TestRemoveCategory:
    def test_deletes_flexible_attribute_from_every_track(self, lib: Library) -> None:
        a = add_track(lib, mood="a")
        b = add_track(lib, mood="b, c")
        add_track(lib)
        assert remove_category(lib, "mood") == 2
        assert "mood" not in lib.get_item(a)
        assert "mood" not in lib.get_item(b)

    def test_blanks_fixed_field(self, lib: Library) -> None:
        a = add_track(lib, composer="a")
        remove_category(lib, "composer")
        assert value_of(lib, a, "composer") == ""

    @needs_list_field
    def test_empties_list_field(self, lib: Library) -> None:
        a = add_track(lib, genres=["a"])
        remove_category(lib, LIST_FIELD)
        assert lib.get_item(a)[LIST_FIELD] == []
