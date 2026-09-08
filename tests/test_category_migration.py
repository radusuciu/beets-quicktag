"""Renaming and deleting options and categories from the TUI, with the
library migration that goes with them."""

from pathlib import Path

import pytest
from beets.library import Item, Library
from textual.app import App, ComposeResult
from textual.pilot import Pilot
from textual.widgets import Input
from textual.widgets.selection_list import Selection

from beetsplug.quicktag.app import QuickTagApp
from beetsplug.quicktag.definitions_file import read_definitions_file
from beetsplug.quicktag.item_values import split_value, write_item_values
from beetsplug.quicktag.widgets.category_panel import CategoryPanel
from beetsplug.quicktag.widgets.custom_selection_list import (
    CustomSelectionList,
    EditKind,
)
from beetsplug.quicktag.widgets.input_with_label import InputWithLabel
from conftest import (
    LIST_FIELD,
    header_text,
    make_app,
    needs_list_field,
    prompts,
    settle,
)

KEY_FOR = {
    EditKind.ADD_OPTION: "plus",
    EditKind.RENAME_OPTION: "f2",
    EditKind.REMOVE_OPTION: "delete",
    EditKind.RENAME_CATEGORY: "ctrl+r",
    EditKind.REMOVE_CATEGORY: "ctrl+d",
}

# The migration each kind runs, as patched in ``beetsplug.quicktag.app``.
MIGRATION_FOR = {
    EditKind.RENAME_OPTION: "rename_option",
    EditKind.REMOVE_OPTION: "remove_option",
    EditKind.RENAME_CATEGORY: "rename_category",
    EditKind.REMOVE_CATEGORY: "remove_category",
}


def tracks(lib: Library) -> list[Item]:
    return list(lib.items())


def set_field(lib: Library, item_id: int, field: str, value: str | None) -> None:
    """Seed a track through the helper the app itself writes with."""
    item = lib.get_item(item_id)
    write_item_values(item, field, split_value(value))
    item.store()


def panel_of(app: QuickTagApp, category: str) -> CategoryPanel:
    return app.query_one(f"#panel-{category}", CategoryPanel)


async def start_edit(
    app: QuickTagApp,
    pilot: Pilot[None],
    kind: EditKind,
    category: str = "mood",
    index: int = 0,
) -> CategoryPanel:
    """Press the key for ``kind`` on ``category``'s list (option kinds act on
    the option at ``index``) and wait for whatever it opens."""
    selection_list = app.query_one(f"#selection-{category}", CustomSelectionList)
    selection_list.focus()
    if kind in (EditKind.RENAME_OPTION, EditKind.REMOVE_OPTION):
        selection_list.highlighted = index
    await pilot.press(KEY_FOR[kind])
    await settle(app, pilot)
    return panel_of(app, category)


async def submit(app: QuickTagApp, pilot: Pilot[None], *keys: str) -> None:
    """Type ``keys`` into the open inline input and press Enter."""
    await pilot.press("ctrl+u", *keys, "enter")
    await settle(app, pilot)


async def answer(app: QuickTagApp, pilot: Pilot[None], key: str) -> None:
    """Answer the open y/n prompt and wait for the edit to finish."""
    await pilot.press(key)
    await settle(app, pilot)


async def run_nothing() -> None:
    pass


