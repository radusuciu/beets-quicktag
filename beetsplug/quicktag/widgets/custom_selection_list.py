from textual.widgets import SelectionList
from textual import events

class CustomSelectionList(SelectionList):
    """
    A custom SelectionList that handles quick selection via alphanumeric key presses.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.search_char: str | None = None

    async def on_key(self, event: events.Key) -> None:
        """Handle key presses for quick selection.
        Pressing an alphanumeric key attempts to jump to the next item in this
        SelectionList (relative to the currently highlighted item) that starts
        with that character, wrapping around if necessary.
        """
        if not event.character or not event.character.isalnum() or len(event.character) != 1:
            # If the key is not a single alphanumeric character, let Textual's default
            # event handling take care of it (e.g., for arrow keys, Enter).
            return

        pressed_char = event.character.lower()

        # The character to search for is the one just pressed.
        self.search_char = pressed_char 

        if not self.options:
            # No options to search through.
            event.stop() # Consume the event as it's handled
            return

        # Determine the starting point for the search.
        # If nothing is highlighted, effectively start from index -1.
        # The search will then begin at index 0 after adding 1.
        current_highlight_idx = self.highlighted if self.highlighted is not None else -1

        num_options = len(self.options)
        
        # Start searching from the item *after* the currently highlighted one.
        # If current_highlight_idx is -1, start_search_from_idx will be 0.
        # Otherwise, it's (highlighted_index + 1).
        start_search_from_idx = (current_highlight_idx + 1) % num_options

        # Iterate through all options once, effectively wrapping around the list.
        # The loop runs num_options times to check every item starting from start_search_from_idx.
        for i in range(num_options):
            check_idx = (start_search_from_idx + i) % num_options
            
            selection_item = self.options[check_idx]
            # Assuming selection_item.prompt is always a string or Text-compatible object
            option_text = str(selection_item.prompt).lower()

            if option_text.startswith(self.search_char):
                # Match found. Highlight it and stop the event.
                self.highlighted = check_idx
                self.scroll_to_highlight()
                event.stop()
                return
        
        # If the loop completes, no item starting with self.search_char was found
        # (from the position after the current highlight, wrapping around).
        # The current highlight remains unchanged.
        event.stop() # Consume the event even if no match is found to prevent other actions.

