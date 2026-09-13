"""Scale categories in the TUI: panels, values, focus, rename and delete."""

from pathlib import Path

import pytest
from beets.library import Item, Library
from textual.app import App, ComposeResult
from textual.widgets import Input

from beetsplug.quicktag.definitions import Scale
from beetsplug.quicktag.definitions_file import read_definitions_file
from beetsplug.quicktag.widgets.category_panel import (
    CategoryPanel,
    ConfirmPrompt,
    ScalePanel,
)
from beetsplug.quicktag.widgets.custom_selection_list import CustomSelectionList
from beetsplug.quicktag.widgets.scale_picker import ScalePicker
from conftest import (
    item_id,
    make_app,
    rendered_text,
    settle,
    stored_item,
    wait_for_footer_keys,
)


class PanelHost(App[None]):
    """A bare app around one scale panel."""

    def compose(self) -> ComposeResult:
        yield ScalePanel("energy", Scale(1, 5))


class TestScalePanel:
    @pytest.mark.asyncio
    async def test_composes_a_picker_with_the_category_ids(self) -> None:
        host = PanelHost()
        async with host.run_test():
            panel = host.query_one("#panel-energy", ScalePanel)
            assert isinstance(panel, CategoryPanel)
            assert panel.category == "energy"
            assert str(panel.border_title) == "energy"
            picker = host.query_one("#scale-energy", ScalePicker)
            assert panel.picker is picker
            assert picker.scale == Scale(1, 5)
            assert not panel.query(CustomSelectionList)

    @pytest.mark.asyncio
    async def test_focus_body_focuses_the_picker(self) -> None:
        host = PanelHost()
        async with host.run_test() as pilot:
            panel = host.query_one(ScalePanel)
            panel.focus_body()
            await pilot.pause()
            assert host.focused is panel.picker

    @pytest.mark.asyncio
    async def test_closing_the_input_refocuses_the_picker(self) -> None:
        host = PanelHost()
        async with host.run_test() as pilot:
            panel = host.query_one(ScalePanel)
            panel.open_input(initial="energy")
            await pilot.pause()
            assert isinstance(host.focused, Input)
            panel.close_input()
            await pilot.pause()
            assert host.focused is panel.picker


def first_item(lib: Library) -> Item:
    return next(iter(lib.items()))


