"""Scale categories in the TUI: panels, values, focus, rename and delete."""

import pytest
from textual.app import App, ComposeResult
from textual.widgets import Input

from beetsplug.quicktag.definitions import Scale
from beetsplug.quicktag.widgets.category_panel import (
    CategoryPanel,
    ScalePanel,
)
from beetsplug.quicktag.widgets.custom_selection_list import CustomSelectionList
from beetsplug.quicktag.widgets.scale_picker import ScalePicker


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