async def must_not_run() -> None:
    raise AssertionError("the abandoned action must not run")


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
            panel = panel_of(app, "mood")
            panel.open_confirm("Sure? y/n", run_nothing)
            await pilot.pause()
            assert panel.confirm_active is True
            assert panel.inline_active is True
            assert panel.input_active is False
            assert app.focused is panel.confirm_prompt
            assert panel.confirm_prompt.render().plain == "Sure? y/n"

    @pytest.mark.asyncio
    async def test_y_runs_the_action_once_and_refocuses_the_list(
        self, temp_beets_library: Library
    ) -> None:
        app = make_app(temp_beets_library, {"mood": ["happy"]})
        async with app.run_test() as pilot:
            panel = panel_of(app, "mood")
            ran: list[bool] = []

            async def run() -> None:
                ran.append(True)

            panel.open_confirm("Sure? y/n", run)
            await pilot.pause()
            await pilot.press("y")
            await pilot.pause()
            assert ran == [True]
            assert panel.confirm_active is False
            assert app.focused is panel.selection_list
            # A second ``y`` reaches the list, not a stale action.
            await pilot.press("y")
            await pilot.pause()
            assert ran == [True]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("key", ["n", "escape"])
    async def test_n_or_escape_closes_confirm_without_running(
        self, temp_beets_library: Library, key: str
    ) -> None:
        app = make_app(temp_beets_library, {"mood": ["happy"]})
        async with app.run_test() as pilot:
            panel = panel_of(app, "mood")
            panel.open_confirm("Sure? y/n", must_not_run)
            await pilot.pause()
            await pilot.press(key)
            await pilot.pause()
            assert panel.confirm_active is False
            assert app.focused is panel.selection_list
            assert app.is_running
            await pilot.press("y")
            await pilot.pause()

    @pytest.mark.asyncio
    async def test_ctrl_n_closes_an_open_confirm_and_drops_its_action(
        self, temp_beets_library: Library
    ) -> None:
        app = make_app(temp_beets_library, {"mood": ["happy"]})
        async with app.run_test() as pilot:
            panel = panel_of(app, "mood")
            panel.open_confirm("Sure? y/n", must_not_run)
            await pilot.pause()
            await pilot.press("ctrl+n")
            await pilot.pause()
            assert panel.confirm_active is False
            assert app.focused is app.query_one("#new-category-input", Input)
            await pilot.press("escape")
            await pilot.press("y")
            await pilot.pause()

    @pytest.mark.asyncio
    async def test_y_is_typed_into_an_open_input_not_confirmed(
        self, temp_beets_library: Library
    ) -> None:
        app = make_app(temp_beets_library, {"mood": ["happy"]})
        async with app.run_test() as pilot:
            await pilot.press("plus", "y")
            assert panel_of(app, "mood").input.value == "y"

    @pytest.mark.asyncio
    async def test_confirm_replaces_an_open_input_and_vice_versa(
        self, temp_beets_library: Library
    ) -> None:
        app = make_app(temp_beets_library, {"mood": ["happy"]})
        async with app.run_test() as pilot:
            panel = panel_of(app, "mood")
            await pilot.press("plus", "x")
            panel.open_confirm("Sure? y/n", must_not_run)
            await pilot.pause()
            assert panel.input_active is False
            assert panel.input.value == ""
            assert panel.confirm_active is True
            panel.open_input()
            await pilot.pause()
            assert panel.confirm_active is False
            assert panel.input_active is True
            assert app.focused is panel.input
            # Reopening the input forgot the action along with the prompt.
            panel.close_input()
            await pilot.press("y")
            await pilot.pause()

    @pytest.mark.asyncio
    async def test_confirm_in_one_panel_closes_input_in_another(
        self, temp_beets_library: Library
    ) -> None:
        app = make_app(temp_beets_library, {"mood": ["happy"], "vibe": ["afro"]})
        async with app.run_test() as pilot:
            await pilot.press("plus", "x")
            mood = panel_of(app, "mood")
            vibe = panel_of(app, "vibe")
            vibe.open_confirm("Sure? y/n", run_nothing)
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
            panel = panel_of(app, "mood")
            panel.open_input(EditKind.RENAME_OPTION, target="happy", initial="happy")
            await pilot.pause()
            assert panel.input.value == "happy"
            assert panel.input.cursor_position == 5
            assert "rename" in panel.input.placeholder
            assert panel.edit_kind is EditKind.RENAME_OPTION
            assert panel.edit_target == "happy"
            panel.close_input()
            assert panel.edit_kind is EditKind.ADD_OPTION
            assert panel.edit_target is None

    @pytest.mark.asyncio
    async def test_set_options_rebuilds_and_clamps_highlight(
        self, temp_beets_library: Library
    ) -> None:
        app = make_app(temp_beets_library, {"mood": ["happy", "sad", "calm"]})
        async with app.run_test() as pilot:
            panel = panel_of(app, "mood")
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


