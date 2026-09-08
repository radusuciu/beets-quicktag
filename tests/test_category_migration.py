"""Renaming and deleting options and categories from the TUI, with the
library migration that goes with them."""

from collections.abc import Sequence
from pathlib import Path

import pytest
from beets.library import Item, Library
from textual.app import App, ComposeResult
from textual.widgets import Input, Static
from textual.widgets.selection_list import Selection

from beetsplug.quicktag.app import QuickTagApp
from beetsplug.quicktag.definitions import CategoryDefinitions
from beetsplug.quicktag.definitions_file import read_definitions_file
from beetsplug.quicktag.widgets.category_panel import CategoryPanel
from beetsplug.quicktag.widgets.custom_selection_list import (
    CustomSelectionList,
    EditKind,
)

LIST_FIELD = "genres"
needs_list_field = pytest.mark.skipif(
    not CategoryDefinitions.is_list_field(LIST_FIELD),
    reason="installed beets has no list-valued 'genres' field",
)


def make_app(
    lib: Library,
    mapping: dict[str, list[str]],
    definitions_path: Path | None = None,
    query: Sequence[str] = (),
) -> QuickTagApp:
    return QuickTagApp(
        lib=lib,
        items=list(lib.items(list(query))),
        definitions=CategoryDefinitions.from_config(mapping),
        autoplay_at_launch_enabled=False,
        autoplay_on_track_change_enabled=False,
        autonext_at_track_end_enabled=False,
        autosave_on_quit_enabled=False,
        keep_playing_on_track_change_if_playing_enabled=False,
        definitions_path=definitions_path,
        query=query,
    )


def header_text(app: QuickTagApp) -> str:
    return app.query_one("#header_text_content", Static).render().plain


def prompts(selection_list: CustomSelectionList) -> list[str]:
    return [
        str(selection_list.get_option_at_index(i).prompt)
        for i in range(selection_list.option_count)
    ]


def tracks(lib: Library) -> list[Item]:
    return list(lib.items())


def set_field(lib: Library, item_id: int, field: str, value: object) -> None:
    item = lib.get_item(item_id)
    if value is None:
        if field in item:
            del item[field]
    else:
        item[field] = value
    item.store()


class ListHost(App[None]):
    """A bare app around one list, to test its keys without the panel."""

    def __init__(self, *values: str) -> None:
        super().__init__()
        self._values = values
        self.requests: list[tuple[EditKind, str | None]] = []

    def compose(self) -> ComposeResult:
        yield CustomSelectionList(*(Selection(v, v) for v in self._values))

    def on_custom_selection_list_edit_requested(
        self, message: CustomSelectionList.EditRequested
    ) -> None:
        self.requests.append((message.kind, message.value))


class TestListEditKeys:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("key", "kind", "value"),
        [
            ("plus", EditKind.ADD_OPTION, None),
            ("f2", EditKind.RENAME_OPTION, "sad"),
            ("delete", EditKind.REMOVE_OPTION, "sad"),
            ("ctrl+r", EditKind.RENAME_CATEGORY, None),
            ("ctrl+d", EditKind.REMOVE_CATEGORY, None),
        ],
    )
    async def test_key_posts_edit_requested(
        self, key: str, kind: EditKind, value: str | None
    ) -> None:
        host = ListHost("happy", "sad")
        async with host.run_test() as pilot:
            host.query_one(CustomSelectionList).highlighted = 1
            await pilot.press(key)
            await pilot.pause()
            assert host.requests == [(kind, value)]

    @pytest.mark.asyncio
    async def test_option_keys_do_nothing_without_a_highlight(self) -> None:
        host = ListHost()
        async with host.run_test() as pilot:
            await pilot.press("f2", "delete")
            await pilot.pause()
            assert host.requests == []
            await pilot.press("plus", "ctrl+r")
            await pilot.pause()
            assert host.requests == [
                (EditKind.ADD_OPTION, None),
                (EditKind.RENAME_CATEGORY, None),
            ]

    @pytest.mark.asyncio
    async def test_editing_keys_are_listed_in_the_footer(
        self, temp_beets_library: Library
    ) -> None:
        from textual.widgets import Footer
        from textual.widgets._footer import FooterKey

        app = make_app(temp_beets_library, {"mood": ["happy"]})
        async with app.run_test() as pilot:
            await pilot.pause()
            keys = {key.key for key in app.query_one(Footer).query(FooterKey)}
            assert {"f2", "delete", "ctrl+r", "ctrl+d"} <= keys


