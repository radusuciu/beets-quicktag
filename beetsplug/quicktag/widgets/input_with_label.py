from textual.widget import Widget
from textual.widgets import Input, Label
from textual.app import ComposeResult


class InputWithLabel(Widget):
    """An input with a label."""

    DEFAULT_CSS = """
    InputWithLabel {
        layout: horizontal;
        height: auto;
    }
    InputWithLabel Label {
        padding: 1;
        width: 12;
        text-align: right;
    }
    InputWithLabel Input {
        width: 1fr;
    }
    """

    def __init__(self, input_label: str, id: str | None = None) -> None:
        self.input_label = input_label
        super().__init__(id=id)

    def compose(self) -> ComposeResult:  
        yield Label(self.input_label)
        yield Input(placeholder="Enter comments here...")

    @property
    def value(self) -> str:
        return self.query_one(Input).value

    @value.setter
    def value(self, value: str) -> None:
        self.query_one(Input).value = value