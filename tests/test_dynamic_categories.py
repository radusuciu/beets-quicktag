"""Adding categories and options from the TUI, and the value shapes they use.

Every test builds the app against the scratch library from ``conftest.py``.
"""

from pathlib import Path

import pytest
from beets.library import Library
from textual.widgets import Input

from beetsplug.quicktag.app import QuickTagApp
from beetsplug.quicktag.definitions import CategoryDefinitions
from beetsplug.quicktag.definitions_file import read_definitions_file
from beetsplug.quicktag.widgets.category_panel import CategoryPanel
from beetsplug.quicktag.widgets.custom_selection_list import CustomSelectionList
from beetsplug.quicktag.widgets.input_with_label import InputWithLabel

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


class TestCategoryPanelLayout:
    @pytest.mark.asyncio
    async def test_each_category_is_a_panel_with_list_and_hidden_input(
        self, temp_beets_library: Library
    ) -> None:
        app = make_app(temp_beets_library, {"mood": ["happy"], "vibe": ["afro"]})
        async with app.run_test():
            panels = list(app.query(CategoryPanel))
            assert [p.id for p in panels] == ["panel-mood", "panel-vibe"]
            mood = app.query_one("#panel-mood", CategoryPanel)
            assert mood.selection_list.id == "selection-mood"
            assert str(mood.border_title) == "mood"
            assert mood.input.display is False
            assert mood.input_active is False

    @pytest.mark.asyncio
    async def test_first_list_has_focus_on_mount(
        self, temp_beets_library: Library
    ) -> None:
        app = make_app(temp_beets_library, {"mood": ["happy"], "vibe": ["afro"]})
        async with app.run_test():
            assert app.focused is app.query_one("#selection-mood")


class TestPlusOpensInlineInput:
    @pytest.mark.asyncio
    async def test_plus_reveals_and_focuses_input_of_focused_panel(
        self, temp_beets_library: Library
    ) -> None:
        app = make_app(temp_beets_library, {"mood": ["happy"], "vibe": ["afro"]})
        async with app.run_test() as pilot:
            app.query_one("#selection-vibe", CustomSelectionList).focus()
            await pilot.press("plus")
            vibe = app.query_one("#panel-vibe", CategoryPanel)
            mood = app.query_one("#panel-mood", CategoryPanel)
            assert vibe.input_active is True
            assert app.focused is vibe.input
            assert vibe.input.value == ""
            assert mood.input_active is False

    @pytest.mark.asyncio
    async def test_plus_is_typed_into_the_open_input(
        self, temp_beets_library: Library
    ) -> None:
        """The binding lives on the list, so it never fires from an Input."""
        app = make_app(temp_beets_library, {"mood": ["happy"]})
        async with app.run_test() as pilot:
            await pilot.press("plus")
            await pilot.press("plus")
            panel = app.query_one("#panel-mood", CategoryPanel)
            assert panel.input.value == "+"

    @pytest.mark.asyncio
    async def test_plus_is_listed_in_footer_with_list_focused(
        self, temp_beets_library: Library
    ) -> None:
        from textual.widgets import Footer
        from textual.widgets._footer import FooterKey

        app = make_app(temp_beets_library, {"mood": ["happy"]})
        async with app.run_test() as pilot:
            await pilot.pause()
            keys = {key.key for key in app.query_one(Footer).query(FooterKey)}
            assert "plus" in keys

    @pytest.mark.asyncio
    async def test_close_input_hides_clears_and_refocuses_list(
        self, temp_beets_library: Library
    ) -> None:
        app = make_app(temp_beets_library, {"mood": ["happy"]})
        async with app.run_test() as pilot:
            await pilot.press("plus", "x")
            panel = app.query_one("#panel-mood", CategoryPanel)
            panel.close_input()
            await pilot.pause()
            assert panel.input_active is False
            assert panel.input.value == ""
            assert app.focused is panel.selection_list

    @pytest.mark.asyncio
    async def test_show_error_keeps_input_open_with_message(
        self, temp_beets_library: Library
    ) -> None:
        app = make_app(temp_beets_library, {"mood": ["happy"]})
        async with app.run_test() as pilot:
            await pilot.press("plus", "x")
            panel = app.query_one("#panel-mood", CategoryPanel)
            panel.show_error("Nope.")
            await pilot.pause()
            assert panel.input_active is True
            assert panel.input.value == ""
            assert panel.input.placeholder == "Nope."
            assert app.focused is panel.input

    @pytest.mark.asyncio
    async def test_add_option_appends_highlights_and_optionally_selects(
        self, temp_beets_library: Library
    ) -> None:
        app = make_app(temp_beets_library, {"mood": ["happy"]})
        async with app.run_test():
            panel = app.query_one("#panel-mood", CategoryPanel)
            panel.add_option("sad", select=True)
            panel.add_option("calm", select=False)
            lst = panel.selection_list
            assert [
                str(lst.get_option_at_index(i).prompt) for i in range(lst.option_count)
            ] == ["happy", "sad", "calm"]
            assert lst.highlighted == 2
            assert lst.selected == ["sad"]