class TestPanelInline:
    @pytest.mark.asyncio
    async def test_open_confirm_shows_question_and_takes_focus(
        self, temp_beets_library: Library
    ) -> None:
        app = make_app(temp_beets_library, {"mood": ["happy"]})
        async with app.run_test() as pilot:
            panel = app.query_one("#panel-mood", CategoryPanel)
            panel.open_confirm("Sure? y/n")
            await pilot.pause()
            assert panel.confirm_active is True
            assert panel.inline_active is True
            assert panel.input_active is False
            assert app.focused is panel.confirm_prompt
            assert panel.confirm_prompt.render().plain == "Sure? y/n"

    @pytest.mark.asyncio
    async def test_n_closes_confirm_and_refocuses_list(
        self, temp_beets_library: Library
    ) -> None:
        app = make_app(temp_beets_library, {"mood": ["happy"]})
        async with app.run_test() as pilot:
            panel = app.query_one("#panel-mood", CategoryPanel)
            ran: list[bool] = []

            async def run() -> None:
                ran.append(True)

            app._ask(panel, "Sure? y/n", run)
            await pilot.pause()
            await pilot.press("n")
            await pilot.pause()
            assert ran == []
            assert panel.confirm_active is False
            assert app.focused is panel.selection_list

    @pytest.mark.asyncio
    async def test_y_runs_the_pending_action_once(
        self, temp_beets_library: Library
    ) -> None:
        app = make_app(temp_beets_library, {"mood": ["happy"]})
        async with app.run_test() as pilot:
            panel = app.query_one("#panel-mood", CategoryPanel)
            ran: list[bool] = []

            async def run() -> None:
                ran.append(True)

            app._ask(panel, "Sure? y/n", run)
            await pilot.pause()
            await pilot.press("y")
            await pilot.pause()
            assert ran == [True]
            assert panel.confirm_active is False
            assert app.focused is panel.selection_list
            assert app._pending_confirm is None

    @pytest.mark.asyncio
    async def test_y_is_typed_into_an_open_input_not_confirmed(
        self, temp_beets_library: Library
    ) -> None:
        app = make_app(temp_beets_library, {"mood": ["happy"]})
        async with app.run_test() as pilot:
            await pilot.press("plus", "y")
            panel = app.query_one("#panel-mood", CategoryPanel)
            assert panel.input.value == "y"

    @pytest.mark.asyncio
    async def test_escape_cancels_confirm_and_does_not_quit(
        self, temp_beets_library: Library
    ) -> None:
        app = make_app(temp_beets_library, {"mood": ["happy"]})
        async with app.run_test() as pilot:
            panel = app.query_one("#panel-mood", CategoryPanel)

            async def run() -> None:
                raise AssertionError("must not run")

            app._ask(panel, "Sure? y/n", run)
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            assert panel.confirm_active is False
            assert app.focused is panel.selection_list
            assert app._pending_confirm is None
            assert app.is_running

    @pytest.mark.asyncio
    async def test_confirm_replaces_an_open_input_and_vice_versa(
        self, temp_beets_library: Library
    ) -> None:
        app = make_app(temp_beets_library, {"mood": ["happy"]})
        async with app.run_test() as pilot:
            panel = app.query_one("#panel-mood", CategoryPanel)
            await pilot.press("plus", "x")
            panel.open_confirm("Sure? y/n")
            await pilot.pause()
            assert panel.input_active is False
            assert panel.input.value == ""
            assert panel.confirm_active is True
            panel.open_input()
            await pilot.pause()
            assert panel.confirm_active is False
            assert panel.input_active is True
            assert app.focused is panel.input

    @pytest.mark.asyncio
    async def test_ctrl_n_closes_an_open_confirm(
        self, temp_beets_library: Library
    ) -> None:
        app = make_app(temp_beets_library, {"mood": ["happy"]})
        async with app.run_test() as pilot:
            panel = app.query_one("#panel-mood", CategoryPanel)
            panel.open_confirm("Sure? y/n")
            await pilot.pause()
            await pilot.press("ctrl+n")
            await pilot.pause()
            assert panel.confirm_active is False
            assert app.focused is app.query_one("#new-category-input", Input)

    @pytest.mark.asyncio
    async def test_confirm_in_one_panel_closes_input_in_another(
        self, temp_beets_library: Library
    ) -> None:
        app = make_app(temp_beets_library, {"mood": ["happy"], "vibe": ["afro"]})
        async with app.run_test() as pilot:
            await pilot.press("plus", "x")
            mood = app.query_one("#panel-mood", CategoryPanel)
            vibe = app.query_one("#panel-vibe", CategoryPanel)
            vibe.open_confirm("Sure? y/n")
            await pilot.pause()
            assert mood.input_active is False
            assert vibe.confirm_active is True
            assert app.focused is vibe.confirm_prompt

    @pytest.mark.asyncio
    async def test_open_input_prefills_for_a_rename(
        self, temp_beets_library: Library
    ) -> None:
        app = make_app(temp_beets_library, {"mood": ["happy"]})
        async with app.run_test() as pilot:
            panel = app.query_one("#panel-mood", CategoryPanel)
            panel.open_input(EditKind.RENAME_OPTION, target="happy", initial="happy")
            await pilot.pause()
            assert panel.input.value == "happy"
            assert panel.input.cursor_position == 5
            assert "rename" in panel.input.placeholder
            assert panel.edit_kind is EditKind.RENAME_OPTION
            assert panel.edit_target == "happy"
            panel.close_input()
            assert panel.edit_kind is None
            assert panel.edit_target is None

    @pytest.mark.asyncio
    async def test_set_options_rebuilds_and_clamps_highlight(
        self, temp_beets_library: Library
    ) -> None:
        app = make_app(temp_beets_library, {"mood": ["happy", "sad", "calm"]})
        async with app.run_test() as pilot:
            panel = app.query_one("#panel-mood", CategoryPanel)
            panel.selection_list.select("sad")
            panel.set_options(["happy", "calm"], highlighted=2)
            await pilot.pause()
            assert prompts(panel.selection_list) == ["happy", "calm"]
            assert panel.selection_list.highlighted == 1
            assert panel.selection_list.selected == []
            panel.set_options([], highlighted=0)
            await pilot.pause()
            assert panel.selection_list.option_count == 0
            assert panel.selection_list.highlighted is None


