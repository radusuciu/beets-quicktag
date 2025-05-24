from enum import Enum
from typing import Optional

from beets.dbcore.db import Results as BeetsResults
from beets.library import Item as BeetsItem
from beets.library import Library as BeetsLibrary
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.dom import NoMatches
from textual.widgets import Footer, Static
from textual.widgets.selection_list import Selection

from .widgets.custom_selection_list import CustomSelectionList
from .widgets.input_with_label import InputWithLabel
from .widgets.playback import PlaybackEnded, PlaybackWidget


class NavigateDirection(Enum):
    """Enum for seek direction."""

    FORWARD = 1
    BACKWARD = -1


class HeaderWidget(Vertical):
    """A custom widget for the application header, now including a playback widget."""

    DEFAULT_CSS = """
    HeaderWidget {
        dock: top;
        width: 100%;
        height: auto; /* Adjusts to content: title line + playback widget */
        background: $panel;
        color: $text;
        padding: 0 1;
    }
    #header_text_content {
        width: 100%;
        height: 1;
    }
    """

    def __init__(self, playback_widget: PlaybackWidget, item=None, **kwargs):
        super().__init__(**kwargs)
        self.item: BeetsItem = item
        self._header_text_display = Static(id="header_text_content")
        self.playback_widget = playback_widget

    def compose(self) -> ComposeResult:
        """Compose the header with text and the playback widget."""
        yield self._header_text_display
        yield self.playback_widget

    def on_mount(self) -> None:
        """Set the header text when the widget is mounted."""
        self.update_header()

    def update_header(self, item: Optional[BeetsItem] = None) -> None:
        """Updates the header text."""
        if item:
            self.item = item

        header_text_value = "QuickTag"
        if self.item:
            header_text_value = f"Tagging: {self.item.artist} - {self.item.title}"

        self._header_text_display.update(header_text_value)


