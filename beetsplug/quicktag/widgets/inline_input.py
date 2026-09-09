"""A one-line input that stays hidden until something needs it.

The panels' add-option line and the app's new-category line are both one
of these, so revealing, closing and showing a validation error work the
same way in both places.
"""

from __future__ import annotations

from textual.widgets import Input


class InlineInput(Input):
    DEFAULT_CSS = """
    InlineInput, InlineInput:focus {
        height: 1;
        border: none;
        padding: 0 1;
    }
    """

    def __init__(self, *, id: str, placeholder: str) -> None:
        super().__init__(id=id, placeholder=placeholder)
        self._idle_placeholder = placeholder
        self.display = False

    @property
    def active(self) -> bool:
        """True while the input is shown."""
        return bool(self.display)

    def open(self, placeholder: str | None = None) -> None:
        """Reveal the input empty, showing ``placeholder`` (default: the idle
        one), and focus it."""
        self.value = ""
        self.placeholder = placeholder or self._idle_placeholder
        self.display = True
        self.focus()

    def close(self) -> None:
        """Hide and clear the input.

        Hiding a focused widget drops focus; where it should go next depends
        on the owner, so that is left to the caller.
        """
        self.display = False
        self.value = ""
        self.placeholder = self._idle_placeholder

    def show_error(self, message: str) -> None:
        """Show ``message`` on the input line and keep it open for a retry."""
        self.value = ""
        self.placeholder = message
        self.focus()

    def on_show(self) -> None:
        # Focusing right after revealing does not scroll the input into view:
        # it had no layout region while hidden, and Textual's focus scroll is
        # skipped for a widget it cannot measure. Scroll once layout has it.
        self.scroll_visible(animate=False, immediate=True)
