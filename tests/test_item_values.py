"""Reading and writing a category's values on a beets Item (§3.3 shapes)."""

import pytest
from beets.library import Item

from beetsplug.quicktag.definitions import CategoryDefinitions
from beetsplug.quicktag.item_values import (
    encode_values,
    read_item_values,
    split_value,
    write_item_values,
)

LIST_FIELD = "genres"
needs_list_field = pytest.mark.skipif(
    not CategoryDefinitions.is_list_field(LIST_FIELD),
    reason="installed beets has no list-valued 'genres' field",
)


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