class TestScaleInTheApp:
    @pytest.mark.asyncio
    async def test_scale_gets_a_scale_panel_in_file_order(
        self, temp_beets_library: Library
    ) -> None:
        app = make_app(
            temp_beets_library, {"mood": ["happy"], "energy": "1..5", "vibe": ["dark"]}
        )
        async with app.run_test():
            panels = list(app.query(CategoryPanel))
            assert [panel.category for panel in panels] == ["mood", "energy", "vibe"]
            assert isinstance(panels[1], ScalePanel)
            assert not isinstance(panels[0], ScalePanel)

    @pytest.mark.asyncio
    async def test_picker_has_focus_on_mount_when_the_scale_comes_first(
        self, temp_beets_library: Library
    ) -> None:
        app = make_app(temp_beets_library, {"energy": "1..5", "mood": ["happy"]})
        async with app.run_test() as pilot:
            await pilot.pause()
            assert app.focused is app.query_one("#scale-energy", ScalePicker)

    @pytest.mark.asyncio
    async def test_tab_moves_from_the_picker_to_the_next_list(
        self, temp_beets_library: Library
    ) -> None:
        app = make_app(temp_beets_library, {"energy": "1..5", "mood": ["happy"]})
        async with app.run_test() as pilot:
            await pilot.press("tab")
            assert app.focused is app.query_one("#selection-mood", CustomSelectionList)

    @pytest.mark.asyncio
    async def test_footer_lists_the_picker_keys(
        self, temp_beets_library: Library
    ) -> None:
        app = make_app(temp_beets_library, {"energy": "1..5"})
        wanted = {"up", "down", "delete", "left", "right"}
        async with app.run_test() as pilot:
            keys = await wait_for_footer_keys(pilot, lambda shown: wanted <= shown)
            assert wanted <= keys

    @pytest.mark.asyncio
    async def test_digit_then_save_stores_the_text(
        self, temp_beets_library: Library
    ) -> None:
        app = make_app(temp_beets_library, {"energy": "1..5"})
        async with app.run_test() as pilot:
            await pilot.press("4")
            await app._save_current_item_tags()
            current = item_id(app.item)
        assert stored_item(temp_beets_library, current).get("energy") == "4"

    @pytest.mark.asyncio
    async def test_clearing_deletes_the_attribute(
        self, temp_beets_library: Library
    ) -> None:
        item = first_item(temp_beets_library)
        item["energy"] = "4"
        item.store()
        app = make_app(temp_beets_library, {"energy": "1..5"})
        async with app.run_test() as pilot:
            assert app.query_one(ScalePicker).value == 4
            await pilot.press("delete")
            await app._save_current_item_tags()
            current = item_id(app.item)
        stored = stored_item(temp_beets_library, current)
        assert "energy" not in stored.keys(with_album=False)

    @pytest.mark.asyncio
    async def test_stored_value_is_shown_and_resaving_changes_nothing(
        self, temp_beets_library: Library, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        item = first_item(temp_beets_library)
        item["energy"] = "3"
        item.store()
        app = make_app(temp_beets_library, {"energy": "1..5"})
        stores: list[str] = []
        async with app.run_test():
            assert app.query_one(ScalePicker).value == 3
            monkeypatch.setattr(app.item, "store", lambda *a, **k: stores.append("s"))
            await app._save_current_item_tags()
        assert stores == []

    @pytest.mark.asyncio
    async def test_foreign_value_is_shown_kept_and_replaceable(
        self, temp_beets_library: Library
    ) -> None:
        item = first_item(temp_beets_library)
        item["energy"] = "high"
        item.store()
        app = make_app(temp_beets_library, {"energy": "1..5"})
        async with app.run_test() as pilot:
            picker = app.query_one(ScalePicker)
            assert picker.value is None
            assert picker.foreign == "high"
            await app._save_current_item_tags()
            current = item_id(app.item)
            assert stored_item(temp_beets_library, current).get("energy") == "high"
            await pilot.press("4")
            await app._save_current_item_tags()
        assert stored_item(temp_beets_library, current).get("energy") == "4"

    @pytest.mark.asyncio
    async def test_moving_track_saves_and_loads_each_tracks_value(
        self, temp_beets_library: Library
    ) -> None:
        items = list(temp_beets_library.items())
        assert len(items) >= 2
        items[1]["energy"] = "2"
        items[1].store()
        app = make_app(temp_beets_library, {"energy": "1..5"})
        async with app.run_test() as pilot:
            first = item_id(app.item)
            await pilot.press("5", "right")
            await settle(app, pilot)
            assert app.query_one(ScalePicker).value == 2
            await pilot.press("left")
            await settle(app, pilot)
            assert app.query_one(ScalePicker).value == 5
        assert stored_item(temp_beets_library, first).get("energy") == "5"

    @pytest.mark.asyncio
    async def test_new_list_category_is_added_below_a_scale(
        self, temp_beets_library: Library, tmp_path: Path
    ) -> None:
        path = tmp_path / "quicktag_categories.yaml"
        app = make_app(temp_beets_library, {"energy": "1..5"}, path)
        async with app.run_test() as pilot:
            await pilot.press("ctrl+n", *"mood", "enter")
            await settle(app, pilot)
            names = [panel.category for panel in app.query(CategoryPanel)]
            assert names == ["energy", "mood"]
        assert read_definitions_file(path).to_mapping() == {
            "energy": "1..5",
            "mood": [],
        }


class TestRenameAndDeleteScale:
    @pytest.mark.asyncio
    async def test_rename_moves_values_and_rebuilds_the_panel(
        self, temp_beets_library: Library, tmp_path: Path
    ) -> None:
        items = list(temp_beets_library.items())
        items[1]["energy"] = "3"
        items[1].store()
        path = tmp_path / "quicktag_categories.yaml"
        app = make_app(temp_beets_library, {"energy": "1..5"}, path)
        async with app.run_test() as pilot:
            await pilot.press("5", "ctrl+r")
            await settle(app, pilot)
            await pilot.press("ctrl+u", *"power", "enter")
            await settle(app, pilot)
            prompt = app.query_one(ConfirmPrompt)
            assert "on 2 tracks" in rendered_text(prompt)
            await pilot.press("y")
            await settle(app, pilot)
            assert [p.category for p in app.query(CategoryPanel)] == ["power"]
            panel = app.query_one("#panel-power", ScalePanel)
            assert panel.scale == Scale(1, 5)
            assert panel.picker.value == 5
            assert app.focused is panel.picker
            current = item_id(app.item)
        assert stored_item(temp_beets_library, current).get("power") == "5"
        assert stored_item(temp_beets_library, item_id(items[1])).get("power") == "3"
        assert read_definitions_file(path).scale("power") == Scale(1, 5)

    @pytest.mark.asyncio
    async def test_delete_clears_values_and_removes_the_panel(
        self, temp_beets_library: Library, tmp_path: Path
    ) -> None:
        item = first_item(temp_beets_library)
        item["energy"] = "2"
        item.store()
        path = tmp_path / "quicktag_categories.yaml"
        app = make_app(temp_beets_library, {"energy": "1..5", "mood": ["a"]}, path)
        async with app.run_test() as pilot:
            await pilot.press("ctrl+d")
            await settle(app, pilot)
            prompt = app.query_one("#confirm-energy", ConfirmPrompt)
            assert "from 1 tracks" in rendered_text(prompt)
            await pilot.press("y")
            await settle(app, pilot)
            assert [p.category for p in app.query(CategoryPanel)] == ["mood"]
            assert app.focused is app.query_one("#selection-mood", CustomSelectionList)
            current = item_id(app.item)
        stored = stored_item(temp_beets_library, current)
        assert "energy" not in stored.keys(with_album=False)
        assert read_definitions_file(path).categories == ["mood"]

    @pytest.mark.asyncio
    async def test_delete_prompt_counts_the_unsaved_pick(
        self, temp_beets_library: Library
    ) -> None:
        app = make_app(temp_beets_library, {"energy": "1..5"})
        async with app.run_test() as pilot:
            await pilot.press("3", "ctrl+d")
            await settle(app, pilot)
            assert "from 1 tracks" in rendered_text(app.query_one(ConfirmPrompt))
            await pilot.press("n")
            await settle(app, pilot)
            assert app.query_one(ScalePicker).value == 3

    @pytest.mark.asyncio
    async def test_rename_onto_a_built_in_field_shows_the_error(
        self, temp_beets_library: Library
    ) -> None:
        app = make_app(temp_beets_library, {"energy": "1..5"})
        async with app.run_test() as pilot:
            await pilot.press("ctrl+r")
            await settle(app, pilot)
            await pilot.press("ctrl+u", *"genres", "enter")
            await settle(app, pilot)
            panel = app.query_one("#panel-energy", ScalePanel)
            assert panel.input_active
            assert "built-in beets field" in panel.input.placeholder