class QuickTagApp(App):
    BINDINGS = [
        Binding("escape", "quit", "Quit", show=True, priority=True),
        Binding("left", "previous_item", "Previous", show=True, priority=True),
        Binding("right", "next_item", "Next", show=True, priority=True),
        ("/", "play_pause_current_item", "Play/Pause"),
        ("<", "seek_backward(5)", "Seek -5s"),
        (">", "seek_forward(5)", "Seek +5s"),
    ]

    DEFAULT_CSS = """
    Screen {
        align: center middle;
    }

    SelectionList {
        padding: 1;
        border: solid $accent;
        /* width: 80%; */
        /* height: 80%; */
    }
    """

    def __init__(
        self,
        lib: BeetsLibrary,
        items: BeetsResults,
        categories: list[tuple[str, list[str]]],
        autoplay_on_track_change_enabled: bool,
        autoplay_at_launch_enabled: bool,
        autonext_at_track_end_enabled: bool,
        autosave_on_quit_enabled: bool,
        keep_playing_on_track_change_if_playing_enabled: bool,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.lib = lib
        self.items = items
        self.categories = categories
        self.autoplay_on_track_change_enabled = autoplay_on_track_change_enabled
        self.autoplay_at_launch_enabled = autoplay_at_launch_enabled
        self.autonext_at_track_end_enabled = autonext_at_track_end_enabled
        self.autosave_on_quit_enabled = autosave_on_quit_enabled
        self.keep_playing_on_track_change_if_playing_enabled = keep_playing_on_track_change_if_playing_enabled

        self.current_item_index = 0
        self.item = items[0] if items else None
        self.playback_widget = PlaybackWidget()
        self.header_widget = HeaderWidget(
            item=self.item, playback_widget=self.playback_widget
        )

        self.log.info("QuickTagApp initialized.")

    async def on_mount(self) -> None:
        """Called when the app is mounted."""
        self.theme = "gruvbox"
        await self._set_item(self.item, save_current_item_tags=False)
        if not self.autoplay_at_launch_enabled:
            self.playback_widget.pause()

    async def on_unmount(self) -> None:
        """Called when the app is unmounted."""
        self.log.info("QuickTagApp unmounted.")

    def compose(self) -> ComposeResult:
        yield self.header_widget

        if self.item:
            for category_name, options in self.categories:
                selection_options = [
                    Selection(option_text, option_idx)
                    for option_idx, option_text in enumerate(options)
                ]
                category_selection_list = CustomSelectionList(
                    *selection_options, id=f"selection-{category_name}"
                )
                category_selection_list.border_title = category_name
                yield category_selection_list
            yield InputWithLabel(input_label="Comments:", id="comments-input")
        else:
            yield Static("No items to tag.")

        yield Footer()

    async def action_quit(self) -> None:
        """Action to quit the application."""
        self.log.info(
            f"action_quit called. autosave_on_quit_enabled: {self.autosave_on_quit_enabled}"
        )
        if self.autosave_on_quit_enabled and self.item:
            self.log.info("Autosaving tags before quitting.")
            await self._save_current_item_tags()
        self.exit()

    async def _load_current_item_for_playback(self) -> None:
        """Load the current item for playback."""

        item_path_bytes = self.item.path

        try:
            item_path_str = item_path_bytes.decode("utf-8", "surrogateescape")
        except AttributeError:
            item_path_str = item_path_bytes
        except Exception as e:
            self.log.error(f"Error decoding item path: {e}")
            return

        self.playback_widget.load_track(item_path_str)

    async def _set_item(self, item: BeetsItem, save_current_item_tags=True) -> None:
        """Handle changes to the current item."""
        # Capture the current playback state before changing items
        was_playing_before = self.playback_widget.is_playing()
        
        if save_current_item_tags:
            await self._save_current_item_tags()
        self.item = item
        self.header_widget.update_header(item)
        await self._load_tags_for_current_item()
        self.log.info(f"Item set to: {item.artist} - {item.title}")

        if self.categories:
            first_category_name, _ = self.categories[0]
            try:
                self.query_one(
                    f"#selection-{first_category_name}", CustomSelectionList
                ).focus()
            except NoMatches:
                pass

        # Load the new track (this doesn't start playback automatically)
        await self._load_current_item_for_playback()

        # Determine whether to start playing the new track
        should_play = False
        
        if was_playing_before and self.keep_playing_on_track_change_if_playing_enabled:
            # If we were playing before and the setting allows it, continue playing the new track
            should_play = True
            self.log.info("Continuing playback with new track (was playing before and keep_playing_on_track_change_if_playing enabled)")
        elif self.autoplay_on_track_change_enabled:
            # If autoplay is enabled, start playing regardless of previous state
            should_play = True
            self.log.info("Starting playback due to autoplay_on_track_change setting")
        else:
            # We were paused or keep_playing_on_track_change_if_playing is disabled, stay paused
            self.log.info("Keeping playback paused (was paused, autoplay disabled, or keep_playing_on_track_change_if_playing disabled)")

        if should_play:
            self.playback_widget.play()
        else:
            # Ensure we're paused if we shouldn't be playing
            if self.playback_widget.is_playing():
                self.playback_widget.pause()

    async def _navigate(self, direction: NavigateDirection) -> None:
        """Navigates through the items list in the specified direction."""
        # TODO: Do we need this?
        # TODO: should be exception?
        if not self.item:
            return

        # TODO: do we stop here or elsewhere?
        # self.playback_widget.stop()
        # self.log.info("Playback stopped for next item.")

        if direction == NavigateDirection.FORWARD:
            if self.current_item_index < len(self.items) - 1:
                self.current_item_index += 1
            else:
                self.header_widget._header_text_display.update(
                    "All items processed. Press Esc to quit."
                )
                return
        elif direction == NavigateDirection.BACKWARD:
            if self.current_item_index > 0:
                self.current_item_index -= 1
            else:
                # We don't want to loop back to the last item
                return
        else:
            # this should never happen...
            error_message = f"Invalid direction: {direction}. Use {NavigateDirection.FORWARD} (NavigateDirection.FORWARD) or {NavigateDirection.BACKWARD} (NavigateDirection.BACKWARD)."
            self.log.error(error_message)
            raise ValueError(error_message)

        await self._set_item(self.items[self.current_item_index])

    async def action_next_item(self) -> None:
        """Saves tags for the current item and moves to the next item."""
        await self._navigate(NavigateDirection.FORWARD)
        self.log.info("action_next_item called.")

    async def action_previous_item(self) -> None:
        """Saves tags for the current item and moves to the previous item."""
        await self._navigate(NavigateDirection.BACKWARD)
        self.log.info("action_previous_item called.")

    async def action_play_pause_current_item(self) -> None:
        """Toggles play/pause for the current item."""
        # might not need to check if item exists if we validate earlier
        # but the path does need to exist
        # TODO: check if path exists, probably not here though
        if not self.item or not hasattr(self.item, "path"):
            self.log.warning("No item selected or item has no path.")
            return

        self.playback_widget.play_pause()
        self.log.info("Requested play/pause for current item.")

    async def action_seek_forward(self, seconds: int = 5) -> None:
        """Seeks forward in the current track."""
        if self.item:
            self.playback_widget.seek_relative(seconds)

    async def action_seek_backward(self, seconds: int = 5) -> None:
        """Seeks backward in the current track."""
        if self.item:
            self.playback_widget.seek_relative(-seconds)

    async def on_playback_widget_track_ended(self, message: PlaybackEnded) -> None:
        """Handles the TrackEnded message from PlaybackWidget."""
        self.log.info(
            f"PlaybackWidget.TrackEnded message received. Autoplay next: {self.autoplay_on_track_change_enabled}"
        )
        if self.autonext_at_track_end_enabled:
            if self.current_item_index < len(self.items) - 1:
                self.log.info("Autoplaying next item due to TrackEnded.")
                await self.action_next_item()
            else:
                self.log.info("Track ended, but already at the last item.")
        else:
            self.playback_widget.pause()
            self.playback_widget.seek(0)

    async def _save_current_item_tags(self) -> None:
        """Saves the tags for the current item based on selections."""
        if not self.item:
            self.log.warning("_save_current_item_tags: No item to save.")
            return

        self.log.info(
            f"_save_current_item_tags: Attempting to save tags for {self.item.artist} - {self.item.title}"
        )
        changed = False
        for category_name, options_list in self.categories:
            try:
                selection_list = self.query_one(
                    f"#selection-{category_name}", CustomSelectionList
                )
            except NoMatches:
                self.log.error(
                    f"Could not find SelectionList for category: {category_name} during save."
                )
                continue

            selected_indices_in_list = selection_list.selected
            selected_values = [options_list[i] for i in selected_indices_in_list]

            current_tag_value = ", ".join(selected_values) if selected_values else None
            old_value = self.item.get(category_name)
            self.log.debug(
                f"Category {category_name} for '{self.item.title}': current_tag_value: '{current_tag_value}', old_value: '{old_value}'"
            )

            if current_tag_value:
                if old_value != current_tag_value:
                    self.log.info(
                        f"Updating tag {category_name} from '{old_value}' to '{current_tag_value}' for {self.item.title}"
                    )
                    self.item[category_name] = current_tag_value
                    changed = True
            elif old_value is not None:
                self.log.info(
                    f"Removing tag {category_name} (was '{old_value}') for {self.item.title}"
                )
                del self.item[category_name]
                changed = True

        # Save comments using InputWithLabel
        try:
            comments_widget = self.query_one("#comments-input", InputWithLabel)
            new_comments = comments_widget.value
            old_comments = self.item.get(
                "comments", ""
            )  # Use get with default for comments
            if isinstance(old_comments, bytes):  # Ensure old_comments is a string
                old_comments = old_comments.decode("utf-8", "ignore")

            if old_comments != new_comments:
                self.log.info(
                    f"Updating comments from '{old_comments}' to '{new_comments}' for {self.item.title}"
                )
                if new_comments:
                    self.item["comments"] = new_comments
                elif "comments" in self.item:  # Only delete if it exists
                    del self.item["comments"]
                changed = True
        except NoMatches:
            self.log.error("Could not find comments input for saving.")

        if changed:
            self.log.info(
                f"Changes detected for '{self.item.artist} - {self.item.title}'. Storing item."
            )
            try:
                self.item.store()
                self.log.info(
                    f"Successfully stored item: {self.item.artist} - {self.item.title}"
                )
            except Exception as e:
                self.log.error(
                    f"Error storing item {self.item.artist} - {self.item.title}: {e}"
                )
        else:
            self.log.info(
                f"No changes detected for '{self.item.artist} - {self.item.title}'. Nothing to store."
            )

    async def _load_tags_for_current_item(self) -> None:
        """Loads the tags for the current item into the selection lists."""
        # TODO: I think we should validate earlier that we have a valid items
        if not self.item:
            return

        for category_name, options_list in self.categories:
            try:
                selection_list = self.query_one(
                    f"#selection-{category_name}", CustomSelectionList
                )
            except NoMatches:
                self.log.error(
                    f"Could not find SelectionList for category: {category_name} during load."
                )
                continue

            selection_list.deselect_all()

            current_tag_string = self.item.get(category_name)
            if not current_tag_string:
                continue

            tagged_values_for_category = {
                val.strip() for val in current_tag_string.split(",")
            }

            newly_selected_indices_in_list = []
            for i, option_text_in_list in enumerate(options_list):
                if option_text_in_list in tagged_values_for_category:
                    newly_selected_indices_in_list.append(i)

            if newly_selected_indices_in_list:
                for index_to_select in newly_selected_indices_in_list:
                    selection_list.select(index_to_select)

            selection_list.scroll_to_highlight()

        # Load comments using InputWithLabel
        try:
            comments_widget = self.query_one("#comments-input", InputWithLabel)
            current_comments = self.item.get(
                "comments", ""
            )  # Use get with default for comments
            if isinstance(current_comments, bytes):  # Ensure comments is a string
                current_comments = current_comments.decode("utf-8", "ignore")
            comments_widget.value = current_comments
        except NoMatches:
            self.log.error("Could not find comments input for loading.")