class TestHeaderMessages:
    @pytest.mark.asyncio
    async def test_show_message_replaces_the_title_until_cleared(
        self, temp_beets_library: Library
    ) -> None:
        app = make_app(temp_beets_library, {"mood": ["x"]})
        async with app.run_test() as pilot:
            title = header_text(app)
            app.header_widget.show_message("Library update failed")
            await pilot.pause()
            assert header_text(app) == "Library update failed"
            app.header_widget.update_header(app.item)
            assert header_text(app) == "Library update failed"
            app.header_widget.clear_message()
            assert header_text(app) == title

    @pytest.mark.asyncio
    async def test_track_change_clears_a_message(
        self, temp_beets_library: Library
    ) -> None:
        app = make_app(temp_beets_library, {"mood": ["x"]})
        async with app.run_test() as pilot:
            app.header_widget.show_message("Something happened")
            await pilot.press("right")
            await pilot.pause()
            assert header_text(app) == (
                f"Tagging: {app.item.artist} - {app.item.title}"
            )


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
    async def test_track_whose_value_was_removed_stays_current(
        self, temp_beets_library: Library
    ) -> None:
        first, second = tracks(temp_beets_library)[:2]
        set_field(temp_beets_library, first.id, "mood", "x")
        set_field(temp_beets_library, second.id, "mood", "x")
        queued = [temp_beets_library.get_item(item.id) for item in (first, second)]
        app = make_app(temp_beets_library, {"mood": ["x"]}, items=queued)
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
    async def test_reload_keeps_a_message_on_screen(
        self, temp_beets_library: Library
    ) -> None:
        app = make_app(temp_beets_library, {"mood": ["happy"]})
        async with app.run_test():
            stale = app.item
            app.header_widget.show_message("Could not write categories file")
            await app._reload_after_migration()
            assert app.header_widget.item is app.item
            assert app.header_widget.item is not stale
            assert header_text(app) == "Could not write categories file"

    @pytest.mark.asyncio
    async def test_queue_gone_from_the_library_is_reported_and_kept(
        self, temp_beets_library: Library
    ) -> None:
        app = make_app(temp_beets_library, {"mood": ["happy"]})
        async with app.run_test():
            held = list(app.items)
            for item in held:
                item.remove()
            await app._reload_after_migration()
            assert app.item is held[0]
            assert app.items == held
            assert "queued tracks" in header_text(app)


class TestMigrationKeepsTheQueue:
    @pytest.mark.asyncio
    async def test_rename_keeps_every_queued_track(
        self, temp_beets_library: Library
    ) -> None:
        """The session tags the tracks it was launched with, migration or not."""
        queued = tracks(temp_beets_library)[:3]
        for item in queued:
            set_field(temp_beets_library, item.id, "mood", "hiphop")
        app = make_app(
            temp_beets_library,
            {"mood": ["hiphop"]},
            items=[temp_beets_library.get_item(item.id) for item in queued],
        )
        async with app.run_test() as pilot:
            held = list(app.items)
            await start_edit(app, pilot, EditKind.RENAME_OPTION)
            await submit(app, pilot, "t", "r", "a", "p")
            await answer(app, pilot, "y")
            assert len(app.items) == 3
            assert [item.id for item in app.items] == [item.id for item in queued]
            assert all(item.get("mood") == "trap" for item in app.items)
            assert all(new is not old for new, old in zip(app.items, held, strict=True))
            assert app.items[app.current_item_index] is app.item

    @pytest.mark.asyncio
    async def test_edit_that_changes_no_track_keeps_the_same_items(
        self, temp_beets_library: Library
    ) -> None:
        app = make_app(temp_beets_library, {"mood": ["happy", "sad"]})
        async with app.run_test() as pilot:
            held = list(app.items)
            panel = await start_edit(app, pilot, EditKind.REMOVE_OPTION, index=1)
            await answer(app, pilot, "y")
            assert app.definitions.options("mood") == ["happy"]
            assert prompts(panel.selection_list) == ["happy"]
            assert app.items == held
            assert app.item is held[0]