class TestReloadAfterMigration:
    @pytest.mark.asyncio
    async def test_replaces_stale_item_and_reloads_selections(
        self, temp_beets_library: Library
    ) -> None:
        app = make_app(temp_beets_library, {"mood": ["happy", "sad"]})
        async with app.run_test():
            item_id = app.item.id
            set_field(temp_beets_library, item_id, "mood", "sad")
            await app._reload_after_migration()
            assert app.item.id == item_id
            assert app.items[app.current_item_index] is app.item
            assert app.item.get("mood") == "sad"
            lst = app.query_one("#selection-mood", CustomSelectionList)
            assert lst.selected == ["sad"]

    @pytest.mark.asyncio
    async def test_keeps_position_in_the_requeried_list(
        self, temp_beets_library: Library
    ) -> None:
        app = make_app(temp_beets_library, {"mood": ["happy"]})
        async with app.run_test() as pilot:
            await pilot.press("right")
            await pilot.pause()
            index, item_id = app.current_item_index, app.item.id
            assert index == 1
            await app._reload_after_migration()
            assert (app.current_item_index, app.item.id) == (index, item_id)
            assert len(app.items) == len(tracks(temp_beets_library))

    @pytest.mark.asyncio
    async def test_track_that_no_longer_matches_the_query_stays_current(
        self, temp_beets_library: Library
    ) -> None:
        first, second = tracks(temp_beets_library)[:2]
        set_field(temp_beets_library, first.id, "mood", "x")
        set_field(temp_beets_library, second.id, "mood", "x")
        app = make_app(temp_beets_library, {"mood": ["x"]}, query=["mood:x"])
        async with app.run_test() as pilot:
            assert len(app.items) == 2
            await pilot.press("right")
            await pilot.pause()
            assert app.item.id == second.id
            set_field(temp_beets_library, second.id, "mood", None)
            await app._reload_after_migration()
            assert app.item.id == second.id
            assert app.items[app.current_item_index] is app.item
            assert [item.id for item in app.items] == [first.id, second.id]
            assert app.query_one("#selection-mood", CustomSelectionList).selected == []

    @pytest.mark.asyncio
    async def test_show_message_replaces_the_header_line(
        self, temp_beets_library: Library
    ) -> None:
        app = make_app(temp_beets_library, {"mood": ["x"]})
        async with app.run_test() as pilot:
            app.header_widget.show_message("Library update failed")
            await pilot.pause()
            assert header_text(app) == "Library update failed"


