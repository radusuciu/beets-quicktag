"""The one-row picker for a scale category, outside any panel."""

import pytest
from textual.app import App, ComposeResult

from beetsplug.quicktag.definitions import Scale
from beetsplug.quicktag.widgets.custom_selection_list import EditKind, EditRequested
from beetsplug.quicktag.widgets.scale_picker import ScalePicker


class PickerHost(App[None]):
    """A bare app around one picker, to test its keys without the panel."""

    def __init__(self, scale: Scale = Scale(1, 5)) -> None:
        super().__init__()
        self._scale = scale
        self.requests: list[EditKind] = []

    def compose(self) -> ComposeResult:
        yield ScalePicker(self._scale, id="scale-energy")

    def on_edit_requested(self, message: EditRequested) -> None:
        self.requests.append(message.kind)


def picker(host: PickerHost) -> ScalePicker:
    return host.query_one(ScalePicker)


class TestKeys:
    @pytest.mark.asyncio
    async def test_digit_sets_the_value(self) -> None:
        host = PickerHost()
        async with host.run_test() as pilot:
            picker(host).focus()
            await pilot.press("4")
            assert picker(host).value == 4

    @pytest.mark.asyncio
    async def test_digit_outside_the_scale_is_ignored(self) -> None:
        host = PickerHost()
        async with host.run_test() as pilot:
            picker(host).focus()
            await pilot.press("3", "9", "0")
            assert picker(host).value == 3

    @pytest.mark.asyncio
    async def test_up_and_down_step_and_saturate(self) -> None:
        host = PickerHost()
        async with host.run_test() as pilot:
            picker(host).focus()
            await pilot.press("up")
            assert picker(host).value == 1
            await pilot.press("up", "up", "up", "up", "up")
            assert picker(host).value == 5
            await pilot.press("down")
            assert picker(host).value == 4

    @pytest.mark.asyncio
    async def test_down_from_unset_gives_the_top(self) -> None:
        host = PickerHost()
        async with host.run_test() as pilot:
            picker(host).focus()
            await pilot.press("down")
            assert picker(host).value == 5

    @pytest.mark.asyncio
    @pytest.mark.parametrize("key", ["delete", "backspace"])
    async def test_delete_and_backspace_clear(self, key: str) -> None:
        host = PickerHost()
        async with host.run_test() as pilot:
            picker(host).focus()
            await pilot.press("2", key)
            assert picker(host).value is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("key", "kind"),
        [("ctrl+r", EditKind.RENAME_CATEGORY), ("ctrl+d", EditKind.REMOVE_CATEGORY)],
    )
    async def test_category_keys_post_edit_requested(
        self, key: str, kind: EditKind
    ) -> None:
        host = PickerHost()
        async with host.run_test() as pilot:
            picker(host).focus()
            await pilot.press(key)
            await pilot.pause()
            assert host.requests == [kind]


class TestStoredValues:
    @pytest.mark.asyncio
    async def test_load_inside_the_scale(self) -> None:
        host = PickerHost()
        async with host.run_test():
            picker(host).load("3")
            assert picker(host).value == 3
            assert picker(host).foreign is None

    @pytest.mark.asyncio
    async def test_load_outside_the_scale_is_foreign(self) -> None:
        host = PickerHost()
        async with host.run_test():
            picker(host).load("high")
            assert picker(host).value is None
            assert picker(host).foreign == "high"
            assert "stored: high" in picker(host).render().plain

    @pytest.mark.asyncio
    async def test_setting_a_value_drops_the_foreign_one(self) -> None:
        host = PickerHost()
        async with host.run_test() as pilot:
            picker(host).load("high")
            picker(host).focus()
            await pilot.press("4")
            assert picker(host).value == 4
            assert picker(host).foreign is None

    @pytest.mark.asyncio
    async def test_delete_drops_the_foreign_one(self) -> None:
        host = PickerHost()
        async with host.run_test() as pilot:
            picker(host).load("high")
            picker(host).focus()
            await pilot.press("delete")
            assert picker(host).foreign is None
            assert picker(host).value is None

    @pytest.mark.asyncio
    async def test_load_none_clears(self) -> None:
        host = PickerHost()
        async with host.run_test():
            picker(host).load("3")
            picker(host).load(None)
            assert picker(host).value is None
            assert picker(host).foreign is None


class TestRender:
    @pytest.mark.asyncio
    async def test_every_step_is_shown(self) -> None:
        host = PickerHost(Scale(0, 10))
        async with host.run_test():
            plain = picker(host).render().plain
            for step in range(11):
                assert f" {step} " in plain