class TestEditFlowsShared:
    """Behaviour every rename and delete flow has in common."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("kind", [EditKind.RENAME_OPTION, EditKind.RENAME_CATEGORY])
    async def test_unchanged_name_just_closes(
        self, temp_beets_library: Library, kind: EditKind
    ) -> None:
        app = make_app(temp_beets_library, {"mood": ["happy", "sad"]})
        async with app.run_test() as pilot:
            panel = await start_edit(app, pilot, kind, index=1)
            await pilot.press("enter")
            await settle(app, pilot)
            assert panel.inline_active is False
            assert app.focused is panel.selection_list
            assert app.definitions.to_mapping() == {"mood": ["happy", "sad"]}

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("kind", "typed", "message_part"),
        [
            (EditKind.RENAME_OPTION, [], "cannot be empty"),
            (EditKind.RENAME_OPTION, ["a", "comma", "b"], "cannot contain a comma"),
            (EditKind.RENAME_CATEGORY, [*"album"], "built-in beets field"),
            (EditKind.RENAME_CATEGORY, [*"vibe"], "already exists"),
            (EditKind.RENAME_CATEGORY, ["1", "x"], "letters, digits"),
        ],
    )
    async def test_invalid_name_shows_error_and_stays_open(
        self,
        temp_beets_library: Library,
        kind: EditKind,
        typed: list[str],
        message_part: str,
    ) -> None:
        app = make_app(temp_beets_library, {"mood": ["happy", "sad"], "vibe": ["afro"]})
        async with app.run_test() as pilot:
            panel = await start_edit(app, pilot, kind, index=1)
            await submit(app, pilot, *typed)
            assert panel.input_active is True
            assert message_part in panel.input.placeholder
            assert app.focused is panel.input
            assert app.definitions.to_mapping() == {
                "mood": ["happy", "sad"],
                "vibe": ["afro"],
            }

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("kind", "expected"),
        [
            (EditKind.RENAME_OPTION, "Rename 'sad' to 'x' on 1 tracks? y/n"),
            (EditKind.REMOVE_OPTION, "Delete 'sad' from 1 tracks? y/n"),
            (
                EditKind.RENAME_CATEGORY,
                "Rename category 'mood' to 'x' on 1 tracks? y/n",
            ),
            (
                EditKind.REMOVE_CATEGORY,
                "Delete category 'mood' and its values from 1 tracks? y/n",
            ),
        ],
    )
    async def test_pending_selection_is_saved_before_counting(
        self, temp_beets_library: Library, kind: EditKind, expected: str
    ) -> None:
        app = make_app(temp_beets_library, {"mood": ["happy", "sad"]})
        async with app.run_test() as pilot:
            app.query_one("#selection-mood", CustomSelectionList).select("sad")
            panel = await start_edit(app, pilot, kind, index=1)
            if panel.input_active:
                await submit(app, pilot, "x")
            assert panel.confirm_prompt.render().plain == expected
        assert temp_beets_library.get_item(app.item.id).get("mood") == "sad"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("key", ["n", "escape"])
    @pytest.mark.parametrize(
        "kind",
        [
            EditKind.RENAME_OPTION,
            EditKind.REMOVE_OPTION,
            EditKind.RENAME_CATEGORY,
            EditKind.REMOVE_CATEGORY,
        ],
    )
    async def test_n_or_escape_cancels(
        self, temp_beets_library: Library, kind: EditKind, key: str
    ) -> None:
        first = tracks(temp_beets_library)[0]
        set_field(temp_beets_library, first.id, "mood", "sad")
        app = make_app(temp_beets_library, {"mood": ["happy", "sad"]})
        async with app.run_test() as pilot:
            panel = await start_edit(app, pilot, kind, index=1)
            if panel.input_active:
                await submit(app, pilot, "x")
            assert panel.confirm_active is True
            await answer(app, pilot, key)
            assert panel.inline_active is False
            assert app.definitions.to_mapping() == {"mood": ["happy", "sad"]}
            assert panel.selection_list.selected == ["sad"]
            assert app.focused is panel.selection_list
            assert app.is_running
        assert temp_beets_library.get_item(first.id).get("mood") == "sad"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "kind",
        [
            EditKind.RENAME_OPTION,
            EditKind.REMOVE_OPTION,
            EditKind.RENAME_CATEGORY,
            EditKind.REMOVE_CATEGORY,
        ],
    )
    async def test_migration_failure_changes_nothing_and_says_so(
        self,
        temp_beets_library: Library,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        kind: EditKind,
    ) -> None:
        first = tracks(temp_beets_library)[0]
        set_field(temp_beets_library, first.id, "mood", "sad")
        path = tmp_path / "quicktag_categories.yaml"
        app = make_app(temp_beets_library, {"mood": ["happy", "sad"]}, path)

        def explode(*args: object, **kwargs: object) -> int:
            raise RuntimeError("disk on fire")

        monkeypatch.setattr(f"beetsplug.quicktag.app.{MIGRATION_FOR[kind]}", explode)
        async with app.run_test() as pilot:
            panel = await start_edit(app, pilot, kind, index=1)
            if panel.input_active:
                await submit(app, pilot, "x")
            await answer(app, pilot, "y")
            assert "Library update failed" in header_text(app)
            assert "disk on fire" in header_text(app)
            assert app.definitions.to_mapping() == {"mood": ["happy", "sad"]}
            assert [p.id for p in app.query(CategoryPanel)] == ["panel-mood"]
            assert prompts(panel.selection_list) == ["happy", "sad"]
            assert panel.selection_list.selected == ["sad"]
            assert panel.inline_active is False
            assert app.focused is panel.selection_list
            assert app.is_running
        assert not path.exists()
        assert temp_beets_library.get_item(first.id).get("mood") == "sad"

    @pytest.mark.asyncio
    async def test_header_says_the_library_is_being_updated(
        self, temp_beets_library: Library, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The message must reach the screen, so the migration cannot hold
        the event loop: reading the header from the migration's thread only
        completes if the loop is free to serve it."""
        app = make_app(temp_beets_library, {"mood": ["happy", "sad"]})
        seen: list[str] = []

        def slow_migration(*args: object, **kwargs: object) -> int:
            seen.append(app.call_from_thread(header_text, app))
            return 0

        monkeypatch.setattr("beetsplug.quicktag.app.remove_option", slow_migration)
        async with app.run_test() as pilot:
            await start_edit(app, pilot, EditKind.REMOVE_OPTION, index=1)
            await answer(app, pilot, "y")
            assert seen == ["Updating library…"]
            assert header_text(app) == (
                f"Tagging: {app.item.artist} - {app.item.title}"
            )

    @pytest.mark.asyncio
    async def test_unwritable_definitions_file_is_reported_and_the_track_reloaded(
        self, temp_beets_library: Library, tmp_path: Path
    ) -> None:
        """The library is updated whatever happens to the file afterwards,
        so the track must be reloaded or the next save writes the old value
        back; and the warning must outlive that reload."""
        first = tracks(temp_beets_library)[0]
        set_field(temp_beets_library, first.id, "mood", "sad")
        path = tmp_path / "missing" / "quicktag_categories.yaml"
        app = make_app(temp_beets_library, {"mood": ["happy", "sad"]}, path)
        async with app.run_test() as pilot:
            panel = await start_edit(app, pilot, EditKind.REMOVE_OPTION, index=1)
            await answer(app, pilot, "y")
            assert "Could not write categories file" in header_text(app)
            assert app.definitions.options("mood") == ["happy"]
            assert app.item.get("mood") is None
            assert panel.selection_list.selected == []
            assert app.is_running
            await pilot.press("right")
            await pilot.pause()
        assert not path.exists()
        assert "mood" not in temp_beets_library.get_item(first.id)