class TestAddOptionFlow:
    @pytest.mark.asyncio
    async def test_enter_adds_selects_persists_and_refocuses_list(
        self, temp_beets_library: Library, tmp_path: Path
    ) -> None:
        path = tmp_path / "quicktag_categories.yaml"
        app = make_app(temp_beets_library, {"mood": ["happy"]}, path)
        async with app.run_test() as pilot:
            await pilot.press("plus", "s", "a", "d", "enter")
            panel = app.query_one("#panel-mood", CategoryPanel)
            lst = panel.selection_list
            assert app.definitions.options("mood") == ["happy", "sad"]
            assert lst.option_count == 2
            assert lst.selected == ["sad"]
            assert lst.highlighted == 1
            assert panel.input_active is False
            assert app.focused is lst
        assert read_definitions_file(path).options("mood") == ["happy", "sad"]

    @pytest.mark.asyncio
    async def test_new_option_is_saved_on_the_current_track(
        self, temp_beets_library: Library
    ) -> None:
        app = make_app(temp_beets_library, {"mood": ["happy"]})
        async with app.run_test() as pilot:
            await pilot.press("plus", "s", "a", "d", "enter")
            item_id = app.item.id
            await app._save_current_item_tags()
        assert temp_beets_library.get_item(item_id).get("mood") == "sad"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("typed", "message_part"),
        [
            (["enter"], "cannot be empty"),
            (["h", "a", "p", "p", "y", "enter"], "already has 'happy'"),
            (["a", "comma", "b", "enter"], "cannot contain a comma"),
        ],
    )
    async def test_invalid_option_shows_error_and_stays_open(
        self, temp_beets_library: Library, typed: list[str], message_part: str
    ) -> None:
        app = make_app(temp_beets_library, {"mood": ["happy"]})
        async with app.run_test() as pilot:
            await pilot.press("plus", *typed)
            panel = app.query_one("#panel-mood", CategoryPanel)
            assert panel.input_active is True
            assert message_part in panel.input.placeholder
            assert panel.input.value == ""
            assert app.focused is panel.input
            assert app.definitions.options("mood") == ["happy"]

    @pytest.mark.asyncio
    async def test_error_placeholder_resets_on_next_open(
        self, temp_beets_library: Library
    ) -> None:
        app = make_app(temp_beets_library, {"mood": ["happy"]})
        async with app.run_test() as pilot:
            await pilot.press("plus", "enter")
            panel = app.query_one("#panel-mood", CategoryPanel)
            panel.close_input()
            await pilot.press("plus")
            assert "Enter to add" in panel.input.placeholder


