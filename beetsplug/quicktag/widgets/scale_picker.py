"""A one-row picker for a scale category: one cell per step, one value.

Digits set the value, Up/Down step it, Delete clears it. A stored value
that is not one of the steps (``foreign``) is shown after the row and left
alone until the user picks a value or clears it.
"""

from __future__ import annotations

from textual import events
from textual.binding import Binding
from textual.content import Content
from textual.reactive import reactive
from textual.widget import Widget

from ..definitions import Scale
from .custom_selection_list import EditKind, EditRequested

DIGITS = "0123456789"


class ScalePicker(Widget):
    DEFAULT_CSS = """
    ScalePicker {
        height: 1;
        width: 100%;
    }
    """

    can_focus = True

    # Left/Right are rebound for the same reason as on CustomSelectionList:
    # the footer lists the focused widget's bindings, so the App's
    # Previous/Next entries would otherwise disappear while a picker has
    # focus. Digits are handled in ``on_key``: ten footer entries would say
    # nothing the row itself does not.
    BINDINGS = [
        Binding("left", "app.previous_item", "Previous"),
        Binding("right", "app.next_item", "Next"),
        Binding("up", "step(1)", "Higher"),
        Binding("down", "step(-1)", "Lower"),
        Binding("delete,backspace", "clear", "Clear"),
        Binding(
            "ctrl+r",
            f"request_edit('{EditKind.RENAME_CATEGORY.value}')",
            "Rename category",
        ),
        Binding(
            "ctrl+d",
            f"request_edit('{EditKind.REMOVE_CATEGORY.value}')",
            "Delete category",
        ),
    ]

    value: reactive[int | None] = reactive(None)
    foreign: reactive[str | None] = reactive(None)

    def __init__(self, scale: Scale, *, id: str) -> None:
        super().__init__(id=id)
        self.scale = scale

    def load(self, raw: str | None) -> None:
        """Show the stored text ``raw``: a value inside the scale, or a
        foreign one that is displayed but not selectable."""
        self.value = self.scale.parse_value(raw)
        self.foreign = None if raw is None or self.value is not None else raw

    def set_value(self, value: int | None) -> None:
        """Pick ``value`` (or nothing), dropping any foreign value."""
        self.value = value
        self.foreign = None

    def action_step(self, delta: int) -> None:
        if self.value is None:
            self.set_value(self.scale.low if delta > 0 else self.scale.high)
            return
        self.set_value(max(self.scale.low, min(self.scale.high, self.value + delta)))

    def action_clear(self) -> None:
        self.set_value(None)

    def action_request_edit(self, kind_name: str) -> None:
        self.post_message(EditRequested(EditKind(kind_name), None))

    async def on_key(self, event: events.Key) -> None:
        """A digit picks that step; a digit outside the scale does nothing."""
        if event.character is None or event.character not in DIGITS:
            return
        event.stop()
        digit = int(event.character)
        if digit in self.scale.steps():
            self.set_value(digit)

    def render(self) -> Content:
        cells = [
            Content.styled(f" {step} ", "reverse bold")
            if step == self.value
            else Content(f" {step} ")
            for step in self.scale.steps()
        ]
        line = Content(" ").join(cells)
        if self.foreign is not None:
            line = Content.assemble(
                line, Content.styled(f"  stored: {self.foreign}", "dim")
            )
        return line