class TestTrackChangeWhileEditing:
    @pytest.mark.asyncio
    async def test_changing_track_withdraws_the_confirm(
        self, temp_beets_library: Library
    ) -> None:
        """Left/Right reach the app while the prompt has focus."""
        first = tracks(temp_beets_library)[0]
        set_field(temp_beets_library, first.id, "mood", "sad")
        app = make_app(temp_beets_library, {"mood": ["happy", "sad"]})
        async with app.run_test() as pilot:
            panel = await start_edit(app, pilot, EditKind.REMOVE_OPTION, index=1)
            assert panel.confirm_active is True
            await pilot.press("right")
            await pilot.pause()
            assert app.current_item_index == 1
            assert panel.confirm_active is False
            assert app.focused is panel.selection_list
            await answer(app, pilot, "y")
            assert app.definitions.options("mood") == ["happy", "sad"]
        assert temp_beets_library.get_item(first.id).get("mood") == "sad"


class TestRenameOptionFlow:
    @pytest.mark.asyncio
    async def test_f2_opens_input_prefilled_with_highlighted_option(
        self, temp_beets_library: Library
    ) -> None:
        app = make_app(temp_beets_library, {"mood": ["happy", "sad"]})
        async with app.run_test() as pilot:
            panel = await start_edit(app, pilot, EditKind.RENAME_OPTION, index=1)
            assert panel.input_active is True
            assert panel.input.value == "sad"
            assert app.focused is panel.input
            assert panel.edit_kind is EditKind.RENAME_OPTION
            assert "rename" in panel.input.placeholder

    @pytest.mark.asyncio
    async def test_rename_with_no_tracks_applies_immediately(
        self, temp_beets_library: Library, tmp_path: Path
    ) -> None:
        path = tmp_path / "quicktag_categories.yaml"
        app = make_app(temp_beets_library, {"mood": ["happy", "sad"]}, path)
        async with app.run_test() as pilot:
            panel = await start_edit(app, pilot, EditKind.RENAME_OPTION, index=1)
            await submit(app, pilot, "b", "l", "u", "e")
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
            panel = await start_edit(app, pilot, EditKind.RENAME_OPTION, index=1)
            await submit(app, pilot, "b", "l", "u", "e")
            assert panel.confirm_active is True
            assert panel.confirm_prompt.render().plain == (
                "Rename 'sad' to 'blue' on 2 tracks? y/n"
            )
            assert app.definitions.options("mood") == ["happy", "sad"]
            await answer(app, pilot, "y")
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
    async def test_merge_asks_and_uses_the_existing_spelling(
        self, temp_beets_library: Library
    ) -> None:
        first = tracks(temp_beets_library)[0]
        set_field(temp_beets_library, first.id, "mood", "Hiphop")
        app = make_app(temp_beets_library, {"mood": ["Hiphop", "Hip-Hop"]})
        async with app.run_test() as pilot:
            panel = await start_edit(app, pilot, EditKind.RENAME_OPTION)
            await submit(app, pilot, *"hip", "minus", *"hop")
            assert panel.confirm_prompt.render().plain == (
                "Merge 'Hiphop' into 'Hip-Hop' on 1 tracks? y/n"
            )
            await answer(app, pilot, "y")
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
            panel = await start_edit(app, pilot, EditKind.RENAME_OPTION)
            await submit(app, pilot, *"hip", "minus", *"hop")
            assert panel.confirm_active is True
            assert "0 tracks" in panel.confirm_prompt.render().plain

    @pytest.mark.asyncio
    async def test_merge_by_exact_spelling_is_still_a_merge(
        self, temp_beets_library: Library
    ) -> None:
        app = make_app(temp_beets_library, {"mood": ["Hiphop", "Hip-Hop"]})
        async with app.run_test() as pilot:
            panel = await start_edit(app, pilot, EditKind.RENAME_OPTION)
            await submit(app, pilot, *"Hip", "minus", *"Hop")
            assert panel.confirm_prompt.render().plain == (
                "Merge 'Hiphop' into 'Hip-Hop' on 0 tracks? y/n"
            )


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
            panel = await start_edit(app, pilot, EditKind.REMOVE_OPTION, index=1)
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
            panel = await start_edit(app, pilot, EditKind.REMOVE_OPTION, index=1)
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
            panel = await start_edit(app, pilot, EditKind.REMOVE_OPTION, index=1)
            await answer(app, pilot, "y")
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
    async def test_deleting_the_last_option_leaves_an_empty_list(
        self, temp_beets_library: Library
    ) -> None:
        app = make_app(temp_beets_library, {"mood": ["only"]})
        async with app.run_test() as pilot:
            panel = await start_edit(app, pilot, EditKind.REMOVE_OPTION)
            await answer(app, pilot, "y")
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
            vibe = await start_edit(app, pilot, EditKind.RENAME_CATEGORY, "vibe")
            assert vibe.input_active is True
            assert vibe.input.value == "vibe"
            assert vibe.edit_kind is EditKind.RENAME_CATEGORY
            assert app.focused is vibe.input
            assert "category" in vibe.input.placeholder

    @pytest.mark.asyncio
    async def test_rename_without_tracks_replaces_the_panel_in_place(
        self, temp_beets_library: Library, tmp_path: Path
    ) -> None:
        path = tmp_path / "quicktag_categories.yaml"
        app = make_app(temp_beets_library, {"mood": ["happy"], "vibe": ["afro"]}, path)
        async with app.run_test() as pilot:
            await start_edit(app, pilot, EditKind.RENAME_CATEGORY)
            await submit(app, pilot, *"feel")
            assert app.definitions.categories == ["feel", "vibe"]
            assert [p.id for p in app.query(CategoryPanel)] == [
                "panel-feel",
                "panel-vibe",
            ]
            feel = panel_of(app, "feel")
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
            mood = await start_edit(app, pilot, EditKind.RENAME_CATEGORY)
            await submit(app, pilot, *"feel")
            assert mood.confirm_prompt.render().plain == (
                "Rename category 'mood' to 'feel' on 2 tracks? y/n"
            )
            await answer(app, pilot, "y")
            feel = panel_of(app, "feel")
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
            await start_edit(app, pilot, EditKind.RENAME_CATEGORY)
            await submit(app, pilot, *"Mood")
            assert app.definitions.categories == ["Mood"]
            assert panel_of(app, "Mood").category == "Mood"

    @pytest.mark.asyncio
    async def test_built_in_text_field_cannot_be_renamed(
        self, temp_beets_library: Library
    ) -> None:
        """Moving every album title into a flex attr and blanking the field
        is not a rename anyone wants from one keystroke."""
        first = tracks(temp_beets_library)[0]
        set_field(temp_beets_library, first.id, "composer", "Bach")
        app = make_app(temp_beets_library, {"composer": ["Bach"]})
        async with app.run_test() as pilot:
            panel = await start_edit(app, pilot, EditKind.RENAME_CATEGORY, "composer")
            assert panel.inline_active is False
            assert "built-in beets field" in header_text(app)
            assert app.focused is panel.selection_list
            assert app.definitions.categories == ["composer"]
        assert temp_beets_library.get_item(first.id).get("composer") == "Bach"

    @needs_list_field
    @pytest.mark.asyncio
    async def test_genre_to_genres_moves_values_into_the_list_field(
        self, temp_beets_library: Library
    ) -> None:
        first = tracks(temp_beets_library)[0]
        set_field(temp_beets_library, first.id, "genre", "House, Techno")
        app = make_app(temp_beets_library, {"genre": ["House", "Techno"]})
        async with app.run_test() as pilot:
            genre = await start_edit(app, pilot, EditKind.RENAME_CATEGORY, "genre")
            await pilot.press("end", "s", "enter")
            await settle(app, pilot)
            assert "Rename category 'genre' to 'genres' on 1 tracks" in (
                genre.confirm_prompt.render().plain
            )
            await answer(app, pilot, "y")
            assert app.definitions.categories == [LIST_FIELD]
            genres = panel_of(app, LIST_FIELD)
            assert sorted(genres.selection_list.selected) == ["House", "Techno"]
        item = temp_beets_library.get_item(first.id)
        assert item[LIST_FIELD] == ["House", "Techno"]
        assert not item.get("genre")