class TestAddCategoryFlow:
    @pytest.mark.asyncio
    async def test_ctrl_n_reveals_input_above_comments(
        self, temp_beets_library: Library
    ) -> None:
        app = make_app(temp_beets_library, {"mood": ["happy"]})
        async with app.run_test() as pilot:
            new_input = app.query_one("#new-category-input", Input)
            assert new_input.display is False
            await pilot.press("ctrl+n")
            assert new_input.display is True
            assert app.focused is new_input
            screen_children = list(app.screen.children)
            comments_index = screen_children.index(app.query_one(InputWithLabel))
            assert screen_children[comments_index - 1] is new_input

    @pytest.mark.asyncio
    async def test_enter_mounts_empty_panel_before_comments_and_persists(
        self, temp_beets_library: Library, tmp_path: Path
    ) -> None:
        path = tmp_path / "quicktag_categories.yaml"
        app = make_app(temp_beets_library, {"mood": ["happy"]}, path)
        async with app.run_test() as pilot:
            await pilot.press("ctrl+n", "v", "i", "b", "e", "enter")
            await pilot.pause()
            assert app.definitions.categories == ["mood", "vibe"]
            panels = [p.id for p in app.query(CategoryPanel)]
            assert panels == ["panel-mood", "panel-vibe"]
            vibe = app.query_one("#panel-vibe", CategoryPanel)
            assert vibe.selection_list.option_count == 0
            assert app.focused is vibe.selection_list
            new_input = app.query_one("#new-category-input", Input)
            assert new_input.display is False
            assert new_input.value == ""
            screen_children = list(app.screen.children)
            assert screen_children.index(vibe) < screen_children.index(new_input)
            assert screen_children.index(new_input) < screen_children.index(
                app.query_one(InputWithLabel)
            )
        assert read_definitions_file(path).to_mapping() == {
            "mood": ["happy"],
            "vibe": [],
        }

    @pytest.mark.asyncio
    async def test_plus_then_enter_in_new_panel_adds_first_option(
        self, temp_beets_library: Library
    ) -> None:
        app = make_app(temp_beets_library, {"mood": ["happy"]})
        async with app.run_test() as pilot:
            await pilot.press("ctrl+n", "v", "i", "b", "e", "enter")
            await pilot.pause()
            await pilot.press("plus", "a", "f", "r", "o", "enter")
            assert app.definitions.options("vibe") == ["afro"]
            vibe = app.query_one("#panel-vibe", CategoryPanel)
            assert vibe.selection_list.selected == ["afro"]

    @pytest.mark.asyncio
    async def test_new_category_is_saved_and_loaded(
        self, temp_beets_library: Library
    ) -> None:
        app = make_app(temp_beets_library, {"mood": ["happy"]})
        async with app.run_test() as pilot:
            await pilot.press("ctrl+n", "v", "i", "b", "e", "enter")
            await pilot.pause()
            await pilot.press("plus", "a", "f", "r", "o", "enter")
            item_id = app.item.id
            await pilot.press("right")  # saves the first item
            await pilot.press("left")  # reloads it
            vibe = app.query_one("#panel-vibe", CategoryPanel)
            assert vibe.selection_list.selected == ["afro"]
        assert temp_beets_library.get_item(item_id).get("vibe") == "afro"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("typed", "message_part"),
        [
            (["enter"], "letters, digits"),
            (["m", "o", "o", "d", "enter"], "already exists"),
            (["y", "e", "a", "r", "enter"], "built-in beets field"),
            (["1", "a", "enter"], "letters, digits"),
        ],
    )
    async def test_invalid_name_shows_error_and_stays_open(
        self, temp_beets_library: Library, typed: list[str], message_part: str
    ) -> None:
        app = make_app(temp_beets_library, {"mood": ["happy"]})
        async with app.run_test() as pilot:
            await pilot.press("ctrl+n", *typed)
            new_input = app.query_one("#new-category-input", Input)
            assert new_input.display is True
            assert message_part in new_input.placeholder
            assert new_input.value == ""
            assert app.focused is new_input
            assert app.definitions.categories == ["mood"]

    @pytest.mark.asyncio
    async def test_comments_enter_does_not_add_a_category(
        self, temp_beets_library: Library
    ) -> None:
        app = make_app(temp_beets_library, {"mood": ["happy"]})
        async with app.run_test() as pilot:
            app.query_one(InputWithLabel).query_one(Input).focus()
            await pilot.press("h", "i", "enter")
            assert app.definitions.categories == ["mood"]
            assert app.query_one(InputWithLabel).value == "hi"

    @pytest.mark.asyncio
    async def test_ctrl_n_works_with_no_categories_at_all(
        self, temp_beets_library: Library
    ) -> None:
        app = make_app(temp_beets_library, {})
        async with app.run_test() as pilot:
            await pilot.press("ctrl+n", "m", "o", "o", "d", "enter")
            await pilot.pause()
            assert app.definitions.categories == ["mood"]
            assert app.query_one("#panel-mood", CategoryPanel)
