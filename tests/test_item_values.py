"""Reading and writing a category's values on a beets Item."""

from pathlib import Path

import pytest
from beets.library import Album, Item, Library

from beetsplug.quicktag.item_values import (
    encode_values,
    read_item_values,
    read_scale_value,
    split_value,
    write_item_values,
    write_scale_value,
)
from conftest import LIST_FIELD, item_id, needs_list_field, stored_item


class TestSplitValue:
    @pytest.mark.parametrize("raw", [None, "", [], b""])
    def test_empty_shapes(self, raw: object) -> None:
        assert split_value(raw) == []

    def test_string_is_split_and_trimmed(self) -> None:
        assert split_value("House, Techno ,Acid,,") == ["House", "Techno", "Acid"]

    def test_bytes_are_decoded(self) -> None:
        assert split_value(b"House, Techno") == ["House", "Techno"]

    def test_list_is_trimmed(self) -> None:
        assert split_value([" House ", "", "Techno"]) == ["House", "Techno"]


class TestEncodeValues:
    def test_flexible_joins_or_deletes(self) -> None:
        assert encode_values("mood", ["a", "b"]) == "a, b"
        assert encode_values("mood", []) is None

    def test_fixed_scalar_joins_or_blanks(self) -> None:
        assert encode_values("album", ["a", "b"]) == "a, b"
        assert encode_values("album", []) == ""

    @needs_list_field
    def test_list_field_keeps_list(self) -> None:
        assert encode_values(LIST_FIELD, ["a", "b"]) == ["a", "b"]
        assert encode_values(LIST_FIELD, []) == []


class TestWriteItemValues:
    def test_flexible_set_and_delete(self) -> None:
        item = Item()
        assert write_item_values(item, "mood", ["a", "b"]) is True
        assert item["mood"] == "a, b"
        assert read_item_values(item, "mood") == ["a", "b"]
        assert write_item_values(item, "mood", []) is True
        assert "mood" not in item

    def test_flexible_empty_on_unset_is_no_change(self) -> None:
        item = Item()
        assert write_item_values(item, "mood", []) is False
        assert "mood" not in item

    def test_fixed_scalar_empty_on_blank_is_no_change(self) -> None:
        """The latent bug: unset fixed fields read back as "" not None."""
        item = Item()
        assert item.get("album") == ""
        assert write_item_values(item, "album", []) is False

    def test_fixed_scalar_set_and_blank(self) -> None:
        item = Item()
        assert write_item_values(item, "album", ["a", "b"]) is True
        assert item.album == "a, b"
        assert write_item_values(item, "album", []) is True
        assert item.album == ""

    def test_same_values_different_case_is_no_change(self) -> None:
        """Browsing past a track must not rewrite its tags (and, for a media
        field, reset ``mtime``) just to normalise the spelling."""
        item = Item()
        item["mood"] = "ROCK"
        assert write_item_values(item, "mood", ["rock"]) is False
        assert item["mood"] == "ROCK"

    def test_same_values_different_order_is_no_change(self) -> None:
        item = Item()
        item["mood"] = "b, a"
        assert write_item_values(item, "mood", ["a", "b"]) is False
        assert item["mood"] == "b, a"

    def test_changed_values_are_written_in_given_order(self) -> None:
        item = Item()
        item["mood"] = "a"
        assert write_item_values(item, "mood", ["b", "a"]) is True
        assert item["mood"] == "b, a"

    @needs_list_field
    def test_list_field_set_and_blank(self) -> None:
        item = Item()
        assert write_item_values(item, LIST_FIELD, []) is False
        assert write_item_values(item, LIST_FIELD, ["House", "Acid"]) is True
        assert item[LIST_FIELD] == ["House", "Acid"]
        assert read_item_values(item, LIST_FIELD) == ["House", "Acid"]
        assert write_item_values(item, LIST_FIELD, []) is True
        assert item[LIST_FIELD] == []


class TestAlbumFallback:
    """``Item.get`` falls back to the album by default, but an album-level
    flexible attribute is not the track's value and cannot be deleted from
    the track."""

    @pytest.fixture
    def item_in_album(self, tmp_path: Path) -> Item:
        # Not ``:memory:``: opening a library runs the beets migrations, and
        # each one writes a backup named after the database. Windows has no
        # filename that can hold the colons.
        lib = Library(str(tmp_path / "library.db"))
        album = Album(lib, album="A")
        album.add(lib)
        item = Item(title="t", album="A", path=b"/t.mp3")
        item.add(lib)
        item.album_id = album.id
        item.store()
        album["mood"] = "dark"
        # ``inherit=True`` (the default) would copy the value onto the track;
        # the case under test is an album value the track only falls back to.
        album.store(inherit=False)
        return stored_item(lib, item_id(item))

    def test_album_value_is_not_read(self, item_in_album: Item) -> None:
        assert item_in_album.get("mood") == "dark"
        assert read_item_values(item_in_album, "mood") == []

    def test_empty_write_over_album_value_is_no_change(
        self, item_in_album: Item
    ) -> None:
        assert write_item_values(item_in_album, "mood", []) is False

    def test_own_value_is_read_and_deleted(self, item_in_album: Item) -> None:
        item_in_album["mood"] = "light"
        assert read_item_values(item_in_album, "mood") == ["light"]
        assert write_item_values(item_in_album, "mood", []) is True
        assert item_in_album.get("mood", with_album=False) is None


class TestScaleValues:
    def test_unset_reads_as_none(self, temp_beets_library: Library) -> None:
        item = next(iter(temp_beets_library.items()))
        assert read_scale_value(item, "energy") is None

    def test_write_then_read(self, temp_beets_library: Library) -> None:
        item = next(iter(temp_beets_library.items()))
        assert write_scale_value(item, "energy", 4) is True
        item.store()
        stored = stored_item(temp_beets_library, item_id(item))
        assert stored.get("energy") == "4"
        assert read_scale_value(stored, "energy") == "4"

    def test_same_value_is_a_no_op(self, temp_beets_library: Library) -> None:
        item = next(iter(temp_beets_library.items()))
        item["energy"] = "4"
        assert write_scale_value(item, "energy", 4) is False

    def test_none_deletes_the_attribute(self, temp_beets_library: Library) -> None:
        item = next(iter(temp_beets_library.items()))
        item["energy"] = "4"
        item.store()
        assert write_scale_value(item, "energy", None) is True
        item.store()
        stored = stored_item(temp_beets_library, item_id(item))
        assert "energy" not in stored.keys(with_album=False)

    def test_none_on_unset_is_a_no_op(self, temp_beets_library: Library) -> None:
        item = next(iter(temp_beets_library.items()))
        assert write_scale_value(item, "energy", None) is False

    def test_album_value_is_not_the_tracks(self, temp_beets_library: Library) -> None:
        item = next(iter(temp_beets_library.items()))
        album = temp_beets_library.add_album([item])
        album["energy"] = "5"
        album.store(inherit=False)
        stored = stored_item(temp_beets_library, item_id(item))
        assert read_scale_value(stored, "energy") is None

    def test_blank_and_bytes(self, temp_beets_library: Library) -> None:
        item = next(iter(temp_beets_library.items()))
        item["energy"] = "  "
        assert read_scale_value(item, "energy") is None
        item["energy"] = b" 3 "
        assert read_scale_value(item, "energy") == "3"