class TestRemoveCategoryFlow:
    @pytest.mark.asyncio
    async def test_ctrl_d_asks_with_the_track_count(
        self, temp_beets_library: Library
    ) -> None:
        first = tracks(temp_beets_library)[0]
        set_field(temp_beets_library, first.id, "mood", "happy")
        app = make_app(temp_beets_library, {"mood": ["happy"]})
        async with app.run_test() as pilot:
            panel = await start_edit(app, pilot, EditKind.REMOVE_CATEGORY)
            assert panel.confirm_prompt.render().plain == (
                "Delete category 'mood' and its values from 1 tracks? y/n"
            )
            assert app.focused is panel.confirm_prompt

    @pytest.mark.asyncio
    async def test_y_removes_panel_values_and_focuses_the_next_panel(
        self, temp_beets_library: Library, tmp_path: Path
    ) -> None:
        first = tracks(temp_beets_library)[0]
        set_field(temp_beets_library, first.id, "mood", "happy")
        path = tmp_path / "quicktag_categories.yaml"
        app = make_app(
            temp_beets_library,
            {"mood": ["happy"], "vibe": ["afro"], "zest": ["z"]},
            path,
        )
        async with app.run_test() as pilot:
            await start_edit(app, pilot, EditKind.REMOVE_CATEGORY)
            await answer(app, pilot, "y")
            assert app.definitions.categories == ["vibe", "zest"]
            assert [p.id for p in app.query(CategoryPanel)] == [
                "panel-vibe",
                "panel-zest",
            ]
            assert app.focused is app.query_one("#selection-vibe")
            assert "mood" not in app.item
        assert "mood" not in temp_beets_library.get_item(first.id)
        assert read_definitions_file(path).categories == ["vibe", "zest"]

    @pytest.mark.asyncio
    async def test_deleting_the_last_panel_focuses_the_previous_one(
        self, temp_beets_library: Library
    ) -> None:
        app = make_app(temp_beets_library, {"mood": ["happy"], "vibe": ["afro"]})
        async with app.run_test() as pilot:
            await start_edit(app, pilot, EditKind.REMOVE_CATEGORY, "vibe")
            await answer(app, pilot, "y")
            assert app.definitions.categories == ["mood"]
            assert app.focused is app.query_one("#selection-mood")

    @pytest.mark.asyncio
    async def test_deleting_the_only_category_focuses_comments(
        self, temp_beets_library: Library
    ) -> None:
        app = make_app(temp_beets_library, {"mood": ["happy"]})
        async with app.run_test() as pilot:
            await start_edit(app, pilot, EditKind.REMOVE_CATEGORY)
            await answer(app, pilot, "y")
            assert app.definitions.categories == []
            assert list(app.query(CategoryPanel)) == []
            assert app.focused is app.query_one(
                "#comments-input", InputWithLabel
            ).query_one(Input)

    @pytest.mark.asyncio
    async def test_built_in_text_field_is_only_unlisted(
        self, temp_beets_library: Library, tmp_path: Path
    ) -> None:
        """The field holds data quicktag did not put there; one keystroke
        plus ``y`` must not blank it across the library."""
        first = tracks(temp_beets_library)[0]
        set_field(temp_beets_library, first.id, "composer", "Bach")
        path = tmp_path / "quicktag_categories.yaml"
        app = make_app(
            temp_beets_library, {"composer": ["Bach"], "mood": ["happy"]}, path
        )
        async with app.run_test() as pilot:
            panel = await start_edit(app, pilot, EditKind.REMOVE_CATEGORY, "composer")
            assert panel.confirm_prompt.render().plain == (
                "Remove category 'composer'? It is a built-in beets field, so "
                "every track keeps its value. y/n"
            )
            await answer(app, pilot, "y")
            assert app.definitions.categories == ["mood"]
            assert [p.id for p in app.query(CategoryPanel)] == ["panel-mood"]
            assert app.item.get("composer") == "Bach"
            assert app.focused is app.query_one("#selection-mood")
            await pilot.press("right")
            await pilot.pause()
        assert temp_beets_library.get_item(first.id).get("composer") == "Bach"
        assert read_definitions_file(path).categories == ["mood"]