async def press_f2_on(
    app: QuickTagApp, category: str, index: int, pilot: object
) -> None:
    """Highlight option ``index`` of ``category`` and press F2."""
    app.query_one(f"#selection-{category}", CustomSelectionList).highlighted = index
    await pilot.press("f2")  # type: ignore[attr-defined]
    await pilot.pause()  # type: ignore[attr-defined]


class TestRenameOptionFlow:
    @pytest.mark.asyncio
    async def test_f2_opens_input_prefilled_with_highlighted_option(
        self, temp_beets_library: Library
    ) -> None:
        app = make_app(temp_beets_library, {"mood": ["happy", "sad"]})
        async with app.run_test() as pilot:
            await press_f2_on(app, "mood", 1, pilot)
            panel = app.query_one("#panel-mood", CategoryPanel)
            assert panel.input_active is True
            assert panel.input.value == "sad"
            assert app.focused is panel.input
            assert panel.edit_kind is EditKind.RENAME_OPTION
            assert "rename" in panel.input.placeholder

    @pytest.mark.asyncio
    async def test_unchanged_name_just_closes(
        self, temp_beets_library: Library
    ) -> None:
        app = make_app(temp_beets_library, {"mood": ["happy", "sad"]})
        async with app.run_test() as pilot:
            await press_f2_on(app, "mood", 1, pilot)
            await pilot.press("enter")
            await pilot.pause()
            panel = app.query_one("#panel-mood", CategoryPanel)
            assert panel.inline_active is False
            assert app.focused is panel.selection_list
            assert app.definitions.options("mood") == ["happy", "sad"]

    @pytest.mark.asyncio
    async def test_rename_with_no_tracks_applies_immediately(
        self, temp_beets_library: Library, tmp_path: Path
    ) -> None:
        path = tmp_path / "quicktag_categories.yaml"
        app = make_app(temp_beets_library, {"mood": ["happy", "sad"]}, path)
        async with app.run_test() as pilot:
            await press_f2_on(app, "mood", 1, pilot)
            await pilot.press("ctrl+u", "b", "l", "u", "e", "enter")
            await pilot.pause()
            panel = app.query_one("#panel-mood", CategoryPanel)
            assert panel.inline_active is False
            assert app.definitions.options("mood") == ["happy", "blue"]
            assert prompts(panel.selection_list) == ["happy", "blue"]
            assert panel.selection_list.highlighted == 1
            assert app.focused is panel.selection_list
        assert read_definitions_file(path).options("mood") == ["happy", "blue"]

    @pytest.mark.asyncio
    async def test_rename_with_tracks_asks_then_migrates(
        self, temp_beets_library: Library, tmp_path: Path
    ) -> None:
        first, second = tracks(temp_beets_library)[:2]
        set_field(temp_beets_library, first.id, "mood", "sad")
        set_field(temp_beets_library, second.id, "mood", "sad, happy")
        path = tmp_path / "quicktag_categories.yaml"
        app = make_app(temp_beets_library, {"mood": ["happy", "sad"]}, path)
        async with app.run_test() as pilot:
            await press_f2_on(app, "mood", 1, pilot)
            await pilot.press("ctrl+u", "b", "l", "u", "e", "enter")
            await pilot.pause()
            panel = app.query_one("#panel-mood", CategoryPanel)
            assert panel.confirm_active is True
            assert panel.confirm_prompt.render().plain == (
                "Rename 'sad' to 'blue' on 2 tracks? y/n"
            )
            assert app.definitions.options("mood") == ["happy", "sad"]
            await pilot.press("y")
            await pilot.pause()
            assert panel.inline_active is False
            assert app.definitions.options("mood") == ["happy", "blue"]
            assert prompts(panel.selection_list) == ["happy", "blue"]
            assert panel.selection_list.selected == ["blue"]
            assert app.item.get("mood") == "blue"
            assert app.focused is panel.selection_list
        assert temp_beets_library.get_item(first.id).get("mood") == "blue"
        assert temp_beets_library.get_item(second.id).get("mood") == "blue, happy"
        assert read_definitions_file(path).options("mood") == ["happy", "blue"]

    @pytest.mark.asyncio
    async def test_pending_selection_is_saved_before_counting(
        self, temp_beets_library: Library
    ) -> None:
        app = make_app(temp_beets_library, {"mood": ["happy", "sad"]})
        async with app.run_test() as pilot:
            app.query_one("#selection-mood", CustomSelectionList).select("sad")
            await press_f2_on(app, "mood", 1, pilot)
            await pilot.press("ctrl+u", "x", "enter")
            await pilot.pause()
            panel = app.query_one("#panel-mood", CategoryPanel)
            assert panel.confirm_prompt.render().plain == (
                "Rename 'sad' to 'x' on 1 tracks? y/n"
            )

    @pytest.mark.asyncio
    async def test_n_cancels_the_rename(self, temp_beets_library: Library) -> None:
        first = tracks(temp_beets_library)[0]
        set_field(temp_beets_library, first.id, "mood", "sad")
        app = make_app(temp_beets_library, {"mood": ["happy", "sad"]})
        async with app.run_test() as pilot:
            await press_f2_on(app, "mood", 1, pilot)
            await pilot.press("ctrl+u", "x", "enter")
            await pilot.pause()
            await pilot.press("n")
            await pilot.pause()
            panel = app.query_one("#panel-mood", CategoryPanel)
            assert panel.inline_active is False
            assert app.definitions.options("mood") == ["happy", "sad"]
            assert app.focused is panel.selection_list
        assert temp_beets_library.get_item(first.id).get("mood") == "sad"

    @pytest.mark.asyncio
    async def test_merge_asks_and_uses_the_existing_spelling(
        self, temp_beets_library: Library
    ) -> None:
        first = tracks(temp_beets_library)[0]
        set_field(temp_beets_library, first.id, "mood", "Hiphop")
        app = make_app(temp_beets_library, {"mood": ["Hiphop", "Hip-Hop"]})
        async with app.run_test() as pilot:
            await press_f2_on(app, "mood", 0, pilot)
            await pilot.press("ctrl+u", "h", "i", "p", "minus", "h", "o", "p", "enter")
            await pilot.pause()
            panel = app.query_one("#panel-mood", CategoryPanel)
            assert panel.confirm_prompt.render().plain == (
                "Merge 'Hiphop' into 'Hip-Hop' on 1 tracks? y/n"
            )
            await pilot.press("y")
            await pilot.pause()
            assert app.definitions.options("mood") == ["Hip-Hop"]
            assert prompts(panel.selection_list) == ["Hip-Hop"]
            assert panel.selection_list.selected == ["Hip-Hop"]
            assert panel.selection_list.highlighted == 0
        assert temp_beets_library.get_item(first.id).get("mood") == "Hip-Hop"

    @pytest.mark.asyncio
    async def test_merge_asks_even_with_no_tracks(
        self, temp_beets_library: Library
    ) -> None:
        app = make_app(temp_beets_library, {"mood": ["Hiphop", "Hip-Hop"]})
        async with app.run_test() as pilot:
            await press_f2_on(app, "mood", 0, pilot)
            await pilot.press("ctrl+u", "h", "i", "p", "minus", "h", "o", "p", "enter")
            await pilot.pause()
            panel = app.query_one("#panel-mood", CategoryPanel)
            assert panel.confirm_active is True
            assert "0 tracks" in panel.confirm_prompt.render().plain

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("typed", "message_part"),
        [
            (["ctrl+u", "enter"], "cannot be empty"),
            (["ctrl+u", "a", "comma", "b", "enter"], "cannot contain a comma"),
        ],
    )
    async def test_invalid_name_shows_error_and_stays_open(
        self, temp_beets_library: Library, typed: list[str], message_part: str
    ) -> None:
        app = make_app(temp_beets_library, {"mood": ["happy", "sad"]})
        async with app.run_test() as pilot:
            await press_f2_on(app, "mood", 1, pilot)
            await pilot.press(*typed)
            await pilot.pause()
            panel = app.query_one("#panel-mood", CategoryPanel)
            assert panel.input_active is True
            assert message_part in panel.input.placeholder
            assert app.focused is panel.input
            assert app.definitions.options("mood") == ["happy", "sad"]

    @pytest.mark.asyncio
    async def test_migration_failure_changes_nothing_and_says_so(
        self,
        temp_beets_library: Library,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        first = tracks(temp_beets_library)[0]
        set_field(temp_beets_library, first.id, "mood", "sad")
        path = tmp_path / "quicktag_categories.yaml"
        app = make_app(temp_beets_library, {"mood": ["happy", "sad"]}, path)

        def explode(*args: object, **kwargs: object) -> int:
            raise RuntimeError("disk on fire")

        monkeypatch.setattr("beetsplug.quicktag.app.rename_option", explode)
        async with app.run_test() as pilot:
            await press_f2_on(app, "mood", 1, pilot)
            await pilot.press("ctrl+u", "x", "enter")
            await pilot.pause()
            await pilot.press("y")
            await pilot.pause()
            panel = app.query_one("#panel-mood", CategoryPanel)
            assert "Library update failed" in header_text(app)
            assert "disk on fire" in header_text(app)
            assert app.definitions.options("mood") == ["happy", "sad"]
            assert prompts(panel.selection_list) == ["happy", "sad"]
            assert panel.selection_list.selected == ["sad"]
            assert panel.inline_active is False
            assert app.focused is panel.selection_list
        assert not path.exists()
        assert temp_beets_library.get_item(first.id).get("mood") == "sad"


class TestRemoveOptionFlow:
    @pytest.mark.asyncio
    async def test_delete_asks_with_the_track_count(
        self, temp_beets_library: Library
    ) -> None:
        first, second = tracks(temp_beets_library)[:2]
        set_field(temp_beets_library, first.id, "mood", "sad")
        set_field(temp_beets_library, second.id, "mood", "sad, happy")
        app = make_app(temp_beets_library, {"mood": ["happy", "sad"]})
        async with app.run_test() as pilot:
            app.query_one("#selection-mood", CustomSelectionList).highlighted = 1
            await pilot.press("delete")
            await pilot.pause()
            panel = app.query_one("#panel-mood", CategoryPanel)
            assert panel.confirm_active is True
            assert panel.confirm_prompt.render().plain == (
                "Delete 'sad' from 2 tracks? y/n"
            )
            assert app.focused is panel.confirm_prompt

    @pytest.mark.asyncio
    async def test_delete_asks_even_with_no_tracks(
        self, temp_beets_library: Library
    ) -> None:
        app = make_app(temp_beets_library, {"mood": ["happy", "sad"]})
        async with app.run_test() as pilot:
            app.query_one("#selection-mood", CustomSelectionList).highlighted = 1
            await pilot.press("delete")
            await pilot.pause()
            panel = app.query_one("#panel-mood", CategoryPanel)
            assert panel.confirm_prompt.render().plain == (
                "Delete 'sad' from 0 tracks? y/n"
            )

    @pytest.mark.asyncio
    async def test_y_removes_option_everywhere(
        self, temp_beets_library: Library, tmp_path: Path
    ) -> None:
        first, second = tracks(temp_beets_library)[:2]
        set_field(temp_beets_library, first.id, "mood", "sad")
        set_field(temp_beets_library, second.id, "mood", "sad, happy")
        path = tmp_path / "quicktag_categories.yaml"
        app = make_app(temp_beets_library, {"mood": ["happy", "sad", "calm"]}, path)
        async with app.run_test() as pilot:
            app.query_one("#selection-mood", CustomSelectionList).highlighted = 1
            await pilot.press("delete")
            await pilot.pause()
            await pilot.press("y")
            await pilot.pause()
            panel = app.query_one("#panel-mood", CategoryPanel)
            assert panel.inline_active is False
            assert app.definitions.options("mood") == ["happy", "calm"]
            assert prompts(panel.selection_list) == ["happy", "calm"]
            assert panel.selection_list.highlighted == 1
            assert panel.selection_list.selected == []
            assert app.item.get("mood") is None
            assert app.focused is panel.selection_list
        assert "mood" not in temp_beets_library.get_item(first.id)
        assert temp_beets_library.get_item(second.id).get("mood") == "happy"
        assert read_definitions_file(path).options("mood") == ["happy", "calm"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("key", ["n", "escape"])
    async def test_n_or_escape_cancels(
        self, temp_beets_library: Library, key: str
    ) -> None:
        first = tracks(temp_beets_library)[0]
        set_field(temp_beets_library, first.id, "mood", "sad")
        app = make_app(temp_beets_library, {"mood": ["happy", "sad"]})
        async with app.run_test() as pilot:
            app.query_one("#selection-mood", CustomSelectionList).highlighted = 1
            await pilot.press("delete")
            await pilot.pause()
            await pilot.press(key)
            await pilot.pause()
            panel = app.query_one("#panel-mood", CategoryPanel)
            assert panel.inline_active is False
            assert app.definitions.options("mood") == ["happy", "sad"]
            assert panel.selection_list.selected == ["sad"]
            assert app.is_running
        assert temp_beets_library.get_item(first.id).get("mood") == "sad"

    @pytest.mark.asyncio
    async def test_pending_selection_is_saved_before_counting(
        self, temp_beets_library: Library
    ) -> None:
        app = make_app(temp_beets_library, {"mood": ["happy", "sad"]})
        async with app.run_test() as pilot:
            lst = app.query_one("#selection-mood", CustomSelectionList)
            lst.select("sad")
            lst.highlighted = 1
            await pilot.press("delete")
            await pilot.pause()
            panel = app.query_one("#panel-mood", CategoryPanel)
            assert panel.confirm_prompt.render().plain == (
                "Delete 'sad' from 1 tracks? y/n"
            )

    @pytest.mark.asyncio
    async def test_deleting_the_last_option_leaves_an_empty_list(
        self, temp_beets_library: Library
    ) -> None:
        app = make_app(temp_beets_library, {"mood": ["only"]})
        async with app.run_test() as pilot:
            app.query_one("#selection-mood", CustomSelectionList).highlighted = 0
            await pilot.press("delete")
            await pilot.pause()
            await pilot.press("y")
            await pilot.pause()
            panel = app.query_one("#panel-mood", CategoryPanel)
            assert app.definitions.options("mood") == []
            assert panel.selection_list.option_count == 0
            assert panel.selection_list.highlighted is None
            assert app.focused is panel.selection_list


class TestRenameCategoryFlow:
    @pytest.mark.asyncio
    async def test_ctrl_r_opens_input_prefilled_with_the_name(
        self, temp_beets_library: Library
    ) -> None:
        app = make_app(temp_beets_library, {"mood": ["happy"], "vibe": ["afro"]})
        async with app.run_test() as pilot:
            app.query_one("#selection-vibe", CustomSelectionList).focus()
            await pilot.press("ctrl+r")
            await pilot.pause()
            vibe = app.query_one("#panel-vibe", CategoryPanel)
            assert vibe.input_active is True
            assert vibe.input.value == "vibe"
            assert vibe.edit_kind is EditKind.RENAME_CATEGORY
            assert app.focused is vibe.input
            assert "category" in vibe.input.placeholder

    @pytest.mark.asyncio
    async def test_unchanged_name_just_closes(
        self, temp_beets_library: Library
    ) -> None:
        app = make_app(temp_beets_library, {"mood": ["happy"]})
        async with app.run_test() as pilot:
            await pilot.press("ctrl+r")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            panel = app.query_one("#panel-mood", CategoryPanel)
            assert panel.inline_active is False
            assert app.definitions.categories == ["mood"]
            assert app.focused is panel.selection_list

    @pytest.mark.asyncio
    async def test_rename_without_tracks_replaces_the_panel_in_place(
        self, temp_beets_library: Library, tmp_path: Path
    ) -> None:
        path = tmp_path / "quicktag_categories.yaml"
        app = make_app(temp_beets_library, {"mood": ["happy"], "vibe": ["afro"]}, path)
        async with app.run_test() as pilot:
            await pilot.press("ctrl+r", "ctrl+u", "f", "e", "e", "l", "enter")
            await pilot.pause()
            assert app.definitions.categories == ["feel", "vibe"]
            assert [p.id for p in app.query(CategoryPanel)] == [
                "panel-feel",
                "panel-vibe",
            ]
            feel = app.query_one("#panel-feel", CategoryPanel)
            assert feel.category == "feel"
            assert feel.selection_list.id == "selection-feel"
            assert str(feel.border_title) == "feel"
            assert prompts(feel.selection_list) == ["happy"]
            assert app.focused is feel.selection_list
            assert feel.inline_active is False
        assert read_definitions_file(path).to_mapping() == {
            "feel": ["happy"],
            "vibe": ["afro"],
        }

    @pytest.mark.asyncio
    async def test_rename_with_tracks_asks_then_migrates(
        self, temp_beets_library: Library
    ) -> None:
        first, second = tracks(temp_beets_library)[:2]
        set_field(temp_beets_library, first.id, "mood", "happy")
        set_field(temp_beets_library, second.id, "mood", "happy")
        app = make_app(temp_beets_library, {"mood": ["happy"]})
        async with app.run_test() as pilot:
            await pilot.press("ctrl+r", "ctrl+u", "f", "e", "e", "l", "enter")
            await pilot.pause()
            mood = app.query_one("#panel-mood", CategoryPanel)
            assert mood.confirm_prompt.render().plain == (
                "Rename category 'mood' to 'feel' on 2 tracks? y/n"
            )
            await pilot.press("y")
            await pilot.pause()
            feel = app.query_one("#panel-feel", CategoryPanel)
            assert feel.selection_list.selected == ["happy"]
            assert app.item.get("feel") == "happy"
            assert "mood" not in app.item
            assert app.focused is feel.selection_list
        assert temp_beets_library.get_item(second.id).get("feel") == "happy"
        assert "mood" not in temp_beets_library.get_item(second.id)

    @pytest.mark.asyncio
    async def test_case_only_rename_is_a_plain_rename(
        self, temp_beets_library: Library
    ) -> None:
        app = make_app(temp_beets_library, {"mood": ["happy"]})
        async with app.run_test() as pilot:
            await pilot.press("ctrl+r", "ctrl+u", "M", "o", "o", "d", "enter")
            await pilot.pause()
            assert app.definitions.categories == ["Mood"]
            assert app.query_one("#panel-Mood", CategoryPanel).category == "Mood"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("typed", "message_part"),
        [
            (["ctrl+u", "a", "l", "b", "u", "m", "enter"], "built-in beets field"),
            (["ctrl+u", "v", "i", "b", "e", "enter"], "already exists"),
            (["ctrl+u", "1", "x", "enter"], "letters, digits"),
        ],
    )
    async def test_invalid_name_shows_error_and_stays_open(
        self, temp_beets_library: Library, typed: list[str], message_part: str
    ) -> None:
        app = make_app(temp_beets_library, {"mood": ["happy"], "vibe": ["afro"]})
        async with app.run_test() as pilot:
            await pilot.press("ctrl+r", *typed)
            await pilot.pause()
            panel = app.query_one("#panel-mood", CategoryPanel)
            assert panel.input_active is True
            assert message_part in panel.input.placeholder
            assert app.focused is panel.input
            assert app.definitions.categories == ["mood", "vibe"]

    @needs_list_field
    @pytest.mark.asyncio
    async def test_genre_to_genres_moves_values_into_the_list_field(
        self, temp_beets_library: Library
    ) -> None:
        first = tracks(temp_beets_library)[0]
        set_field(temp_beets_library, first.id, "genre", "House, Techno")
        app = make_app(temp_beets_library, {"genre": ["House", "Techno"]})
        async with app.run_test() as pilot:
            await pilot.press("ctrl+r", "end", "s", "enter")
            await pilot.pause()
            assert "Rename category 'genre' to 'genres' on 1 tracks" in (
                app.query_one("#panel-genre", CategoryPanel)
                .confirm_prompt.render()
                .plain
            )
            await pilot.press("y")
            await pilot.pause()
            assert app.definitions.categories == [LIST_FIELD]
            genres = app.query_one(f"#panel-{LIST_FIELD}", CategoryPanel)
            assert sorted(genres.selection_list.selected) == ["House", "Techno"]
        item = temp_beets_library.get_item(first.id)
        assert item[LIST_FIELD] == ["House", "Techno"]
        assert not item.get("genre")
