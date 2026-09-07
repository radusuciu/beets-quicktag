"""One category: its selection list plus an inline input for adding options.

When idle the panel looks exactly like the bare list did: the border and
title that used to be on the list live on the panel, and the input is hidden.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.content import Content
from textual.message import Message
from textual.widgets import Input
from textual.widgets.selection_list import Selection

from .custom_selection_list import CustomSelectionList

OPTION_PLACEHOLDER = "New option, Enter to add, Esc to cancel"


class CategoryPanel(Vertical):
    DEFAULT_CSS = """
    CategoryPanel {
        height: auto;
        padding: 1;
        border: solid $accent;
    }
    CategoryPanel:focus-within {
        border: tall $border;
    }
    CategoryPanel > CustomSelectionList,
    CategoryPanel > CustomSelectionList:focus {
        border: none;
        padding: 0;
    }
    CategoryPanel > Input,
    CategoryPanel > Input:focus {
        height: 1;
        border: none;
        padding: 0 1;
        margin-top: 1;
    }
    """

    class OptionSubmitted(Message):
        """The user pressed Enter in the panel's inline input."""

        def __init__(self, panel: CategoryPanel, value: str) -> None:
            super().__init__()
            self.panel = panel
            self.value = value

    def __init__(self, category: str, options: list[str]) -> None:
        super().__init__(id=f"panel-{category}")
        self.category = category
        self._initial_options = list(options)
        self.border_title = Content(category)

    def compose(self) -> ComposeResult:
        yield CustomSelectionList(
            *(Selection(Content(option), option) for option in self._initial_options),
            id=f"selection-{self.category}",
        )
        inline_input = Input(
            id=f"input-{self.category}", placeholder=OPTION_PLACEHOLDER
        )
        inline_input.display = False
        yield inline_input

    # ---- children ------------------------------------------------------------

    @property
    def selection_list(self) -> CustomSelectionList:
        return self.query_one(CustomSelectionList)

    @property
    def input(self) -> Input:
        return self.query_one(Input)

    @property
    def input_active(self) -> bool:
        return bool(self.input.display)

    # ---- inline input ----------------------------------------------------------

    def open_input(self, placeholder: str = OPTION_PLACEHOLDER) -> None:
        inline_input = self.input
        inline_input.value = ""
        inline_input.placeholder = placeholder
        inline_input.display = True
        inline_input.focus()

    def close_input(self) -> None:
        inline_input = self.input
        inline_input.display = False
        inline_input.value = ""
        inline_input.placeholder = OPTION_PLACEHOLDER
        self.selection_list.focus()

    def show_error(self, message: str) -> None:
        """Show ``message`` on the input line and keep it open for a retry."""
        inline_input = self.input
        inline_input.value = ""
        inline_input.placeholder = message
        inline_input.focus()

    # ---- options ---------------------------------------------------------------

    def add_option(self, value: str, *, select: bool) -> None:
        """Append ``value`` to the list, highlight it and optionally select it."""
        selection_list = self.selection_list
        selection_list.add_option(Selection(Content(value), value))
        selection_list.highlighted = selection_list.option_count - 1
        if select:
            selection_list.select(value)
        selection_list.scroll_to_highlight()

    # ---- messages ----------------------------------------------------------------

    def on_custom_selection_list_add_option_requested(
        self, message: CustomSelectionList.AddOptionRequested
    ) -> None:
        message.stop()
        self.open_input()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        # Stop here so the app's handler only ever sees its own new-category
        # input's submissions.
        event.stop()
        self.post_message(self.OptionSubmitted(self, event.value))
