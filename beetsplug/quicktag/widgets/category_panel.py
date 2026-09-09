"""One category: its selection list plus a one-line inline area beneath it.

The inline area is either an ``Input`` (add an option, rename an option,
rename the category) or a ``ConfirmPrompt`` (a y/n question before a
delete or a migration). When idle the panel looks exactly like the bare list
did: the border and title that used to be on the list live on the panel, and
both inline widgets are hidden.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.content import Content
from textual.message import Message
from textual.widgets import Input, Static
from textual.widgets.selection_list import Selection

from .custom_selection_list import CustomSelectionList, EditKind
from .inline_input import InlineInput

OPTION_PLACEHOLDER = "New option, Enter to add, Esc to cancel"
RENAME_OPTION_PLACEHOLDER = "New name, Enter to rename, Esc to cancel"
RENAME_CATEGORY_PLACEHOLDER = "New category name, Enter to rename, Esc to cancel"

_PLACEHOLDERS = {
    EditKind.ADD_OPTION: OPTION_PLACEHOLDER,
    EditKind.RENAME_OPTION: RENAME_OPTION_PLACEHOLDER,
    EditKind.RENAME_CATEGORY: RENAME_CATEGORY_PLACEHOLDER,
}


class ConfirmPrompt(Static):
    """A one-line y/n question. Focusable so ``y``/``n`` bind and show in
    the footer, and so the list's letter-jump handler never sees them."""

    can_focus = True

    BINDINGS = [
        Binding("y", "answer(True)", "Yes"),
        Binding("n", "answer(False)", "No"),
    ]

    class Answered(Message):
        def __init__(self, confirmed: bool) -> None:
            super().__init__()
            self.confirmed = confirmed

    def action_answer(self, confirmed: bool) -> None:
        self.post_message(self.Answered(confirmed))


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
    CategoryPanel > InlineInput,
    CategoryPanel > ConfirmPrompt {
        margin-top: 1;
    }
    CategoryPanel > ConfirmPrompt {
        height: 1;
        padding: 0 1;
    }
    """

    class InlineSubmitted(Message):
        """The user pressed Enter in the panel's inline input."""

        def __init__(
            self, panel: CategoryPanel, kind: EditKind, target: str | None, value: str
        ) -> None:
            super().__init__()
            self.panel = panel
            self.kind = kind
            self.target = target
            self.value = value

    class EditRequested(Message):
        """The user pressed an editing key that needs the app (everything
        except adding an option, which the panel handles itself)."""

        def __init__(
            self, panel: CategoryPanel, kind: EditKind, value: str | None
        ) -> None:
            super().__init__()
            self.panel = panel
            self.kind = kind
            self.value = value

    class Confirmed(Message):
        """The user answered ``y``; ``run`` is what they agreed to."""

        def __init__(
            self, panel: CategoryPanel, run: Callable[[], Awaitable[None]]
        ) -> None:
            super().__init__()
            self.panel = panel
            self.run = run

    class InputOpened(Message):
        """The panel's inline line (input or confirm) has just been revealed.

        Whoever owns the screen decides what else must close; the panel only
        announces it.
        """

        def __init__(self, panel: CategoryPanel) -> None:
            super().__init__()
            self.panel = panel

    def __init__(self, category: str, options: list[str]) -> None:
        super().__init__(id=f"panel-{category}")
        self.category = category
        self._initial_options = list(options)
        self.border_title = Content(category)
        # What the inline input is open for. ``ADD_OPTION`` is the resting
        # value, matching the input's idle placeholder.
        self.edit_kind: EditKind = EditKind.ADD_OPTION
        self.edit_target: str | None = None
        # What ``y`` on the confirm prompt runs; dropped whenever the prompt
        # closes, however it closes.
        self._confirm_run: Callable[[], Awaitable[None]] | None = None

    def compose(self) -> ComposeResult:
        yield CustomSelectionList(
            *(Selection(Content(option), option) for option in self._initial_options),
            id=f"selection-{self.category}",
        )
        yield InlineInput(id=f"input-{self.category}", placeholder=OPTION_PLACEHOLDER)
        prompt = ConfirmPrompt(id=f"confirm-{self.category}", markup=False)
        prompt.display = False
        yield prompt

    # ---- children ------------------------------------------------------------

    @property
    def selection_list(self) -> CustomSelectionList:
        return self.query_one(CustomSelectionList)

    @property
    def input(self) -> InlineInput:
        return self.query_one(InlineInput)

    @property
    def confirm_prompt(self) -> ConfirmPrompt:
        return self.query_one(ConfirmPrompt)

    @property
    def input_active(self) -> bool:
        return self.input.active

    @property
    def confirm_active(self) -> bool:
        return bool(self.confirm_prompt.display)

    @property
    def inline_active(self) -> bool:
        return self.input_active or self.confirm_active

    # ---- inline input ----------------------------------------------------------

    def open_input(
        self,
        kind: EditKind = EditKind.ADD_OPTION,
        *,
        target: str | None = None,
        initial: str = "",
    ) -> None:
        """Reveal the input for ``kind``; ``target`` is the option being renamed."""
        if self.confirm_active:
            self.close_confirm(refocus=False)
        self.edit_kind = kind
        self.edit_target = target
        inline_input = self.input
        inline_input.open(_PLACEHOLDERS[kind])
        inline_input.value = initial
        inline_input.cursor_position = len(initial)
        self.post_message(self.InputOpened(self))

    def close_input(self, *, refocus: bool = True) -> None:
        """Hide and clear the input; ``refocus`` moves focus back to the list.

        Closing an input that never had focus (because another one is taking
        over) must not steal focus, hence ``refocus=False``.
        """
        self.input.close()
        self.edit_kind = EditKind.ADD_OPTION
        self.edit_target = None
        if refocus:
            self.selection_list.focus()

    def show_error(self, message: str) -> None:
        """Show ``message`` on the input line and keep it open for a retry."""
        self.input.show_error(message)

    # ---- confirm prompt ----------------------------------------------------------

    def open_confirm(self, question: str, run: Callable[[], Awaitable[None]]) -> None:
        """Replace the inline line with a y/n ``question``; ``y`` runs ``run``."""
        if self.input_active:
            self.close_input(refocus=False)
        self._confirm_run = run
        prompt = self.confirm_prompt
        prompt.update(question)
        prompt.display = True
        prompt.focus()
        self.post_message(self.InputOpened(self))

    def close_confirm(self, *, refocus: bool = True) -> None:
        """Hide the prompt and forget what it would have run."""
        self._confirm_run = None
        prompt = self.confirm_prompt
        prompt.display = False
        prompt.update("")
        if refocus:
            self.selection_list.focus()

    def close_inline(self, *, refocus: bool = True) -> None:
        """Close whichever inline line is open, if any."""
        if self.input_active:
            self.close_input(refocus=refocus)
        if self.confirm_active:
            self.close_confirm(refocus=refocus)

    # ---- options ---------------------------------------------------------------

    def add_option(self, value: str, *, select: bool) -> None:
        """Append ``value`` to the list, highlight it and optionally select it."""
        selection_list = self.selection_list
        selection_list.add_option(Selection(Content(value), value))
        selection_list.highlighted = selection_list.option_count - 1
        if select:
            selection_list.select(value)
        selection_list.scroll_to_highlight()

    def set_options(self, options: list[str], *, highlighted: int | None) -> None:
        """Rebuild the list from ``options`` with nothing selected.

        The caller reloads the track's selections afterwards. ``highlighted``
        is the index to restore, clamped to the new length.
        """
        selection_list = self.selection_list
        selection_list.clear_options()
        selection_list.add_options(
            Selection(Content(option), option) for option in options
        )
        if options and highlighted is not None:
            selection_list.highlighted = min(highlighted, len(options) - 1)
            selection_list.scroll_to_highlight()

    # ---- messages ----------------------------------------------------------------

    def on_custom_selection_list_edit_requested(
        self, message: CustomSelectionList.EditRequested
    ) -> None:
        message.stop()
        if message.kind is EditKind.ADD_OPTION:
            self.open_input()
            return
        self.post_message(self.EditRequested(self, message.kind, message.value))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        # Stop here so the app's handler only ever sees its own new-category
        # input's submissions.
        event.stop()
        self.post_message(
            self.InlineSubmitted(self, self.edit_kind, self.edit_target, event.value)
        )

    def on_confirm_prompt_answered(self, message: ConfirmPrompt.Answered) -> None:
        message.stop()
        run = self._confirm_run
        self.close_confirm()
        if message.confirmed and run is not None:
            self.post_message(self.Confirmed(self, run))
