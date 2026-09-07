"""Renaming and deleting options and categories from the TUI, with the
library migration that goes with them."""

from pathlib import Path

import pytest
from beets.library import Item, Library
from textual.app import App, ComposeResult
from textual.widgets import Static
from textual.widgets.selection_list import Selection

from beetsplug.quicktag.app import QuickTagApp
from beetsplug.quicktag.definitions import CategoryDefinitions
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
