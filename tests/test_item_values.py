"""Reading and writing a category's values on a beets Item."""

import pytest
from beets.library import Album, Item, Library

from beetsplug.quicktag.item_values import (
    encode_values,
    read_item_values,
    split_value,
    write_item_values,
)
from conftest import LIST_FIELD, needs_list_field


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
    def item_in_album(self) -> Item:
        lib = Library(":memory:")
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
        return lib.get_item(item.id)

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
