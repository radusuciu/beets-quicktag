"""Adding categories and options from the TUI, and the value shapes they use.

Every test builds the app against the scratch library from ``conftest.py``.
"""

from pathlib import Path

import pytest
from beets.library import Library

from beetsplug.quicktag.app import QuickTagApp
from beetsplug.quicktag.definitions import CategoryDefinitions
from beetsplug.quicktag.definitions_file import read_definitions_file
from beetsplug.quicktag.widgets.custom_selection_list import CustomSelectionList

LIST_FIELD = "genres"
needs_list_field = pytest.mark.skipif(
    not CategoryDefinitions.is_list_field(LIST_FIELD),
    reason="installed beets has no list-valued 'genres' field",
)


def make_app(
    lib: Library,
    mapping: dict[str, list[str]],
    definitions_path: Path | None = None,
) -> QuickTagApp:
    return QuickTagApp(
        lib=lib,
        items=list(lib.items()),
        definitions=CategoryDefinitions.from_config(mapping),
        autoplay_at_launch_enabled=False,
        autoplay_on_track_change_enabled=False,
        autonext_at_track_end_enabled=False,
        autosave_on_quit_enabled=False,
        keep_playing_on_track_change_if_playing_enabled=False,
        definitions_path=definitions_path,
    )


class TestValueBasedSelections:
    @pytest.mark.asyncio
    async def test_selected_returns_option_strings(
        self, temp_beets_library: Library
    ) -> None:
        app = make_app(temp_beets_library, {"mood": ["happy", "sad"]})
        async with app.run_test():
            lst = app.query_one("#selection-mood", CustomSelectionList)
            lst.select("sad")
            assert lst.selected == ["sad"]

    @pytest.mark.asyncio
    async def test_save_writes_values_in_definition_order(
        self, temp_beets_library: Library
    ) -> None:
        app = make_app(temp_beets_library, {"mood": ["happy", "sad", "calm"]})
        async with app.run_test():
            lst = app.query_one("#selection-mood", CustomSelectionList)
            lst.select("calm")
            lst.select("happy")
            await app._save_current_item_tags()
        item = temp_beets_library.get_item(app.item.id)
        assert item.get("mood") == "happy, calm"

    @pytest.mark.asyncio
    async def test_load_selects_stored_values(
        self, temp_beets_library: Library
    ) -> None:
        item = next(iter(temp_beets_library.items()))
        item["mood"] = "sad, calm"
        item.store()
        app = make_app(temp_beets_library, {"mood": ["happy", "sad", "calm"]})
        async with app.run_test():
            lst = app.query_one("#selection-mood", CustomSelectionList)
            assert sorted(lst.selected) == ["calm", "sad"]

    @pytest.mark.asyncio
    async def test_save_with_nothing_selected_does_not_store(
        self, temp_beets_library: Library, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An unset fixed text field reads back as ""; that is not a change."""
        app = make_app(temp_beets_library, {"composer": ["a", "b"]})
        stores: list[str] = []
        async with app.run_test():
            assert (
                app.query_one("#selection-composer", CustomSelectionList).selected == []
            )
            monkeypatch.setattr(
                app.item, "store", lambda *a, **k: stores.append("store")
            )
            await app._save_current_item_tags()
        assert stores == []

    @needs_list_field
    @pytest.mark.asyncio
    async def test_list_field_round_trip(self, temp_beets_library: Library) -> None:
        app = make_app(temp_beets_library, {LIST_FIELD: ["House", "Acid"]})
        async with app.run_test():
            lst = app.query_one(f"#selection-{LIST_FIELD}", CustomSelectionList)
            lst.select("Acid")
            await app._save_current_item_tags()
            item_id = app.item.id
        item = temp_beets_library.get_item(item_id)
        assert item[LIST_FIELD] == ["Acid"]

        app2 = make_app(temp_beets_library, {LIST_FIELD: ["House", "Acid"]})
        async with app2.run_test():
            lst2 = app2.query_one(f"#selection-{LIST_FIELD}", CustomSelectionList)
            assert lst2.selected == ["Acid"]


class TestAdoptingUnknownValues:
    @pytest.mark.asyncio
    async def test_unknown_stored_value_is_adopted_selected_and_persisted(
        self, temp_beets_library: Library, tmp_path: Path
    ) -> None:
        item = next(iter(temp_beets_library.items()))
        item["mood"] = "happy, Jazzy"
        item.store()
        path = tmp_path / "quicktag_categories.yaml"
        app = make_app(temp_beets_library, {"mood": ["happy", "sad"]}, path)
        async with app.run_test():
            lst = app.query_one("#selection-mood", CustomSelectionList)
            prompts = [
                str(lst.get_option_at_index(i).prompt) for i in range(lst.option_count)
            ]
            assert prompts == ["happy", "sad", "Jazzy"]
            assert sorted(lst.selected) == ["Jazzy", "happy"]
            assert app.definitions.options("mood") == ["happy", "sad", "Jazzy"]
        assert read_definitions_file(path).options("mood") == [
            "happy",
            "sad",
            "Jazzy",
        ]

    @pytest.mark.asyncio
    async def test_adopted_value_survives_save(
        self, temp_beets_library: Library
    ) -> None:
        """Closes the silent data-loss bug: the value is no longer dropped."""
        item = next(iter(temp_beets_library.items()))
        item["mood"] = "Jazzy"
        item.store()
        app = make_app(temp_beets_library, {"mood": ["happy"]})
        async with app.run_test():
            await app._save_current_item_tags()
        assert temp_beets_library.get_item(item.id).get("mood") == "Jazzy"

    @pytest.mark.asyncio
    async def test_case_variant_of_known_option_is_not_adopted(
        self, temp_beets_library: Library
    ) -> None:
        """'HAPPY' collides case-insensitively with 'happy'; it is logged and
        left unselected rather than crashing the load."""
        item = next(iter(temp_beets_library.items()))
        item["mood"] = "HAPPY"
        item.store()
        app = make_app(temp_beets_library, {"mood": ["happy"]})
        async with app.run_test():
            lst = app.query_one("#selection-mood", CustomSelectionList)
            assert lst.option_count == 1
            assert lst.selected == []


class TestPersistDefinitions:
    @pytest.mark.asyncio
    async def test_write_failure_is_logged_not_raised(
        self, temp_beets_library: Library, tmp_path: Path
    ) -> None:
        item = next(iter(temp_beets_library.items()))
        item["mood"] = "Jazzy"
        item.store()
        path = tmp_path / "missing" / "quicktag_categories.yaml"
        app = make_app(temp_beets_library, {"mood": ["happy"]}, path)
        async with app.run_test():
            pass
        assert app.definitions.options("mood") == ["happy", "Jazzy"]
        assert not path.exists()
